import json
import os
from django.http import JsonResponse
import requests

def verify_captcha(token):
    """Verifica el token de reCAPTCHA con la API de Google."""
    recaptcha_api_url = os.getenv("RECAPTCHA_API_URL")
    secret_key = os.getenv("RECAPTCHA_SECRET_KEY")

    if not secret_key or not token:
        return False

    params = {
        "secret": secret_key,
        "response": token,
    }

    try:
        response = requests.post(recaptcha_api_url, data=params, timeout=5)
        result = response.json()
        return bool(result.get("success"))
    except Exception:
        return False


def require_captcha(func):
    def wrapper(request, *args, **kwargs):
        if request.method == "OPTIONS":
            return func(request, *args, **kwargs)

        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
            token = body.get("captchaToken")
        except (ValueError, TypeError):
            return JsonResponse({
                "success": False,
                "message": "Petición con formato inválido.",
                "internMessage": "JSON body parse error.",
            }, status=400)

        if not verify_captcha(token):
            return JsonResponse({
                "success": False,
                "message": "reCAPTCHA inválido.",
                "internMessage": "reCAPTCHA verification failed.",
            }, status=400)

        return func(request, *args, **kwargs)
    return wrapper
