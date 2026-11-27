from django.urls import re_path

from .views import (
    MyPasswordView,
    MyProfileView,
    ProfileListView,
    UserDetailView,
    UserListCreateView,
)

urlpatterns = [
    re_path(r"^profiles/?$", ProfileListView.as_view(), name="profile-list"),
    re_path(r"^users/me/?$", MyProfileView.as_view(), name="user-me"),
    re_path(r"^users/me/password/?$", MyPasswordView.as_view(), name="user-me-password"),
    re_path(r"^users/?$", UserListCreateView.as_view(), name="user-list"),
    re_path(r"^users/(?P<user_id>\d+)/?$", UserDetailView.as_view(), name="user-detail"),
]
