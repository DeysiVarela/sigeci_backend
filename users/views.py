import uuid
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from util.auth_service import SigeciAPIView, require_permission_drf
from util.utilDB import queryDB

from .models import Profile, User
from .validators import validate_strong_password

ADMIN_PROFILE = "ADMIN"


def _is_admin(user_id):
    rows = queryDB(
        """
        select 1
        from user_profiles up
        inner join profile p
            on p.profile_id = up.profile_id
            and p.profile_active = true
            and p.profile_delete = false
        where up.user_id = %s
          and p.profile_name = %s
        limit 1
        """,
        [user_id, ADMIN_PROFILE],
    )
    return bool(rows)


def _is_last_admin(user_id):
    if not _is_admin(user_id):
        return False
    rows = queryDB(
        """
        select 1
        from users u
        inner join user_profiles up on up.user_id = u.user_id
        inner join profile p on p.profile_id = up.profile_id
        where p.profile_name = %s
          and u.user_active = true
          and u.user_delete = false
          and u.user_id <> %s
        limit 1
        """,
        [ADMIN_PROFILE, user_id],
    )
    return not bool(rows)


def _attach_profiles(users_list):
    if not users_list:
        return users_list

    user_ids = [u["user_id"] for u in users_list]
    placeholders = ",".join(["%s"] * len(user_ids))
    profile_rows = queryDB(
        f"""
        select
            up.user_id,
            p.profile_id,
            p.profile_name
        from user_profiles up
        inner join profile p
            on p.profile_id = up.profile_id
            and p.profile_active = true
            and p.profile_delete = false
        where up.user_id in ({placeholders})
        order by p.profile_id asc
        """,
        user_ids,
    )

    by_user = {}
    for row in profile_rows:
        by_user.setdefault(row["user_id"], []).append({
            "profile_id": row["profile_id"],
            "profile_name": row["profile_name"],
        })

    for u in users_list:
        user_profiles = by_user.get(u["user_id"], [])
        u["profiles"] = user_profiles
        u["profiles_names"] = ", ".join(p["profile_name"] for p in user_profiles)

    return users_list


def _fetch_user_by_id(user_id):
    rows = queryDB(
        """
        select
            u.user_id,
            u.user_name,
            u.user_lastname,
            u.user_email,
            u.user_provider,
            u.user_active,
            u.user_created_at,
            u.user_updated_at
        from users u
        where u.user_id = %s
          and u.user_delete = false
        limit 1
        """,
        [user_id],
    )
    if not rows:
        return None
    return _attach_profiles(rows)[0]


def _extract_validation_message(exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, list) and detail:
        return str(detail[0])
    return str(exc)


class ProfileListView(SigeciAPIView):
    """GET /api/v1/profiles/ — Lista los perfiles activos del sistema."""

    @require_permission_drf(endpoint="users", action="view")
    def get(self, request):
        profiles = queryDB(
            """
            select
                profile_id,
                profile_name
            from profile
            where profile_active = true
              and profile_delete = false
            order by profile_id asc
            """,
            None,
        )
        return Response({
            "success": True,
            "message": "Perfiles obtenidos con éxito.",
            "data": profiles,
        }, status=status.HTTP_200_OK)


class UserListCreateView(SigeciAPIView):
    """
    GET  /api/v1/users/
    POST /api/v1/users/
    """

    @require_permission_drf(endpoint="users", action="view")
    def get(self, request):
        where_clauses = ["u.user_delete = false"]
        params = []

        profile_filter = request.query_params.get("profile")
        active_filter = request.query_params.get("active")

        if profile_filter not in (None, ""):
            if not str(profile_filter).isdigit():
                return Response({
                    "success": False,
                    "message": "El filtro de perfil debe ser numérico.",
                }, status=status.HTTP_400_BAD_REQUEST)
            where_clauses.append(
                "exists (select 1 from user_profiles upf where upf.user_id = u.user_id and upf.profile_id = %s)"
            )
            params.append(int(profile_filter))

        if active_filter not in (None, ""):
            val = str(active_filter).lower()
            if val not in ("true", "false"):
                return Response({
                    "success": False,
                    "message": "El filtro de estado debe ser true o false.",
                }, status=status.HTTP_400_BAD_REQUEST)
            where_clauses.append("u.user_active = %s")
            params.append(val == "true")

        where_sql = " and ".join(where_clauses)
        users = queryDB(
            f"""
            select
                u.user_id,
                u.user_name,
                u.user_lastname,
                u.user_email,
                u.user_provider,
                u.user_active,
                u.user_created_at,
                u.user_updated_at
            from users u
            where {where_sql}
            order by u.user_id desc
            """,
            params if params else None,
        )
        _attach_profiles(users)

        return Response({
            "success": True,
            "message": "Usuarios obtenidos con éxito.",
            "data": users,
        }, status=status.HTTP_200_OK)

    @require_permission_drf(endpoint="users", action="create")
    def post(self, request):
        actor_id = request.user.get("user_id")
        data = request.data

        user_name = (data.get("user_name") or "").strip()
        user_lastname = (data.get("user_lastname") or "").strip()
        user_email = (data.get("user_email") or "").strip().lower()
        user_password = data.get("user_password") or ""
        profile_ids = data.get("profiles") or []

        if not user_name or not user_lastname or not user_email or not user_password:
            return Response({
                "success": False,
                "message": "Nombre, apellido, correo y contraseña son obligatorios.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(profile_ids, list) or len(profile_ids) == 0:
            return Response({
                "success": False,
                "message": "Debes asignar al menos un perfil al usuario.",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_strong_password(user_password)
        except DRFValidationError as exc:
            return Response({
                "success": False,
                "message": _extract_validation_message(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(user_email__iexact=user_email).exists():
            return Response({
                "success": False,
                "message": "Ya existe un usuario registrado con este correo.",
            }, status=status.HTTP_400_BAD_REQUEST)

        profiles_qs = list(Profile.objects.filter(
            profile_id__in=profile_ids, profile_active=True, profile_delete=False
        ))
        if len(profiles_qs) != len(set(profile_ids)):
            return Response({
                "success": False,
                "message": "Uno o más perfiles seleccionados no son válidos.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if any(p.profile_name == ADMIN_PROFILE for p in profiles_qs) and not _is_admin(actor_id):
            return Response({
                "success": False,
                "message": "Solo un administrador puede asignar el perfil de administrador.",
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            with transaction.atomic():
                new_user = User(
                    user_name=user_name,
                    user_lastname=user_lastname,
                    user_email=user_email,
                    user_provider=User.PROVIDER_ACCOUNT,
                    user_seed_token=str(uuid.uuid4()),
                    user_created_by_id=actor_id,
                    user_updated_by_id=actor_id,
                )
                new_user.set_password(user_password)
                new_user.save()
                new_user.profiles.set(profiles_qs)
        except IntegrityError:
            return Response({
                "success": False,
                "message": "Ya existe un usuario registrado con este correo.",
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "Usuario creado con éxito.",
            "data": _fetch_user_by_id(new_user.user_id),
        }, status=status.HTTP_201_CREATED)


class UserDetailView(SigeciAPIView):
    """
    GET    /api/v1/users/<user_id>/
    PUT    /api/v1/users/<user_id>/
    PATCH  /api/v1/users/<user_id>/
    DELETE /api/v1/users/<user_id>/
    """

    @require_permission_drf(endpoint="users", action="view")
    def get(self, request, user_id):
        user_data = _fetch_user_by_id(user_id)
        if not user_data:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "success": True,
            "message": "Usuario obtenido con éxito.",
            "data": user_data,
        }, status=status.HTTP_200_OK)

    def _update(self, request, user_id):
        actor_id = request.user.get("user_id")
        target = User.objects.prefetch_related("profiles").filter(
            pk=user_id, user_delete=False
        ).first()
        if target is None:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)

        if _is_admin(target.user_id) and not _is_admin(actor_id):
            return Response({
                "success": False,
                "message": "Solo un administrador puede modificar cuentas de administradores.",
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        if "user_name" in data:
            val = (data.get("user_name") or "").strip()
            if not val:
                return Response({"success": False, "message": "El nombre es obligatorio."}, status=400)
            target.user_name = val

        if "user_lastname" in data:
            val = (data.get("user_lastname") or "").strip()
            if not val:
                return Response({"success": False, "message": "El apellido es obligatorio."}, status=400)
            target.user_lastname = val

        if "user_email" in data:
            val = (data.get("user_email") or "").strip().lower()
            if not val:
                return Response({"success": False, "message": "El correo es obligatorio."}, status=400)
            if User.objects.filter(user_email__iexact=val).exclude(pk=target.user_id).exists():
                return Response({
                    "success": False,
                    "message": "Ya existe un usuario registrado con este correo.",
                }, status=status.HTTP_400_BAD_REQUEST)
            target.user_email = val

        if "user_active" in data:
            new_active = bool(data.get("user_active"))
            if not new_active:
                if int(actor_id) == int(target.user_id):
                    return Response({
                        "success": False,
                        "message": "No puedes desactivar tu propia cuenta.",
                    }, status=status.HTTP_400_BAD_REQUEST)
                if _is_last_admin(target.user_id):
                    return Response({
                        "success": False,
                        "message": "No se puede desactivar al único administrador activo.",
                    }, status=status.HTTP_400_BAD_REQUEST)
            target.user_active = new_active

        profiles_to_set = None
        if "profiles" in data:
            profile_ids = data.get("profiles") or []
            if not isinstance(profile_ids, list) or len(profile_ids) == 0:
                return Response({
                    "success": False,
                    "message": "Debes asignar al menos un perfil.",
                }, status=status.HTTP_400_BAD_REQUEST)

            profiles_qs = list(Profile.objects.filter(
                profile_id__in=profile_ids, profile_active=True, profile_delete=False
            ))
            if len(profiles_qs) != len(set(profile_ids)):
                return Response({
                    "success": False,
                    "message": "Uno o más perfiles seleccionados no son válidos.",
                }, status=status.HTTP_400_BAD_REQUEST)

            new_pks = {p.profile_id for p in profiles_qs}
            old_pks = {p.profile_id for p in target.profiles.all()}
            if new_pks != old_pks:
                if int(actor_id) == int(target.user_id):
                    return Response({
                        "success": False,
                        "message": "No puedes cambiar tus propios perfiles.",
                    }, status=status.HTTP_400_BAD_REQUEST)
                if any(p.profile_name == ADMIN_PROFILE for p in profiles_qs) and not _is_admin(actor_id):
                    return Response({
                        "success": False,
                        "message": "Solo un administrador puede asignar el perfil de administrador.",
                    }, status=status.HTTP_403_FORBIDDEN)
                if _is_last_admin(target.user_id) and not any(p.profile_name == ADMIN_PROFILE for p in profiles_qs):
                    return Response({
                        "success": False,
                        "message": "No se puede quitar el perfil de administrador al único administrador activo.",
                    }, status=status.HTTP_400_BAD_REQUEST)
                profiles_to_set = profiles_qs

        target.user_updated_by_id = actor_id
        target.user_updated_at = timezone.now()

        with transaction.atomic():
            target.save()
            if profiles_to_set is not None:
                target.profiles.set(profiles_to_set)

        return Response({
            "success": True,
            "message": "Usuario actualizado con éxito.",
            "data": _fetch_user_by_id(target.user_id),
        }, status=status.HTTP_200_OK)

    @require_permission_drf(endpoint="users", action="update")
    def patch(self, request, user_id):
        return self._update(request, user_id)

    @require_permission_drf(endpoint="users", action="update")
    def put(self, request, user_id):
        return self._update(request, user_id)

    @require_permission_drf(endpoint="users", action="delete")
    def delete(self, request, user_id):
        actor_id = request.user.get("user_id")
        target = User.objects.filter(pk=user_id, user_delete=False).first()
        if target is None:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)

        if _is_admin(target.user_id) and not _is_admin(actor_id):
            return Response({
                "success": False,
                "message": "Solo un administrador puede eliminar cuentas de administradores.",
            }, status=status.HTTP_403_FORBIDDEN)

        if int(actor_id) == int(target.user_id):
            return Response({
                "success": False,
                "message": "No puedes eliminar tu propia cuenta.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if _is_last_admin(target.user_id):
            return Response({
                "success": False,
                "message": "No se puede eliminar al único administrador activo.",
            }, status=status.HTTP_400_BAD_REQUEST)

        target.user_delete = True
        target.user_active = False
        target.user_updated_by_id = actor_id
        target.user_updated_at = timezone.now()
        target.save(update_fields=["user_delete", "user_active", "user_updated_by", "user_updated_at"])

        return Response({
            "success": True,
            "message": "Usuario eliminado con éxito.",
            "data": None,
        }, status=status.HTTP_200_OK)


class MyProfileView(SigeciAPIView):
    """
    GET   /api/v1/users/me
    PATCH /api/v1/users/me
    """

    @require_permission_drf(endpoint="me", action="view")
    def get(self, request):
        user_data = _fetch_user_by_id(request.user.get("user_id"))
        if not user_data:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "success": True,
            "message": "Perfil obtenido con éxito.",
            "data": user_data,
        }, status=status.HTTP_200_OK)

    @require_permission_drf(endpoint="me", action="view")
    def patch(self, request):
        user_id = request.user.get("user_id")
        user = User.objects.filter(pk=user_id, user_active=True, user_delete=False).first()
        if user is None:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        user_name = (data.get("user_name") or "").strip()
        user_lastname = (data.get("user_lastname") or "").strip()
        user_email = (data.get("user_email") or "").strip().lower()

        if not user_name or not user_lastname or not user_email:
            return Response({
                "success": False,
                "message": "Nombre, apellido y correo son obligatorios.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(user_email__iexact=user_email).exclude(pk=user.user_id).exists():
            return Response({
                "success": False,
                "message": "Ya existe un usuario registrado con este correo.",
            }, status=status.HTTP_400_BAD_REQUEST)

        user.user_name = user_name
        user.user_lastname = user_lastname
        user.user_email = user_email
        user.user_updated_by_id = user.user_id
        user.user_updated_at = timezone.now()
        user.save(update_fields=["user_name", "user_lastname", "user_email", "user_updated_by", "user_updated_at"])

        return Response({
            "success": True,
            "message": "Perfil actualizado con éxito.",
            "data": _fetch_user_by_id(user.user_id),
        }, status=status.HTTP_200_OK)


class MyPasswordView(SigeciAPIView):
    """PUT /api/v1/users/me/password/ — Cambio de contraseña del usuario en sesión."""

    @require_permission_drf(endpoint="me", action="view")
    def put(self, request):
        user_id = request.user.get("user_id")
        user = User.objects.filter(pk=user_id, user_active=True, user_delete=False).first()
        if user is None:
            return Response({
                "success": False,
                "message": "Usuario no encontrado.",
            }, status=status.HTTP_404_NOT_FOUND)

        if user.user_provider != User.PROVIDER_ACCOUNT:
            return Response({
                "success": False,
                "message": "Tu cuenta no usa una contraseña propia.",
            }, status=status.HTTP_400_BAD_REQUEST)

        current_password = request.data.get("current_password") or ""
        new_password = request.data.get("new_password") or ""

        if not current_password or not new_password:
            return Response({
                "success": False,
                "message": "Debes ingresar la contraseña actual y la nueva contraseña.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(current_password):
            return Response({
                "success": False,
                "message": "La contraseña actual no es correcta.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if current_password == new_password:
            return Response({
                "success": False,
                "message": "La nueva contraseña debe ser diferente a la actual.",
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_strong_password(new_password)
        except DRFValidationError as exc:
            return Response({
                "success": False,
                "message": _extract_validation_message(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.user_updated_by_id = user.user_id
        user.user_updated_at = timezone.now()
        with transaction.atomic():
            user.save(update_fields=["user_password", "user_updated_by", "user_updated_at"])
            user.reset_pins.filter(used_at__isnull=True).update(used_at=timezone.now())

        return Response({
            "success": True,
            "message": "Contraseña actualizada con éxito.",
            "data": None,
        }, status=status.HTTP_200_OK)
