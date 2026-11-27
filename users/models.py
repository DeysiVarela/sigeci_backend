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
    """Matriz de permisos por perfil y módulo."""

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
    """Usuario del sistema (tabla `users` y relación M:N `user_profiles`)."""

    PROVIDER_ACCOUNT = "ACCOUNT"
    PROVIDER_GMAIL = "GMAIL"
    PROVIDERS = [(PROVIDER_ACCOUNT, "ACCOUNT"), (PROVIDER_GMAIL, "GMAIL")]

    user_id = models.AutoField(primary_key=True)
    user_name = models.CharField(max_length=60)
    user_lastname = models.CharField(max_length=60)
    user_password = models.TextField()
    user_email = models.CharField(max_length=120, unique=True)
    user_provider = models.CharField(max_length=60, choices=PROVIDERS, default=PROVIDER_ACCOUNT)

    user_seed_token = models.CharField(max_length=120, null=True, blank=True)
    profiles = models.ManyToManyField(Profile, related_name="users", db_table="user_profiles")
    user_active = models.BooleanField(default=True)
    user_delete = models.BooleanField(default=False)

    user_created_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        db_column="user_created_by", related_name="+",
    )
    user_created_at = models.DateTimeField(auto_now_add=True)
    user_updated_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        db_column="user_updated_by", related_name="+",
    )
    user_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users"
        ordering = ["user_id"]

    def __str__(self):
        return self.user_email

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def set_password(self, raw_password):
        self.user_password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.user_password)

    def has_perm_on(self, action, permission):
        rows = ProfileAction.objects.filter(
            profile__in=self.profiles.all(),
            profile__profile_active=True,
            profile__profile_delete=False,
            profile_action_active=True,
            profile_action_delete=False,
            profile_action_action=action,
        ).values_list("profile_action_permissions", flat=True)
        return any(permission in (perms or "").split("|") for perms in rows)

    def permissions_map(self):
        rows = ProfileAction.objects.filter(
            profile__in=self.profiles.all(),
            profile__profile_active=True,
            profile__profile_delete=False,
            profile_action_active=True,
            profile_action_delete=False,
        ).values_list("profile_action_action", "profile_action_permissions")

        result = {}
        for action, perms in rows:
            for perm in (perms or "").split("|"):
                if perm and perm not in result.setdefault(action, []):
                    result[action].append(perm)
        return result


class PasswordResetPin(models.Model):
    """PIN temporal de recuperación (hasheado)."""

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
