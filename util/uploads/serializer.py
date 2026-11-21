import os
from rest_framework import serializers

ALLOWED = {
    '.pdf': 'application/pdf',
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

MAX_SIZE = 20 * 1024 * 1024

class SignUploadSerializer(serializers.Serializer):
    # Solo letras, números, _ y -, separados por "/". Bloquea "..", "/" inicial, etc.
    folder = serializers.RegexField(r"^[\w-]+(/[\w-]+)*$", max_length=100)
    filename = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1, max_value=MAX_SIZE)

    def validate_filename(self, value):
        if os.path.splitext(value)[1].lower() not in ALLOWED:
            raise serializers.ValidationError("Tipo de archivo no permitido")
        return value

    def validate(self, attrs):
        ext = os.path.splitext(attrs["filename"])[1].lower()
        attrs["content_type"] = ALLOWED[ext]
        return attrs