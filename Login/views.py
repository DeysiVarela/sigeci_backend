import json
import logging
import math
import secrets
import time
from datetime import timedelta

from util.enum.Codes import Codes

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import PasswordResetPin, User
from accounts.users.serializers import UserSerializer
from accounts.views import (
    INVALID_CREDENTIALS,
    INVALID_PIN,
    FORGOT_GENERIC,
    _eligible_user,
    _resend_key,
    _user_payload,
)
from notifications.services import PinEmailError, send_recovery_pin_email
from util.captcha_service import require_captcha

logger = logging.getLogger(__name__)


def _parse_body(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, TypeError):
        return {}


@csrf_exempt
@require_captcha
def login(request):
    """
    POST /api/v1/auth/login
    Valida credenciales, genera JWT (access + refresh) y retorna datos del usuario.
    El captchaToken ya es validado previamente por @require_captcha.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed", "success": False}, status=405)

    data        = json.loads(request.body.decode('utf-8'))
    email       = data.get("email").strip()
    password    = data.get("password")

    if not email or not password:
        return JsonResponse({
            "success": False,
            "message": "Correo y contraseña son obligatorios.",
            "detail": "Credenciales incompletas."
        }, status=400)

    user = _getUser(email)
    if user is None or not check_password(password, user.user_password):
        return JsonResponse({
            "success": False,
            "message": "Credenciales inválidas.",
            "detail": INVALID_CREDENTIALS["detail"]
        }, status=400)

    # Generamos tokens JWT
    refresh         = RefreshToken.for_user(user)

    refresh["user_id"]          = user.user_id
    refresh["profile_id"]       = user.profile_id
    refresh["user_seed_token"]  = user.user_seed_token

    access_token    = str(refresh.access_token)
    refresh_token   = str(refresh)
    user_data       = _user_payload(user)

    return JsonResponse({
        "success": True,
        "message": "Inicio de sesión exitoso.",
        "data": {
            "token":           access_token,
            "refresh_token":   refresh_token,
            "user":            user_data
        }
    }, status=200)


@csrf_exempt
def me(request):
    """
    GET /api/v1/auth/me
    Devuelve los datos y permisos del usuario autenticado a partir del JWT.
    """
    if request.method != "GET":
        return JsonResponse({"detail": "Método no permitido.", "success": False}, status=405)

    token = request.headers.get("Authorization")
    if not token:
        return JsonResponse({
            "success": False,
            "message": "Token de autenticación requerido.",
            "action": "closeSession"
        }, status=401)

    raw_token = token.split(" ")[1] if token.startswith("Bearer ") else token

    try:
        from rest_framework_simplejwt.tokens import AccessToken
        token_obj = AccessToken(raw_token)
        user_id = token_obj["user_id"]
        user = User.objects.select_related("profile").filter(
            pk=user_id,
            user_active=True,
            user_delete=False
        ).first()
    except Exception:
        return JsonResponse({
            "success": False,
            "message": "Token inválido o expirado.",
            "action": "closeSession"
        }, status=401)

    if not user:
        return JsonResponse({
            "success": False,
            "message": "Usuario no encontrado o inactivo.",
            "action": "closeSession"
        }, status=401)

    return JsonResponse({
        "success": True,
        "message": "Usuario obtenido con éxito.",
        "data": _user_payload(user)
    }, status=200)


@csrf_exempt
def refresh_token(request):
    """
    POST /api/v1/auth/refresh o /api/v1/auth/refresh-token
    Renueva el access token a partir del refresh token.
    Compatible tanto con { refresh: "..." } como con { refresh_token: "..." }.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    token_str = data.get("refresh_token") or data.get("refresh")

    if not token_str:
        return JsonResponse({
            "success": False,
            "message": Codes.UNAUTHORIZED.value,
            "internMessage": "El token de refresco es obligatorio.",
            "detail": "Missing refresh token."
        }, status=400)

    try:
        refresh = RefreshToken(token_str)
        user = User.objects.filter(pk=refresh["user_id"], user_active=True, user_delete=False).first()
    except (TokenError, KeyError, Exception):
        return JsonResponse({
            "success": False,
            "message": "Token inválido o vencido.",
            "action": "closeSession"
        }, status=401)

    if user is None:
        return JsonResponse({
            "success": False,
            "message": "Usuario no encontrado o inactivo.",
            "action": "closeSession"
        }, status=401)

    new_access = str(refresh.access_token)

    return JsonResponse({
        "success": True,
        "message": "Token renovado exitosamente.",
        "data": {
            "token": new_access,
            "access": new_access,
            "refresh_token": str(refresh),
            "refresh": str(refresh),
        }
    }, status=200)


@csrf_exempt
def forgot_password(request):
    """
    POST /api/v1/auth/password/forgot
    Envía PIN de recuperación por correo.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    email = (data.get("email") or "").strip()

    if not email:
        return JsonResponse({
            "success": False,
            "message": "El correo es obligatorio."
        }, status=400)

    wait = settings.PASSWORD_RESET_RESEND_SECONDS
    key = _resend_key(email)
    now_ts = time.time()
    until = cache.get(key)

    if until and until > now_ts:
        remaining = math.ceil(until - now_ts)
        unit = "segundo" if remaining == 1 else "segundos"
        return JsonResponse({
            "success": False,
            "message": f"Espera {remaining} {unit} para solicitar un nuevo PIN.",
            "retry_after": remaining
        }, status=429)

    cache.set(key, now_ts + wait, wait)
    user = _eligible_user(email)

    if user is not None:
        now = timezone.now()
        last = user.reset_pins.first()
        cooldown = timedelta(seconds=settings.PASSWORD_RESET_RESEND_SECONDS)
        if last is None or now - last.created_at >= cooldown:
            length = settings.PASSWORD_RESET_PIN_LENGTH
            pin = "".join(str(secrets.randbelow(10)) for _ in range(length))
            with transaction.atomic():
                user.reset_pins.filter(used_at__isnull=True).update(used_at=now)
                PasswordResetPin.objects.create(
                    user=user,
                    pin_hash=make_password(pin),
                    expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_PIN_MINUTES),
                )
            try:
                send_recovery_pin_email(user.user_email, pin)
            except PinEmailError:
                logger.error("No se pudo enviar el PIN de recuperación (user_id=%s)", user.pk)
            except Exception:
                logger.exception("Error inesperado enviando el PIN (user_id=%s)", user.pk)

    return JsonResponse({
        "success": True,
        "message": FORGOT_GENERIC["detail"],
        "retry_after": wait
    }, status=200)


@csrf_exempt
def reset_password(request):
    """
    POST /api/v1/auth/password/reset
    Verifica el PIN y actualiza la contraseña del usuario.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    email = (data.get("email") or "").strip()
    pin = (str(data.get("pin") or "")).strip()
    password = data.get("password") or data.get("pass")

    if not email or not pin or not password:
        return JsonResponse({
            "success": False,
            "message": "Correo, PIN y nueva contraseña son obligatorios."
        }, status=400)

    user = _eligible_user(email)
    if user is None:
        return JsonResponse({
            "success": False,
            "message": INVALID_PIN["detail"]
        }, status=400)

    with transaction.atomic():
        pin_row = (
            PasswordResetPin.objects.select_for_update()
            .filter(user=user, used_at__isnull=True, expires_at__gt=timezone.now())
            .order_by("-created_at")
            .first()
        )
        if pin_row is None:
            return JsonResponse({"success": False, "message": INVALID_PIN["detail"]}, status=400)

        if pin_row.attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
            pin_row.used_at = timezone.now()
            pin_row.save(update_fields=["used_at"])
            return JsonResponse({"success": False, "message": INVALID_PIN["detail"]}, status=400)

        if not check_password(pin, pin_row.pin_hash):
            pin_row.attempts += 1
            pin_row.save(update_fields=["attempts"])
            return JsonResponse({"success": False, "message": INVALID_PIN["detail"]}, status=400)

        user.set_password(password)
        user.save(update_fields=["user_password", "user_updated_at"])
        user.reset_pins.filter(used_at__isnull=True).update(used_at=timezone.now())

    return JsonResponse({
        "success": True,
        "message": "Contraseña actualizada exitosamente. Ya puedes iniciar sesión."
    }, status=200)


def _getUser(email):
    try:
        return User.objects.get(user_email=email, user_active=True, user_delete=False)
    except User.DoesNotExist:
        return None