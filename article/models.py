from django.db import models


class Topic(models.Model):
    topic_id = models.AutoField(primary_key=True)
    topic_subject = models.CharField(max_length=150)
    topic_description = models.TextField(blank=True, null=True)
    topic_active = models.BooleanField(default=True)
    topic_delete = models.BooleanField(default=False)

    # Campos de auditoría
    topic_created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="topic_created_by",
        related_name="+",
    )
    topic_created_at = models.DateTimeField(auto_now_add=True)
    topic_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="topic_updated_by",
        related_name="+",
    )
    topic_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "topic"

    def __str__(self):
        return f"{self.topic_id}: {self.topic_subject}"

    def to_dict(self):
        return {
            "topic_id": self.topic_id,
            "topic_subject": self.topic_subject,
            "topic_description": self.topic_description,
            "topic_active": self.topic_active,
            "topic_delete": self.topic_delete,
            "topic_created_by": self.topic_created_by_id,
            "topic_created_at": self.topic_created_at.isoformat() if self.topic_created_at else None,
            "topic_updated_by": self.topic_updated_by_id,
            "topic_updated_at": self.topic_updated_at.isoformat() if self.topic_updated_at else None,
        }


class Article(models.Model):
    article_id = models.AutoField(primary_key=True)
    article_subject = models.CharField(max_length=255)
    article_description = models.TextField(blank=True, default="")
    topic_id = models.ForeignKey(
        Topic,
        on_delete=models.RESTRICT,
        db_column="topic_id",
        related_name="articles"
    )
    article = models.TextField()
    article_date = models.DateField(null=True, blank=True)
    article_copyright_url = models.URLField(blank=True, null=True)
    article_active = models.BooleanField(default=True)
    article_delete = models.BooleanField(default=False)

    # Campos de auditoría
    article_created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_created_by",
        related_name="+",
    )
    article_created_at = models.DateTimeField(auto_now_add=True)
    article_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_updated_by",
        related_name="+",
    )
    article_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "article"
        ordering = ["-article_id"]

    def __str__(self):
        return f"{self.article_id}: {self.article_subject}"

    def to_dict(self):
        return {
            "article_id": self.article_id,
            "article_subject": self.article_subject,
            "article_description": self.article_description,
            "topic_id": self.topic_id_id,
            "article": self.article,
            "article_date": str(self.article_date) if self.article_date else None,
            "article_copyright_url": self.article_copyright_url,
            "article_active": self.article_active,
            "article_delete": self.article_delete,
            "article_created_by": self.article_created_by_id,
            "article_created_at": self.article_created_at.isoformat() if self.article_created_at else None,
            "article_updated_by": self.article_updated_by_id,
            "article_updated_at": self.article_updated_at.isoformat() if self.article_updated_at else None,
        }


class ArticleAttached(models.Model):
    article_attached_id = models.AutoField(primary_key=True)
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        db_column="article_id",
        related_name="attachments"
    )
    article_attached_url = models.TextField()
    article_attached_version = models.CharField(max_length=20, default="1.0")
    article_attached_active = models.BooleanField(default=True)
    article_attached_delete = models.BooleanField(default=False)

    # Campos de auditoría
    article_attached_created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_attached_created_by",
        related_name="+",
    )
    article_attached_created_at = models.DateTimeField(auto_now_add=True)
    article_attached_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_attached_updated_by",
        related_name="+",
    )
    article_attached_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "article_attached"
        ordering = ["-article_attached_id"]

    def __str__(self):
        return f"Attached {self.article_attached_id} v{self.article_attached_version} (Article {self.article_id})"

    def to_dict(self):
        return {
            "article_attached_id": self.article_attached_id,
            "article_id": self.article_id,
            "article_attached_url": self.article_attached_url,
            "article_attached_version": self.article_attached_version,
            "article_attached_active": self.article_attached_active,
            "article_attached_delete": self.article_attached_delete,
            "article_attached_created_by": self.article_attached_created_by_id,
            "article_attached_created_at": self.article_attached_created_at.isoformat() if self.article_attached_created_at else None,
            "article_attached_updated_by": self.article_attached_updated_by_id,
            "article_attached_updated_at": self.article_attached_updated_at.isoformat() if self.article_attached_updated_at else None,
        }


class ArticleReviewer(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("IN_REVIEW", "In Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("FOR_PRESENTATION", "For Presentation"),
        ("FOR_PUBLICATION", "For Publication")
    )

    article_reviewer_id = models.AutoField(primary_key=True)
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        db_column="article_id",
        related_name="reviewers"
    )
    article_attached = models.ForeignKey(
        ArticleAttached,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_attached_id",
        related_name="reviews"
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="article_assignments"
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="IN_REVIEW")
    comment = models.TextField(blank=True, null=True)
    article_reviewer_active = models.BooleanField(default=True)
    article_reviewer_delete = models.BooleanField(default=False)

    # Campos de auditoría
    article_reviewer_created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_reviewer_created_by",
        related_name="+",
    )
    article_reviewer_created_at = models.DateTimeField(auto_now_add=True)
    article_reviewer_updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="article_reviewer_updated_by",
        related_name="+",
    )
    article_reviewer_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "article_reviewer"
        ordering = ["-article_reviewer_id"]

    def __str__(self):
        return f"Reviewer {self.article_reviewer_id} - User {self.user_id} on Article {self.article_id} ({self.status})"

    def to_dict(self):
        return {
            "article_reviewer_id": self.article_reviewer_id,
            "article_id": self.article_id,
            "article_attached_id": self.article_attached_id,
            "user_id": self.user_id,
            "status": self.status,
            "comment": self.comment,
            "article_reviewer_active": self.article_reviewer_active,
            "article_reviewer_delete": self.article_reviewer_delete,
            "article_reviewer_created_by": self.article_reviewer_created_by_id,
            "article_reviewer_created_at": self.article_reviewer_created_at.isoformat() if self.article_reviewer_created_at else None,
            "article_reviewer_updated_by": self.article_reviewer_updated_by_id,
            "article_reviewer_updated_at": self.article_reviewer_updated_at.isoformat() if self.article_reviewer_updated_at else None,
        }
