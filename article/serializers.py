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