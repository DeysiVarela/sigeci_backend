import json
import os
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


RECAPTCHA_VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify'


def _response(data, status=200, origin=None):
    allowed_origins = {
        origin.strip()
        for origin in os.getenv(
            'FRONTEND_ORIGINS',
            os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173'),
        ).split(',')
    }
    response = JsonResponse(data, status=status)
    response['Access-Control-Allow-Origin'] = (
        origin
        if origin in allowed_origins
        else next(iter(allowed_origins), 'http://localhost:5173')
    )
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response


def health(request):
    return _response({'status': 'ok'})


@csrf_exempt
def login(request):
    origin = request.headers.get('Origin')
    if request.method == 'OPTIONS':
        return _response({}, origin=origin)
    if request.method != 'POST':
        return _response({'message': 'Método no permitido.'}, status=405, origin=origin)

    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return _response(
            {'message': 'La solicitud no tiene un formato válido.'},
            status=400,
            origin=origin,
        )

    identifier = payload.get('identifier')
    password = payload.get('password')
    captcha_token = payload.get('captchaToken')
    if not identifier or not password or not captcha_token:
        return _response(
            {'message': 'Correo, contraseña y CAPTCHA son obligatorios.'},
            status=400,
            origin=origin,
        )

    secret_key = os.getenv('RECAPTCHA_SECRET_KEY')
    if not secret_key:
        return _response(
            {'message': 'El servicio de autenticación no está disponible.'},
            status=503,
            origin=origin,
        )

    if not _verify_captcha(captcha_token, request.META.get('REMOTE_ADDR')):
        return _response(
            {'message': 'La verificación CAPTCHA no es válida. Inténtalo nuevamente.'},
            status=400,
            origin=origin,
        )

    if (
        identifier != os.getenv('DEMO_USER_EMAIL')
        or password != os.getenv('DEMO_USER_PASSWORD')
    ):
        return _response(
            {'message': 'Las credenciales no son válidas.'},
            status=401,
            origin=origin,
        )

    return _response({
        'message': 'Inicio de sesión exitoso.',
        'user': {'identifier': identifier},
    }, origin=origin)


def _verify_captcha(token, remote_ip):
    secret_key = os.getenv('RECAPTCHA_SECRET_KEY')
    values = {'secret': secret_key, 'response': token}
    if remote_ip:
        values['remoteip'] = remote_ip

    try:
        request = Request(
            RECAPTCHA_VERIFY_URL,
            data=urlencode(values).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read())
        return result.get('success') is True
    except (OSError, URLError, ValueError):
        return False
