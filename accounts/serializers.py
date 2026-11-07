from django.conf import settings
from rest_framework import serializers

from .validators import validate_strong_password


# --------------------------------------------------------------------------- #
# Autenticación y recuperación
# --------------------------------------------------------------------------- #
class LoginSerializer(serializers.Serializer):
    """Contrato final: { identifier, password, captchaToken }.
    `email` se acepta como alias de `identifier` por compatibilidad."""

    identifier = serializers.CharField(required=False, max_length=120)
    email = serializers.CharField(required=False, max_length=120)
    password = serializers.CharField(trim_whitespace=False)
    captchaToken = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        identifier = (attrs.get("identifier") or attrs.get("email") or "").strip()
        if not identifier:
            raise serializers.ValidationError({"identifier": "Este campo es obligatorio."})
        attrs["identifier"] = identifier
        return attrs


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    pin = serializers.RegexField(
        r"^\d+$", min_length=settings.PASSWORD_RESET_PIN_LENGTH,
        max_length=settings.PASSWORD_RESET_PIN_LENGTH,
        error_messages={"invalid": "El PIN debe contener solo dígitos."},
    )
    password = serializers.CharField(validators=[validate_strong_password])
