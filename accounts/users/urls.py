from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

# Las rutas /users/me van ANTES del router: si no, "me" se tomaría como el id de un usuario.
urlpatterns = [
    path("profiles/", views.ProfileListView.as_view()),
    re_path(r"^users/me/?$", views.MyProfileView.as_view()),  # /api/users/me y /api/users/me/
    re_path(r"^users/me/password/?$", views.MyPasswordView.as_view()),  # /api/users/me/password/
] + router.urls
