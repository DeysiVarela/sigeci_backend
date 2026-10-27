from django.urls import path

from .views import health, login

urlpatterns = [
    path('health', health, name='health'),
    path('api/auth/login', login, name='login'),
]
