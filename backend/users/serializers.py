from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import FavoriteTrack, PromptHistory, UserPreference

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'profile_picture',
            'bio',
            'is_spotify_connected',
            'is_staff',
            'is_superuser',
            'preferred_artists',
            'personalization_opt_in',
            'terms_accepted_at',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'is_spotify_connected',
            'is_staff',
            'is_superuser',
            'terms_accepted_at',
        ]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True)
    accept_terms = serializers.BooleanField(write_only=True)
    personalization_opt_in = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'password',
            'confirm_password',
            'accept_terms',
            'personalization_opt_in',
        ]

    def validate(self, data):
        data['username'] = str(data.get('username') or '').strip()
        data['email'] = str(data.get('email') or '').strip().lower()
        if not data['username']:
            raise serializers.ValidationError({'username': 'Display name is required.'})
        if not data['accept_terms']:
            raise serializers.ValidationError({
                'accept_terms': 'You must agree to the Terms and Privacy Policy.',
            })
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        validated_data.pop('accept_terms')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            personalization_opt_in=validated_data.get('personalization_opt_in', True),
            terms_accepted_at=timezone.now(),
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)
    confirm_new_password = serializers.CharField(required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError("New passwords do not match.")
        return data


class FavoriteTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = FavoriteTrack
        fields = '__all__'
        # `emotion` is set by the view from the request, which normalizes an
        # unknown value to "untagged" instead of rejecting the favorite.
        read_only_fields = ['user', 'added_at', 'emotion']


class PromptHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptHistory
        fields = '__all__'
        read_only_fields = ['user', 'created_at']


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = '__all__'
        read_only_fields = ['user']
