from django.urls import path
from . import views

urlpatterns = [
    # Ruta para el Drag & Drop (SCRUM-176)
    path('topics/<int:topic_id>/articles/', views.ArticleByTopicListView.as_view(), name='articles-by-topic'),
    path('reorder/', views.ArticleReorderView.as_view(), name='article-reorder'),
    
    # Rutas SCRUM-30
    path('<int:pk>/corrected-version/', views.ArticleCorrectedVersionView.as_view(), name='article-corrected-version'),
    path('<int:pk>/aval-presentation/', views.ArticleAvalPresentationView.as_view(), name='article-aval-presentation'),
    
    # Rutas SCRUM-31
    path('<int:pk>/final-submission/', views.ArticleFinalSubmissionView.as_view(), name='article-final-submission'),
    path('<int:pk>/aval-publication/', views.ArticleAvalPublicationView.as_view(), name='article-aval-publication'),
]