from rest_framework import serializers
from .models import Article, ArticleAttached, ArticleReviewer

class ArticleAttachedSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleAttached
        fields = ["article_attached_id", "article_attached_url", "article_attached_version", "article_attached_created_at"]

class ArticleCorrectedVersionSerializer(serializers.ModelSerializer):
    corrected_version = serializers.SerializerMethodField()
    class Meta:
        model = Article
        fields = ["article_id", "article_subject", "article_description", "corrected_version"]

    def get_corrected_version(self, obj):
        latest = obj.attachments.filter(article_attached_active=True, article_attached_delete=False).order_by("-article_attached_created_at").first()
        if latest:
            return ArticleAttachedSerializer(latest).data
        return None

class AvalInputSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)

class CorrectedVersionUploadSerializer(serializers.Serializer):
    corrected_pdf = serializers.FileField()

class FinalSubmissionSerializer(serializers.Serializer):
    final_pdf = serializers.FileField()
    copyright_pdf = serializers.FileField()

class ArticleReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )