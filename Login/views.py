import hashlib
import json
import logging
import math
import secrets
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.services import PinEmailError, send_recovery_pin_email
from users.models import PasswordResetPin, Profile, User
from users.serializers import UserSerializer
from users.validators import validate_strong_password
from util.auth_service import require_permission
from util.captcha_service import require_captcha
from util.enum.Codes import Codes
from util.utilDB import queryDB

logger = logging.getLogger(__name__)

AUTHOR_PROFILE = "AUTHOR"
INVALID_CREDENTIALS = {"detail": "Credenciales inválidas."}
INVALID_PIN = {"detail": "PIN inválido, vencido o ya utilizado."}
FORGOT_GENERIC = {
    "detail": "Si el correo corresponde a una cuenta activa, recibirás un PIN para restablecer tu contraseña."
}


def _parse_body(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except (ValueError, TypeError):
        return {}


def _user_payload(user):
    data = UserSerializer(user).data
    data["permissions"] = user.permissions_map()
    return data


def _resend_key(email):
    return "pin_resend:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _eligible_user(email):
    return (
        User.objects.prefetch_related("profiles")
        .filter(
            user_email__iexact=email.strip(),
            user_active=True,
            user_delete=False,
            user_provider=User.PROVIDER_ACCOUNT,
        )
        .first()
    )


def _getUser(email):
    try:
        return User.objects.prefetch_related("profiles").get(
            user_email__iexact=email, user_active=True, user_delete=False
        )
    except User.DoesNotExist:
        return None

@require_captcha
def login(request):
    """
    POST /api/v1/auth/login
    Valida credenciales, genera JWT (token + refresh_token) y retorna datos del usuario.
    El captchaToken ya es validado previamente por @require_captcha.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

    data        = _parse_body(request)
    email       = data.get("email").strip()
    password    = data.get("password")

    if not email or not password:
        return JsonResponse({
            "success": False,
            "message": "Correo y contraseña son obligatorios.",
        }, status=400)

    user = _getUser(email)
    if user is None or not check_password(password, user.user_password):
        return JsonResponse({
            "success": False,
            "message": "Credenciales inválidas.",
        }, status=400)

    if not user.user_seed_token:
        user.user_seed_token = str(uuid.uuid4())
        user.save(update_fields=["user_seed_token"])

    refresh = RefreshToken.for_user(user)
    refresh["user_id"] = user.user_id
    refresh["user_seed_token"] = user.user_seed_token

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


@require_captcha
def register(request):
    """
    POST /api/v1/auth/register
    Registro público de usuarios con rol AUTHOR.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    name = (data.get("name") or "").strip()
    lastname = (data.get("lastname") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not lastname or not email or not password:
        return JsonResponse({
            "success": False,
            "message": "Todos los campos son obligatorios.",
        }, status=400)

    try:
        validate_strong_password(password)
    except (DjangoValidationError, DRFValidationError) as exc:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, list) and detail:
            msg = str(detail[0])
        elif getattr(exc, "messages", None):
            msg = exc.messages[0]
        else:
            msg = str(exc)
        return JsonResponse({"success": False, "message": msg}, status=400)

    author = Profile.objects.filter(
        profile_name=AUTHOR_PROFILE, profile_active=True, profile_delete=False
    ).first()
    if author is None:
        logger.error("Registro público: no existe el perfil AUTHOR.")
        return JsonResponse({
            "success": False,
            "message": "El registro no está disponible en este momento.",
        }, status=503)

    if User.objects.filter(user_email__iexact=email).exists():
        return JsonResponse({
            "success": False,
            "message": "Ya existe una cuenta registrada con este correo.",
        }, status=409)

    user = User(
        user_name=name,
        user_lastname=lastname,
        user_email=email,
        user_provider=User.PROVIDER_ACCOUNT,
        user_seed_token=str(uuid.uuid4()),
    )
    user.set_password(password)

    try:
        with transaction.atomic():
            user.save()
            user.profiles.add(author)
    except IntegrityError:
        return JsonResponse({
            "success": False,
            "message": "Ya existe una cuenta registrada con este correo.",
        }, status=409)

    return JsonResponse({
        "success": True,
        "message": "Cuenta creada exitosamente. Ya puedes iniciar sesión.",
        "data": UserSerializer(user).data,
    }, status=201)


@require_permission(endpoint="me", action="view")
def me(request):
    """
    GET /api/v1/auth/me
    Devuelve los datos y permisos del usuario autenticado a partir del JWT.
    """
    if request.method != "GET":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

    # ejecutar peticion a permisos para renderizar menu
    profile = request.user.get("profile_id")

    menu = queryDB("""
        select
            *
        from profile_action pa
        inner join profile pr
            on pr.profile_id = pa.profile_id
            and pr.profile_active = true
            and pr.profile_delete = false
        where
            pa.profile_id = %s
            and pa.profile_action_active = true
            and pa.profile_action_delete = false
    """, [profile])

    if not menu:
        return JsonResponse({
            "success": False,
            "message": "Usuario no encontrado o inactivo.",
            "action": "closeSession"
        }, status=401)

    return JsonResponse({
        "success": True,
        "message": "Response OK",
        "data": menu
    }, status=200)


def refresh_token(request):
    """
    POST /api/v1/auth/refresh o /api/v1/auth/refresh-token
    Renueva el access token a partir del refresh token.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    token_str = data.get("refresh_token")

    if not token_str:
        return JsonResponse({
            "success": False,
            "message": Codes.UNAUTHORIZED.value,
            "internMessage": "El token de refresco es obligatorio.",
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

    refresh["user_id"] = user.user_id
    refresh["user_seed_token"] = user.user_seed_token
    new_access = str(refresh.access_token)

    return JsonResponse({
        "success": True,
        "message": "Token renovado exitosamente.",
        "data": {
            "token": new_access,
            "refresh_token": str(refresh),
        }
    }, status=200)


def forgot_password(request):
    """
    POST /api/v1/auth/password/forgot
    Envía PIN de recuperación por correo.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

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


def reset_password(request):
    """
    POST /api/v1/auth/password/reset
    Verifica el PIN y actualiza la contraseña del usuario.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Método no permitido.", "success": False}, status=405)

    data = _parse_body(request)
    email = (data.get("email") or "").strip()
    pin = (str(data.get("pin") or "")).strip()
    password = data.get("password")

    if not email or not pin or not password:
        return JsonResponse({
            "success": False,
            "message": "Correo, PIN y nueva contraseña son obligatorios."
        }, status=400)

    try:
        validate_strong_password(password)
    except (DjangoValidationError, DRFValidationError) as exc:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, list) and detail:
            msg = str(detail[0])
        elif getattr(exc, "messages", None):
            msg = exc.messages[0]
        else:
            msg = str(exc)
        return JsonResponse({"success": False, "message": msg}, status=400)

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