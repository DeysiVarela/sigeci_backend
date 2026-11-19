from django.urls import re_path
from .views import (
    sign_url
)

urlpatterns = [
    re_path(r"^uploads/sign/?$", sign_url, name='upload-sign')
]
