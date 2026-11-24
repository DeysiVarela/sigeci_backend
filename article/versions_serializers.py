import os

from rest_framework import serializers

from .models import Article, ArticleAttached, ArticleReviewer
from .versions_storage import download_url

MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Primeros bytes reales del archivo: la extensión la escribe el cliente, el contenido no se puede disfrazar igual.
PDF_MAGIC = (b"%PDF-",)
IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")


def _ext(upload):
    return os.path.splitext(upload.name or "")[1].lower()


def _has_magic(upload, magics):
    upload.seek(0)
    head = upload.read(8)
    upload.seek(0)
    return any(head.startswith(m) for m in magics)


class ArticleAttachedSerializer(serializers.ModelSerializer):
    article_attached_url = serializers.SerializerMethodField()

    class Meta:
        model = ArticleAttached
        fields = [
            "article_attached_id",
            "article_attached_url",
            "article_attached_version",
            "article_attached_created_at",
        ]

    def get_article_attached_url(self, obj):
        return download_url(obj.article_attached_url)


class ArticleVersionsSerializer(serializers.ModelSerializer):
    """GET /api/articles/{id}/corrected-version/ (CA-01): versión más reciente + historial."""

    article_copyright_url = serializers.SerializerMethodField()
    corrected_version = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "article_id",
            "article_subject",
            "article_description",
            "article_copyright_url",
            "corrected_version",
            "versions",
        ]

    def _attachments(self, obj):
        return obj.attachments.filter(
            article_attached_active=True, article_attached_delete=False
        ).order_by("-article_attached_created_at", "-article_attached_id")

    def get_article_copyright_url(self, obj):
        return download_url(obj.article_copyright_url) if obj.article_copyright_url else None

    def get_corrected_version(self, obj):
        latest = self._attachments(obj).first()
        return ArticleAttachedSerializer(latest).data if latest else None

    def get_versions(self, obj):
        return ArticleAttachedSerializer(self._attachments(obj), many=True).data


class AvalInputSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CorrectedVersionUploadSerializer(serializers.Serializer):
    """SCRUM-30: PDF de la versión corregida que sube el autor."""

    corrected_pdf = serializers.FileField()

    def validate_corrected_pdf(self, value):
        if _ext(value) != ".pdf":
            raise serializers.ValidationError("El archivo corregido debe ser un PDF.")
        if value.size == 0:
            raise serializers.ValidationError("El archivo corregido está vacío.")
        if value.size > MAX_BYTES:
            raise serializers.ValidationError("El archivo corregido no debe superar los 10MB.")
        if not _has_magic(value, PDF_MAGIC):
            raise serializers.ValidationError("El archivo corregido no es un PDF válido.")
        return value


class FinalSubmissionSerializer(serializers.Serializer):
    """SCRUM-31: versión final (PDF) + documento de copyright (PDF o imagen)."""

    final_pdf = serializers.FileField()
    copyright_pdf = serializers.FileField()

    def validate_final_pdf(self, value):
        if _ext(value) != ".pdf":
            raise serializers.ValidationError("El archivo final debe ser un PDF.")
        if value.size == 0:
            raise serializers.ValidationError("El archivo final está vacío.")
        if value.size > MAX_BYTES:
            raise serializers.ValidationError("El archivo final no debe superar los 10MB.")
        if not _has_magic(value, PDF_MAGIC):
            raise serializers.ValidationError("El archivo final no es un PDF válido.")
        return value

    def validate_copyright_pdf(self, value):
        ext = _ext(value)
        if ext not in (".pdf", ".jpg", ".jpeg", ".png"):
            raise serializers.ValidationError("El copyright debe ser un PDF o una imagen (JPG/PNG).")
        if value.size == 0:
            raise serializers.ValidationError("El copyright está vacío.")
        if value.size > MAX_BYTES:
            raise serializers.ValidationError("El copyright no debe superar los 10MB.")
        magics = PDF_MAGIC if ext == ".pdf" else IMAGE_MAGIC
        if not _has_magic(value, magics):
            raise serializers.ValidationError("El copyright no es un PDF o imagen válidos.")
        return value
