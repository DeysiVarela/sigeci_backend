"""Verificación de CAPTCHA (SCRUM-15, CA-02).

Si CAPTCHA_SECRET_KEY está vacío (desarrollo) no se exige. Si está definido,
el token es obligatorio y se valida contra CAPTCHA_VERIFY_URL; ante cualquier
fallo del servicio se rechaza el intento (fail-closed).
Sirve para reCAPTCHA y para Cloudflare Turnstile (solo cambia la URL).
"""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def captcha_enabled():
    return bool(getattr(settings, "CAPTCHA_SECRET_KEY", ""))


def verify_captcha(token, remote_ip=None):
    if not captcha_enabled():
        return True
    if not token:
        return False
    data = {"secret": settings.CAPTCHA_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    req = urllib.request.Request(
        settings.CAPTCHA_VERIFY_URL,
        data=urllib.parse.urlencode(data).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return bool(json.load(resp).get("success"))
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo verificar el CAPTCHA")
        return False
