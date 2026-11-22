from django.urls import path, re_path
from .views import (
    list_articles,
    list_topics,
    create_article,
    detail_article,
    update_article,
    delete_article,
    ArticleByTopicListView,
    ArticleReorderView,
)

urlpatterns = [
    re_path(r"^topic/?$", list_topics, name='topic-list'),
    re_path(r"^article/?$", list_articles, name='article-list'),
    re_path(r"^article/create/?$", create_article, name='article-create'),
    re_path(r"^article/(?P<article_id>\d+)/?$", detail_article, name='article-detail'),
    re_path(r"^article/(?P<article_id>\d+)/update/?$", update_article, name='article-update'),
    re_path(r"^article/(?P<article_id>\d+)/delete/?$", delete_article, name='article-delete'),

    # Rutas SCRUM-176 (Artículos por tópico y reordenamiento)
    re_path(r"^article/topics/(?P<topic_id>\d+)/articles/?$", ArticleByTopicListView.as_view(), name='articles-by-topic'),
    re_path(r"^article/reorder/?$", ArticleReorderView.as_view(), name='article-reorder'),
]