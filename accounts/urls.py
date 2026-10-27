from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    re_path(r"^auth/login/?$", views.LoginView.as_view()),  # /api/auth/login y /api/auth/login/
    path("auth/refresh/", views.RefreshView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("auth/password/forgot/", views.ForgotPasswordView.as_view()),
    path("auth/password/reset/", views.ResetPasswordView.as_view()),
    path("profiles/", views.ProfileListView.as_view()),
] + router.urls
