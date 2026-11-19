from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from ..models import Profile, User
from ..validators import validate_strong_password


ADMIN_PROFILE = "ADMIN"


def is_admin(user):
    """True si `user` tiene el rol administrador (en su lista de roles)."""
    return user.profiles.filter(profile_name=ADMIN_PROFILE).exists()


def is_last_admin(user):
    """True si `user` es el único ADMIN activo del sistema."""
    if not is_admin(user):
        return False
    return not (
        User.objects.filter(profiles__profile_name="ADMIN", user_active=True, user_delete=False)
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
    user_seed_token = serializers.CharField(read_only=True)    
    
    # CAMBIO: Ahora devuelve un arreglo de perfiles
    profiles = ProfileSerializer(many=True, read_only=True) 
    
    created_at = serializers.DateTimeField(source="user_created_at", read_only=True)
    updated_at = serializers.DateTimeField(source="user_updated_at", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "name", "lastname", "email", "provider",
            "profiles", "user_seed_token", "active", "created_at", "updated_at",
        ]


# --------------------------------------------------------------------------- #
# Escritura (crear / actualizar)
# --------------------------------------------------------------------------- #
class _UserWriteBase(serializers.ModelSerializer):
    name = serializers.CharField(source="user_name", max_length=60)
    lastname = serializers.CharField(source="user_lastname", max_length=60)
    email = serializers.EmailField(source="user_email", max_length=120)
    
    # CAMBIO: Ahora acepta un arreglo de IDs (many=True)
    profiles = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.filter(profile_active=True, profile_delete=False),
        many=True
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

    def validate_profiles(self, value):
        # value es una lista de objetos Profile
        if not value:
            raise serializers.ValidationError("Debes asignar al menos un rol.")
            
        # Solo un administrador puede asignar el rol administrador
        has_admin_role = any(p.profile_name == ADMIN_PROFILE for p in value)
        if has_admin_role and not is_admin(self.actor):
            raise PermissionDenied("Solo un administrador puede asignar el rol de administrador.")
        return value

    @property
    def actor(self):
        return self.context["request"].user


class UserCreateSerializer(_UserWriteBase):
    password = serializers.CharField(write_only=True, validators=[validate_strong_password])

    class Meta:
        model = User
        fields = ["name", "lastname", "email", "password", "profiles", "active"]

    @transaction.atomic
    def create(self, validated_data):
        profiles = validated_data.pop("profiles") # Extraemos los roles
        password = validated_data.pop("password")
        
        user = User(**validated_data)
        user.user_provider = User.PROVIDER_ACCOUNT
        user.user_created_by = self.actor
        user.user_updated_by = self.actor
        user.set_password(password)
        user.save()
        
        user.profiles.set(profiles) # Asignamos los roles ManyToMany
        return user


class UserUpdateSerializer(_UserWriteBase):
    class Meta:
        model = User
        fields = ["name", "lastname", "email", "profiles", "active"]

    def validate(self, attrs):
        user = self.instance
        actor = self.actor

        # Regla de oro: Quien no es administrador no puede modificar cuentas de administradores.
        if is_admin(user) and not is_admin(actor):
            raise PermissionDenied("Solo un administrador puede modificar o eliminar cuentas de administradores.")

        new_profiles = attrs.get("profiles")
        if new_profiles is not None:
            # Comparamos si la lista de roles cambió
            new_pks = {p.pk for p in new_profiles}
            old_pks = {p.pk for p in user.profiles.all()}
            
            if new_pks != old_pks:
                if not actor.has_perm_on("user_role", "update"):
                    raise PermissionDenied("No tienes autorización para modificar roles.")
                if actor.pk == user.pk:
                    raise serializers.ValidationError({"profiles": "No puedes cambiar tus propios roles."})
                
                # Si el usuario era el último admin, y en la nueva lista de roles ya no está ADMIN
                if is_last_admin(user) and not any(p.profile_name == ADMIN_PROFILE for p in new_profiles):
                    raise serializers.ValidationError(
                        {"profiles": "No se puede quitar el rol de administrador al único administrador activo."}
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
        profiles = validated_data.pop("profiles", None)
        
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.user_updated_by = self.actor
        instance.save()
        
        if profiles is not None:
            instance.profiles.set(profiles) # Actualizamos los roles ManyToMany
            
        return instance


# --------------------------------------------------------------------------- #
# SCRUM-125: mi perfil (solo el usuario de la sesión)
# --------------------------------------------------------------------------- #
class MyProfileUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user_name", max_length=60)
    lastname = serializers.CharField(source="user_lastname", max_length=60)
    email = serializers.EmailField(source="user_email", max_length=120)

    class Meta:
        model = User
        fields = ["name", "lastname", "email"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo es obligatorio.")
        return value

    validate_lastname = validate_name

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(user_email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return value

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.user_updated_by = instance
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(write_only=True, trim_whitespace=False)
    newPassword = serializers.CharField(write_only=True, trim_whitespace=False, validators=[validate_strong_password])

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["currentPassword"]):
            raise serializers.ValidationError({"currentPassword": "La contraseña actual no es correcta."})
        if attrs["currentPassword"] == attrs["newPassword"]:
            raise serializers.ValidationError({"newPassword": "La nueva contraseña debe ser diferente a la actual."})
        return attrs