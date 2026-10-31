from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .models import User


class SigeciJWTAuthentication(JWTAuthentication):
    """JWT que resuelve el usuario contra accounts.User (no auth.User)."""

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken("El token no contiene un identificador de usuario.")

        user = User.objects.select_related("profile").filter(pk=user_id).first()
        if user is None or not user.user_active or user.user_delete:
            raise AuthenticationFailed("Usuario inexistente o inactivo.", code="user_inactive")
        return user
