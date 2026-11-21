from django.urls import re_path
from .views import (
    login,
    me,
    refresh_token,
    forgot_password,
    reset_password,
)

urlpatterns = [
    re_path(r"^auth/login/?$", login, name="login_v1"),
    re_path(r"^auth/me/?$", me, name="me_v1"),
    re_path(r"^auth/refresh/?$", refresh_token, name="refresh_v1"),
    re_path(r"^auth/refresh-token/?$", refresh_token, name="refresh_token_v1"),
    re_path(r"^auth/password/forgot/?$", forgot_password, name="forgot_password_v1"),
    re_path(r"^auth/password/reset/?$", reset_password, name="reset_password_v1"),
]