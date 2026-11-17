from rest_framework import serializers
from .models import Article, ArticleAttached, ArticleReviewer

class ArticleAttachedSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleAttached
        fields = [
            "article_attached_id", 
            "article_attached_url", 
            "article_attached_version", 
            "article_attached_created_at"
        ]

class ArticleCorrectedVersionSerializer(serializers.ModelSerializer):
    # Traemos la última versión adjunta (el PDF corregido)
    corrected_version = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = ["article_id", "article_subject", "article_description", "corrected_version"]

    def get_corrected_version(self, obj):
        # Obtenemos la versión más reciente activa y no eliminada
        latest_attachment = obj.attachments.filter(
            article_attached_active=True, 
            article_attached_delete=False
        ).order_by("-article_attached_created_at").first()

        if latest_attachment:
            return ArticleAttachedSerializer(latest_attachment).data
        return None
    
class AvalPresentationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleReviewer
        fields = [
            "article_reviewer_id",
            "article_id",
            "status",
            "comment",
            "article_reviewer_updated_at",
            "article_reviewer_updated_by"
        ]
        read_only_fields = fields
        
class AvalInputSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    
class FinalSubmissionSerializer(serializers.Serializer):
    final_pdf = serializers.FileField()
    copyright_pdf = serializers.FileField()

    def validate_final_pdf(self, value):
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError("El archivo final debe ser un PDF.")
        if value.size > 10 * 1024 * 1024:  # 10 MB
            raise serializers.ValidationError("El archivo final no debe superar los 10MB.")
        return value

    def validate_copyright_pdf(self, value):
        valid_extensions = ('.pdf', '.jpg', '.jpeg', '.png')
        if not value.name.lower().endswith(valid_extensions):
            raise serializers.ValidationError("El copyright debe ser un PDF o una imagen (JPG/PNG).")
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("El copyright no debe superar los 10MB.")
        return value