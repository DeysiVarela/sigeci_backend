from rest_framework import serializers

from .models import Profile, User

class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="profile_id", read_only=True)
    name = serializers.CharField(source="profile_name", read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    """Serializador de sesión para Login (/auth/login y /auth/register)."""

    id = serializers.IntegerField(source="user_id", read_only=True)
    name = serializers.CharField(source="user_name", read_only=True)
    lastname = serializers.CharField(source="user_lastname", read_only=True)
    email = serializers.CharField(source="user_email", read_only=True)
    provider = serializers.CharField(source="user_provider", read_only=True)
    active = serializers.BooleanField(source="user_active", read_only=True)
    user_seed_token = serializers.CharField(read_only=True)
    profiles = ProfileSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(source="user_created_at", read_only=True)
    updated_at = serializers.DateTimeField(source="user_updated_at", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "name", "lastname", "email", "provider",
            "profiles", "user_seed_token", "active", "created_at", "updated_at",
        ]
