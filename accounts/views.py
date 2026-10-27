import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .captcha import verify_captcha
from .models import PasswordResetPin, Profile, User
from .permissions import HasProfilePermission
from .serializers import (
    ForgotPasswordSerializer, LoginSerializer, ProfileSerializer, RefreshSerializer,
    ResetPasswordSerializer, UserCreateSerializer, UserSerializer, UserUpdateSerializer,
    is_last_admin,
)

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = {"detail": "Credenciales inválidas."}
INVALID_PIN = {"detail": "PIN inválido, vencido o ya utilizado."}
FORGOT_GENERIC = {
    "detail": "Si el correo corresponde a una cuenta activa, recibirás un PIN para restablecer tu contraseña."
}


def _user_payload(user):
    data = UserSerializer(user).data
    data["permissions"] = user.permissions_map()
    return data


def _eligible_user(email):
    """Cuenta que puede iniciar sesión / recuperar clave con contraseña."""
    return (
        User.objects.select_related("profile")
        .filter(
            user_email__iexact=email.strip(),
            user_active=True,
            user_delete=False,
            user_provider=User.PROVIDER_ACCOUNT,
        )
        .first()
    )


# --------------------------------------------------------------------------- #
# SCRUM-15: login y recuperación en dos pasos
# --------------------------------------------------------------------------- #
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not verify_captcha(ser.validated_data.get("captchaToken"), request.META.get("REMOTE_ADDR")):
            return Response(
                {"detail": "Verificación CAPTCHA inválida o vencida."}, status=status.HTTP_400_BAD_REQUEST
            )
        user = _eligible_user(ser.validated_data["identifier"])
        # Mismo mensaje para "no existe", "inactivo" y "clave incorrecta"
        if user is None or not user.check_password(ser.validated_data["password"]):
            return Response(INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh), "user": _user_payload(user)}
        )


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        ser = RefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(ser.validated_data["refresh"])
            user = User.objects.filter(pk=refresh["user_id"], user_active=True, user_delete=False).first()
        except (TokenError, KeyError):
            return Response({"detail": "Token inválido o vencido."}, status=status.HTTP_401_UNAUTHORIZED)
        if user is None:
            return Response({"detail": "Token inválido o vencido."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"access": str(refresh.access_token)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))


class ForgotPasswordView(APIView):
    """Paso 1: genera y envía el PIN. La respuesta es siempre la misma."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        ser = ForgotPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"]
        user = _eligible_user(email)

        if user is not None:
            now = timezone.now()
            last = user.reset_pins.first()
            cooldown = timedelta(seconds=settings.PASSWORD_RESET_RESEND_SECONDS)
            if last is None or now - last.created_at >= cooldown:
                length = settings.PASSWORD_RESET_PIN_LENGTH
                pin = "".join(str(secrets.randbelow(10)) for _ in range(length))
                with transaction.atomic():
                    user.reset_pins.filter(used_at__isnull=True).update(used_at=now)  # invalida anteriores
                    PasswordResetPin.objects.create(
                        user=user,
                        pin_hash=make_password(pin),
                        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_PIN_MINUTES),
                    )
                try:
                    send_mail(
                        "SIGECI - PIN para restablecer tu contraseña",
                        f"Tu PIN es: {pin}\n\nVence en {settings.PASSWORD_RESET_PIN_MINUTES} minutos. "
                        "Si no lo solicitaste, ignora este mensaje.",
                        settings.DEFAULT_FROM_EMAIL,
                        [user.user_email],
                    )
                except Exception:  # noqa: BLE001 - no revelar nada al cliente
                    logger.exception("No se pudo enviar el PIN de recuperación (user_id=%s)", user.pk)
        return Response(FORGOT_GENERIC)


class ResetPasswordView(APIView):
    """Paso 2: verifica el PIN y establece la nueva contraseña."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        ser = ResetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        user = _eligible_user(data["email"])
        if user is None:
            return Response(INVALID_PIN, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            pin_row = (
                PasswordResetPin.objects.select_for_update()
                .filter(user=user, used_at__isnull=True, expires_at__gt=timezone.now())
                .order_by("-created_at")
                .first()
            )
            if pin_row is None:
                return Response(INVALID_PIN, status=status.HTTP_400_BAD_REQUEST)

            if pin_row.attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
                pin_row.used_at = timezone.now()
                pin_row.save(update_fields=["used_at"])
                return Response(INVALID_PIN, status=status.HTTP_400_BAD_REQUEST)

            if not check_password(data["pin"], pin_row.pin_hash):
                pin_row.attempts += 1
                pin_row.save(update_fields=["attempts"])
                return Response(INVALID_PIN, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(data["password"])
            user.save(update_fields=["user_password", "user_updated_at"])
            user.reset_pins.filter(used_at__isnull=True).update(used_at=timezone.now())

        return Response({"detail": "Contraseña actualizada. Ya puedes iniciar sesión."})


# --------------------------------------------------------------------------- #
# SCRUM-16 / 61 / 62: CRUD de usuarios
# --------------------------------------------------------------------------- #
class UserPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class UserViewSet(viewsets.ModelViewSet):
    """
    GET    /api/users/?page=&page_size=&profile=<id>&active=<true|false>
    POST   /api/users/
    GET    /api/users/{id}/
    PATCH  /api/users/{id}/
    DELETE /api/users/{id}/   -> borrado lógico
    """

    permission_classes = [IsAuthenticated, HasProfilePermission]
    permission_resource = "user"
    pagination_class = UserPagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def get_queryset(self):
        qs = User.objects.select_related("profile").filter(user_delete=False).order_by("user_id")
        if self.action != "list":
            return qs

        params = self.request.query_params
        profile = params.get("profile")
        active = params.get("active")
        if profile not in (None, ""):
            if not profile.isdigit():
                raise ValidationError({"profile": "Debe ser el id numérico de un rol."})
            qs = qs.filter(profile_id=int(profile))
        if active not in (None, ""):
            value = active.lower()
            if value not in ("true", "false"):
                raise ValidationError({"active": "Use true o false."})
            qs = qs.filter(user_active=(value == "true"))
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def _respond_with_read_serializer(self, instance, status_code):
        return Response(UserSerializer(instance).data, status=status_code)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = ser.save()
        except IntegrityError:  # carrera entre dos altas con el mismo correo
            raise ValidationError({"email": "Ya existe un usuario con este correo."})
        return self._respond_with_read_serializer(user, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        ser = self.get_serializer(instance, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return self._respond_with_read_serializer(user, status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "No puedes eliminar tu propia cuenta."})
        if is_last_admin(user):
            raise ValidationError({"detail": "No se puede eliminar al único administrador activo."})
        user.user_delete = True
        user.user_active = False
        user.user_updated_by = request.user
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CanViewUsers(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and getattr(u, "is_authenticated", False) and u.has_perm_on("user", "view"))


class ProfileListView(ListAPIView):
    """Roles disponibles para los selects del frontend."""

    permission_classes = [IsAuthenticated, CanViewUsers]
    serializer_class = ProfileSerializer
    pagination_class = None
    queryset = Profile.objects.filter(profile_active=True, profile_delete=False).order_by("profile_id")
