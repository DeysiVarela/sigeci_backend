from django.urls import re_path
from .views import (
    list_articles,
    create_article,
    detail_article,
    update_article,
    delete_article,
    assigned_evaluations,
    assigned_evaluation_detail,
    submit_evaluation_verdict,
)

urlpatterns = [
    re_path(r"^evaluations/assigned/?$", assigned_evaluations, name="evaluation-assigned-list"),
    re_path(r"^evaluations/assigned/(?P<review_id>\d+)/?$", assigned_evaluation_detail, name="evaluation-assigned-detail"),
    re_path(r"^evaluations/assigned/(?P<review_id>\d+)/verdict/?$", submit_evaluation_verdict, name="evaluation-verdict"),
    re_path(r"^article/?$", list_articles, name='article-list'),
    re_path(r"^article/create/?$", create_article, name='article-create'),
    re_path(r"^article/(?P<article_id>\d+)/?$", detail_article, name='article-detail'),
    re_path(r"^article/(?P<article_id>\d+)/update/?$", update_article, name='article-update'),
    re_path(r"^article/(?P<article_id>\d+)/delete/?$", delete_article, name='article-delete'),
]
