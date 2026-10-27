from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import Profile, User
from .validators import validate_strong_password


def is_last_admin(user):
    """True si `user` es el único ADMIN activo del sistema."""
    if user.profile.profile_name != "ADMIN":
        return False
    return not (
        User.objects.filter(profile__profile_name="ADMIN", user_active=True, user_delete=False)
        .exclude(pk=user.pk)
        .exists()
    )


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #
class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="profile_id", read_only=True)
    name = serializers.CharField(source="profile_name", read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    """Nunca expone contraseña, hash ni PIN."""

    id = serializers.IntegerField(source="user_id", read_only=True)
    name = serializers.CharField(source="user_name", read_only=True)
    lastname = serializers.CharField(source="user_lastname", read_only=True)
    email = serializers.CharField(source="user_email", read_only=True)
    provider = serializers.CharField(source="user_provider", read_only=True)
    active = serializers.BooleanField(source="user_active", read_only=True)
    profile = serializers.IntegerField(source="profile_id", read_only=True)
    profile_name = serializers.CharField(source="profile.profile_name", read_only=True)
    created_at = serializers.DateTimeField(source="user_created_at", read_only=True)
    updated_at = serializers.DateTimeField(source="user_updated_at", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "name", "lastname", "email", "provider",
            "profile", "profile_name", "active", "created_at", "updated_at",
        ]


# --------------------------------------------------------------------------- #
# Escritura (crear / actualizar)
# --------------------------------------------------------------------------- #
class _UserWriteBase(serializers.ModelSerializer):
    name = serializers.CharField(source="user_name", max_length=60)
    lastname = serializers.CharField(source="user_lastname", max_length=60)
    email = serializers.EmailField(source="user_email", max_length=120)
    profile = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.filter(profile_active=True, profile_delete=False)
    )
    active = serializers.BooleanField(source="user_active", required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo es obligatorio.")
        return value

    validate_lastname = validate_name

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(user_email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return value

    @property
    def actor(self):
        return self.context["request"].user


class UserCreateSerializer(_UserWriteBase):
    password = serializers.CharField(write_only=True, validators=[validate_strong_password])

    class Meta:
        model = User
        fields = ["name", "lastname", "email", "password", "profile", "active"]

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.user_provider = User.PROVIDER_ACCOUNT
        user.user_created_by = self.actor
        user.user_updated_by = self.actor
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(_UserWriteBase):
    class Meta:
        model = User
        fields = ["name", "lastname", "email", "profile", "active"]

    def validate(self, attrs):
        user = self.instance
        actor = self.actor

        new_profile = attrs.get("profile")
        if new_profile is not None and new_profile.pk != user.profile_id:
            # Cambiar el rol requiere autorización explícita
            if not actor.has_perm_on("user_role", "update"):
                raise PermissionDenied("No tienes autorización para modificar roles.")
            if actor.pk == user.pk:
                raise serializers.ValidationError({"profile": "No puedes cambiar tu propio rol."})
            if is_last_admin(user):
                raise serializers.ValidationError(
                    {"profile": "No se puede quitar el rol al único administrador activo."}
                )

        if "user_active" in attrs and attrs["user_active"] != user.user_active:
            needed = "active" if attrs["user_active"] else "inactive"
            if not actor.has_perm_on("user", needed):
                raise PermissionDenied("No tienes autorización para cambiar el estado.")
            if not attrs["user_active"]:
                if actor.pk == user.pk:
                    raise serializers.ValidationError({"active": "No puedes desactivar tu propia cuenta."})
                if is_last_admin(user):
                    raise serializers.ValidationError(
                        {"active": "No se puede desactivar al único administrador activo."}
                    )
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.user_updated_by = self.actor
        instance.save()
        return instance


# --------------------------------------------------------------------------- #
# Autenticación y recuperación
# --------------------------------------------------------------------------- #
class LoginSerializer(serializers.Serializer):
    """Contrato final: { identifier, password, captchaToken }.
    `email` se acepta como alias de `identifier` por compatibilidad."""

    identifier = serializers.CharField(required=False, max_length=120)
    email = serializers.CharField(required=False, max_length=120)
    password = serializers.CharField(trim_whitespace=False)
    captchaToken = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        identifier = (attrs.get("identifier") or attrs.get("email") or "").strip()
        if not identifier:
            raise serializers.ValidationError({"identifier": "Este campo es obligatorio."})
        attrs["identifier"] = identifier
        return attrs


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    pin = serializers.RegexField(
        r"^\d+$", min_length=settings.PASSWORD_RESET_PIN_LENGTH,
        max_length=settings.PASSWORD_RESET_PIN_LENGTH,
        error_messages={"invalid": "El PIN debe contener solo dígitos."},
    )
    password = serializers.CharField(validators=[validate_strong_password])
