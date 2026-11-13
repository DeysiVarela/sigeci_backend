from django.urls import re_path
from .views import get_metrics

urlpatterns = [
    re_path(r"^dashboard/?$", get_metrics, name='dashboard'),
]