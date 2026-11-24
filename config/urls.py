from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'ok'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health', health),
    path('api/', include('accounts.urls')),
    # Versionamiento oficial de origin/main
    path("api/v1/health", health),
    path('api/v1/', include('Login.urls')),
    path('api/v1/', include('dashboard.urls')),
    path('api/v1/', include('article.urls')),
    path('api/', include('article.urls')),
    path('api/v1/', include('uploads.urls')),
]
