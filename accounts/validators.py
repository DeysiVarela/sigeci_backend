import re

from django.contrib.auth.password_validation import validate_password as django_validate
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

# Misma regla que InputPassword.jsx en el frontend
STRONG_PASSWORD = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&._\-#^()+=])[A-Za-z\d@$!%*?&._\-#^()+=]{8,}$")


def validate_strong_password(value):
    if not STRONG_PASSWORD.match(value or ""):
        raise serializers.ValidationError(
            "La contraseña debe tener al menos 8 caracteres, una mayúscula, "
            "una minúscula, un número y un carácter especial."
        )
    try:
        django_validate(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return value
