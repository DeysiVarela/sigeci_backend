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


# Campos con los que alguien podría intentar elegir su propio rol en el autorregistro
ROLE_FIELDS = ("profile", "profile_id", "profile_name", "role", "role_id", "rol", "perfil", "user_role")


class RegisterSerializer(serializers.Serializer):
    """Registro público: los mismos datos que crear usuario (nombre, apellido, correo y clave) sin el rol,
    más el token del CAPTCHA. El rol NO es un campo: siempre se asigna AUTHOR en la vista."""

    name = serializers.CharField(max_length=60)
    lastname = serializers.CharField(max_length=60)
    email = serializers.EmailField(max_length=120)
    password = serializers.CharField(write_only=True, trim_whitespace=False, validators=[validate_strong_password])
    captchaToken = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo es obligatorio.")
        return value

    validate_lastname = validate_name

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        # Cualquier valor en un campo de rol/perfil se rechaza: no existe el autorregistro con privilegios
        sent = [k for k in ROLE_FIELDS if self.initial_data.get(k) not in (None, "")]
        if sent:
            raise serializers.ValidationError({"profile": "No se permite indicar el rol o perfil en el registro."})
        return attrs
