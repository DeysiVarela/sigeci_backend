"""
Modelos del módulo de usuarios, perfiles y permisos.

Los nombres de tabla y de columna siguen el ERD del equipo
(users, profile, profile_action). La tabla `password_reset_pin`
NO está en el ERD: se agrega para SCRUM-15 (recuperación con PIN).
"""
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Profile(models.Model):
    """Perfil/rol: ADMIN | MEMBER | AUTHOR."""

    profile_id = models.AutoField(primary_key=True)
    profile_name = models.CharField(max_length=60, unique=True)
    profile_active = models.BooleanField(default=True)
    profile_delete = models.BooleanField(default=False)

    class Meta:
        db_table = "profile"

    def __str__(self):
        return self.profile_name


class ProfileAction(models.Model):
    """
    Matriz de permisos: una fila por (perfil, recurso, permiso).

    action      -> article | event | application | user | user_role
    permissions -> view | create | update | delete | active | inactive | download
    """

    profile_action_id = models.AutoField(primary_key=True)
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, db_column="profile_id", related_name="actions"
    )
    profile_action_action = models.CharField(max_length=60)
    profile_action_permissions = models.CharField(max_length=60)
    profile_action_active = models.BooleanField(default=True)
    profile_action_delete = models.BooleanField(default=False)

    class Meta:
        db_table = "profile_action"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "profile_action_action", "profile_action_permissions"],
                name="uq_profile_action_permission",
            )
        ]

    def __str__(self):
        return f"{self.profile_id}:{self.profile_action_action}:{self.profile_action_permissions}"


class User(models.Model):
    """
    Usuario del sistema. No usa django.contrib.auth.User (la BD ya tiene
    las migraciones iniciales aplicadas): la contraseña se guarda con los
    hashers de Django y la sesión se maneja con JWT.
    """

    PROVIDER_ACCOUNT = "ACCOUNT"
    PROVIDER_GMAIL = "GMAIL"
    PROVIDERS = [(PROVIDER_ACCOUNT, "ACCOUNT"), (PROVIDER_GMAIL, "GMAIL")]

    user_id = models.AutoField(primary_key=True)
    user_name = models.CharField(max_length=60)
    user_lastname = models.CharField(max_length=60)
    user_password = models.TextField()
    user_email = models.CharField(max_length=120, unique=True)
    user_provider = models.CharField(max_length=60, choices=PROVIDERS, default=PROVIDER_ACCOUNT)
    profile = models.ForeignKey(
        Profile, on_delete=models.PROTECT, db_column="profile_id", related_name="users"
    )
    user_active = models.BooleanField(default=True)
    user_delete = models.BooleanField(default=False)

    # Campos de auditoría (recuadro "Definition" del ERD)
    user_created_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        db_column="user_created_by", related_name="+",
    )
    user_created_at = models.DateTimeField(auto_now_add=True)
    user_updated_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        db_column="user_updated_by", related_name="+",
    )
    user_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        ordering = ["user_id"]

    def __str__(self):
        return self.user_email

    # --- Contrato mínimo que DRF espera de request.user ---
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    # --- Contraseña ---
    def set_password(self, raw_password):
        self.user_password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.user_password)

    # --- Permisos por perfil ---
    def has_perm_on(self, action, permission):
        return ProfileAction.objects.filter(
            profile_id=self.profile_id,
            profile__profile_active=True,
            profile__profile_delete=False,
            profile_action_active=True,
            profile_action_delete=False,
            profile_action_action=action,
            profile_action_permissions=permission,
        ).exists()

    def permissions_map(self):
        rows = ProfileAction.objects.filter(
            profile_id=self.profile_id,
            profile__profile_active=True,
            profile__profile_delete=False,
            profile_action_active=True,
            profile_action_delete=False,
        ).values_list("profile_action_action", "profile_action_permissions")
        result = {}
        for action, perm in rows:
            result.setdefault(action, []).append(perm)
        return result


class PasswordResetPin(models.Model):
    """PIN temporal de recuperación. Se guarda hasheado, nunca en claro."""

    pin_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_pins")
    pin_hash = models.TextField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "password_reset_pin"
        ordering = ["-created_at"]
