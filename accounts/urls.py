from django.urls import include, path, re_path

from . import views

urlpatterns = [
    re_path(r"^auth/login/?$", views.LoginView.as_view()),  # /api/auth/login y /api/auth/login/
    path("auth/refresh/", views.RefreshView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("auth/password/forgot/", views.ForgotPasswordView.as_view()),
    path("auth/password/reset/", views.ResetPasswordView.as_view()),
    path("", include("accounts.users.urls")),  # /api/users/ y /api/profiles/
]
