import json
import os
from django.http import HttpResponse
from django.http import JsonResponse
import requests

''' TODA LA LOGICA DE CAPTCHA DE GOOGLE '''

"""
    Verifica el token de reCAPTCHA con la API de Google
    Args:
        token: Token de reCAPTCHA
    Returns:
        bool: True si el token es válido, False en caso contrario
"""
def verify_captcha(token):
    recaptcha_api_url = os.getenv("RECAPTCHA_API_URL")
    secret_key = os.getenv("RECAPTCHA_SECRET_KEY")

    if not secret_key or not recaptcha_api_url:
        return False, "reCAPTCHA no está configurado."
    
    params = {
        'secret': secret_key,
        'response': token,
    }
    
    response = requests.post(recaptcha_api_url, data=params)
    result = response.json()
    
    return result['success']

def require_captcha(func):
    def wrapper(request, *args, **kwargs):
        if request.method == 'OPTIONS':
            return view_func(request, *args, **kwargs)
        
        try:
            body = json.loads(request.body.decode('utf-8')) if request.body else {}
            token = body.get('captchaToken')
        except (ValueError, TypeError):
            return ApiResponse.error(
                message="Petición con formato inválido.",
                intern_message="JSON body parse error.",
                status=400
            )
        res = verify_captcha(token)
        if not res:
            return JsonResponse({
                "message": "reCAPTCHA inválido.",
                "success": False,
                "intern_message": "reCAPTCHA verification failed."
            }, status=400)
        return func(request, *args, **kwargs)
    return wrapper