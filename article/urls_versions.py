"""Rutas SCRUM-30/31. Se montan en config/urls.py bajo `api/articles/`."""
from django.urls import path

from .versions_views import (
    ArticleAvalPresentationView,
    ArticleAvalPublicationView,
    ArticleCorrectedVersionView,
    ArticleFinalSubmissionView,
)

urlpatterns = [
    path("<int:pk>/corrected-version/", ArticleCorrectedVersionView.as_view(), name="corrected-version"),
    path("<int:pk>/aval-presentation/", ArticleAvalPresentationView.as_view(), name="aval-presentation"),
    path("<int:pk>/final-submission/", ArticleFinalSubmissionView.as_view(), name="final-submission"),
    path("<int:pk>/aval-publication/", ArticleAvalPublicationView.as_view(), name="aval-publication"),
]
