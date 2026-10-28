"""CAPTCHA del login (SCRUM-15, CA-02), integrado con auth_api (SCRUM-18).

- Misma variable que auth_api: RECAPTCHA_SECRET_KEY.
- La verificación contra Google es UNA sola: la de auth_api (`_verify_captcha`).
  Aquí solo se define la política: obligatorio por defecto y fail-closed.
- Solo en desarrollo se puede desactivar con CAPTCHA_REQUIRED=False
  (en settings se fuerza a True cuando DEBUG está apagado).
"""
import logging
import os

from django.conf import settings

from auth_api.views import _verify_captcha

logger = logging.getLogger(__name__)


def captcha_required():
    return getattr(settings, "CAPTCHA_REQUIRED", True)


def captcha_configured():
    return bool(os.getenv("RECAPTCHA_SECRET_KEY"))


def verify_captcha(token, remote_ip=None):
    if not captcha_required():
        return True
    if not captcha_configured() or not token:
        return False
    return _verify_captcha(token, remote_ip)
