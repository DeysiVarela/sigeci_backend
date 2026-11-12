from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from ..models import Profile, User
from ..permissions import HasProfilePermission
from .serializers import (
    ChangePasswordSerializer, MyProfileUpdateSerializer, ProfileSerializer, UserCreateSerializer,
    UserSerializer, UserUpdateSerializer, is_admin, is_last_admin,
)

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

    def _ensure_can_manage(self, request, target):
        """Quien no es administrador no puede modificar ni eliminar cuentas de administradores."""
        if is_admin(target) and not is_admin(request.user):
            raise PermissionDenied("Solo un administrador puede modificar o eliminar cuentas de administradores.")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        self._ensure_can_manage(request, instance)
        ser = self.get_serializer(instance, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return self._respond_with_read_serializer(user, status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        self._ensure_can_manage(request, user)
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "No puedes eliminar tu propia cuenta."})
        if is_last_admin(user):
            raise ValidationError({"detail": "No se puede eliminar al único administrador activo."})
        # Borrado lógico: el usuario pierde el acceso y desaparece de la API, pero su registro se
        # conserva (integridad referencial con otras tablas, p. ej. article_reviewer).
    # Generar el sufijo con fecha y hora actual (Ej: _delete_20261112_103900)
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")

    # Nota: se agrega fecha al correo 
        if user.user_email:
            user.user_email = f"{user.user_email}_delete_{timestamp}"

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


# --------------------------------------------------------------------------- #
# SCRUM-125: mi perfil (solo operan sobre el usuario de la sesión)
# --------------------------------------------------------------------------- #
class PasswordChangeRateThrottle(UserRateThrottle):
    """Límite de intentos por usuario. Configurable con PASSWORD_CHANGE_RATE (por defecto 5/min)."""

    scope = "password_change"

    def get_rate(self):
        return getattr(settings, "PASSWORD_CHANGE_RATE", "5/min")


def _my_payload(user):
    """Misma forma que /api/auth/me/ (con `permissions`): el frontend puede refrescar la sesión con la respuesta."""
    data = dict(UserSerializer(user).data)
    data["permissions"] = user.permissions_map()
    return data


class MyProfileView(APIView):
    """
    GET   /api/users/me   -> mis datos
    PATCH /api/users/me   -> actualizo mi nombre, apellido y correo

    No recibe ningún id y no exige permisos de la matriz: cada usuario gestiona su propio perfil.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_my_payload(request.user))

    def patch(self, request):
        ser = MyProfileUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = ser.save()
        except IntegrityError:  # dos cambios simultáneos al mismo correo
            raise ValidationError({"email": ["Ya existe un usuario con este correo."]})
        return Response(_my_payload(user))


class MyPasswordView(APIView):
    """PUT /api/users/me/password/ -> cambio mi contraseña (pide la actual)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordChangeRateThrottle]

    def put(self, request):
        user = request.user
        if user.user_provider != User.PROVIDER_ACCOUNT:
            return Response(
                {"detail": "Tu cuenta no usa una contraseña propia; no se puede cambiar aquí."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        user.set_password(ser.validated_data["newPassword"])
        user.user_updated_by = user
        with transaction.atomic():
            user.save(update_fields=["user_password", "user_updated_by", "user_updated_at"])
            # Un PIN de recuperación pedido antes del cambio ya no debe servir
            user.reset_pins.filter(used_at__isnull=True).update(used_at=timezone.now())
        return Response({"detail": "Contraseña actualizada."})
