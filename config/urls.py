"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # accounts va PRIMERO: /api/auth/login es el login real (usuarios en BD + JWT).
    # El login de demostración de auth_api queda en la misma ruta, por lo que no se alcanza;
    # de auth_api se sigue usando /health.
    path('api/', include('accounts.urls')),
    path('', include('auth_api.urls')),
]
