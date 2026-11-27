"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'OK'})

urlpatterns = [
    path('admin/', admin.site.urls),
    # Versionamiento
    path("api/v1/health", health),
    path('api/v1/', include('Login.urls')),
    path('api/v1/', include('users.urls')),
    path('api/v1/', include('dashboard.urls')),
    path('api/v1/', include('article.urls')),
    path('api/v1/', include('uploads.urls')),
]
