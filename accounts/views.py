import hashlib
import logging
import math
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.services import PinEmailError, send_recovery_pin_email

from .captcha import captcha_configured, captcha_required, verify_captcha
from .models import PasswordResetPin, User
from .serializers import (
    ForgotPasswordSerializer, LoginSerializer, RefreshSerializer, ResetPasswordSerializer,
)
from .users.serializers import UserSerializer

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


def _resend_key(email):
    """Clave de la espera entre solicitudes de PIN (por correo, sin distinguir mayúsculas)."""
    return "pin_resend:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()


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
        if captcha_required() and not captcha_configured():
            logger.error("CAPTCHA obligatorio pero RECAPTCHA_SECRET_KEY no está configurada: login deshabilitado.")
            return Response(
                {"detail": "El servicio de autenticación no está disponible."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
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

        # Espera entre solicitudes. Se aplica IGUAL exista o no la cuenta, para no revelar
        # qué correos están registrados.
        wait = settings.PASSWORD_RESET_RESEND_SECONDS
        key = _resend_key(email)
        now_ts = time.time()
        until = cache.get(key)
        if until and until > now_ts:
            remaining = math.ceil(until - now_ts)
            unit = "segundo" if remaining == 1 else "segundos"
            response = Response(
                {"detail": f"Espera {remaining} {unit} para solicitar un nuevo PIN.", "retry_after": remaining},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(remaining)
            return response
        cache.set(key, now_ts + wait, wait)

        # Solo se genera y envía el PIN si el correo pertenece a una cuenta registrada y activa
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
                    send_recovery_pin_email(user.user_email, pin)
                except PinEmailError:
                    logger.error("No se pudo enviar el PIN de recuperación (user_id=%s)", user.pk)
                except Exception:  # noqa: BLE001 - nunca revelar nada al cliente
                    logger.exception("Error inesperado enviando el PIN (user_id=%s)", user.pk)
        return Response({**FORGOT_GENERIC, "retry_after": wait})


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
