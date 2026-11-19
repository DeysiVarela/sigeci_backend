from django.urls import path
from .views import (
    ArticleCorrectedVersionView, 
    ArticleAvalPresentationView,
    ArticleFinalSubmissionView, 
    ArticleAvalPublicationView  
)

urlpatterns = [
    path('<int:pk>/corrected-version/', ArticleCorrectedVersionView.as_view(), name='corrected-version'),
    path('<int:pk>/aval-presentation/', ArticleAvalPresentationView.as_view(), name='aval-presentation'),
    path('<int:pk>/final-submission/', ArticleFinalSubmissionView.as_view(), name='final-submission'),
    path('<int:pk>/aval-publication/', ArticleAvalPublicationView.as_view(), name='aval-publication'),
]