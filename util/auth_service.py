
import jwt
import os
import logging
from functools import wraps
from util.enum.Codes import Codes
from django.db import connection
from django.http import JsonResponse 

logger = logging.getLogger(__name__)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

# Decodificamos token
def decode_token(token_header):
    if not token_header:
        return None
    token = token_header.split(" ")[1] if token_header.startswith("Bearer ") else token_header
    try:
        payload = jwt.decode(token, key=SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception as e:
        logger.error(f"Error al decodificar token: {e}")
        return None

# Validar seed Token
def validate_seed_token(user_id, user_seed_token):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM users WHERE user_id = %s AND user_seed_token = %s",
            [user_id, user_seed_token]
        )
        row = cursor.fetchone()
        return bool(row and row[0])


# validamos permisos del usuario para su peticion
def check_permission(user_id, endpoint, action):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT 
                    profile_action_permissions 
                FROM 
                    profile_action pa 
                inner join profile p 
                    on pa.profile_id = p.profile_id 
                inner join users u 
                    on u.profile_id = p.profile_id 
                where 
                    u.user_id = %s
                    and pa.profile_action_action = %s
            """,
            [user_id, endpoint]
        )
        row = cursor.fetchone()
        print("row", row)
        permissions = row[0].split("|")
        print("permissions", permissions)
        # create|view|update
        if action in permissions:
            return True
        return False


def require_permission(endpoint: str, action: str):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            token = request.headers.get("Authorization")
            payload = decode_token(token)
            if not payload:
                return JsonResponse({
                    "message": Codes.UNAUTHORIZED.value,
                    "success": False,
                    "internMessage": "Token inválido o expirado"
                }, status=401)
            user_id         = payload.get("user_id")
            profile_id      = payload.get("profile_id")
            user_seed_token = payload.get("user_seed_token")

            user = {
                "user_id":          user_id,
                "profile_id":       profile_id,
                "user_seed_token":  user_seed_token
            }
            
            request.user = user

            if not validate_seed_token(user_id, user_seed_token):
                return JsonResponse({
                    "message": Codes.NOT_PERMISSION.value,
                    "success": False,
                    "internMessage": "Your user needs to login again",
                    "action": "closeSession"
                }, status=401)
            
            if not check_permission(user_id, endpoint, action):
                return JsonResponse({
                    "message": Codes.NOT_PERMISSION.value,
                    "success": False,
                    "internMessage": "you don't have permission"
                }, status=403)

            return func(request, *args, **kwargs)
        return wrapper
    return decorator