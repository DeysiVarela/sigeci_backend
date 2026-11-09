from django.urls import re_path
from .views import (
    list_articles,
    create_article,
    detail_article,
    update_article,
    delete_article,
)

urlpatterns = [
    re_path(r"^article/?$", list_articles, name='article-list'),
    re_path(r"^article/create/?$", create_article, name='article-create'),
    re_path(r"^article/(?P<article_id>\d+)/?$", detail_article, name='article-detail'),
    re_path(r"^article/(?P<article_id>\d+)/update/?$", update_article, name='article-update'),
    re_path(r"^article/(?P<article_id>\d+)/delete/?$", delete_article, name='article-delete'),
]
