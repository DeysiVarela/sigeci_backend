from django.urls import path
from . import views

urlpatterns = [
    path('<int:pk>/corrected-version/', views.ArticleCorrectedVersionView.as_view(), name='article-corrected-version'),
    path('<int:pk>/aval-presentation/', views.ArticleAvalPresentationView.as_view(), name='article-aval-presentation'),
]