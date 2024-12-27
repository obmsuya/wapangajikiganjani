from rest_framework import serializers
from django.contrib.auth import get_user_model
from phonenumber_field.serializerfields import PhoneNumberField

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    phone_number = PhoneNumberField()

    class Meta:
        model = User
        fields = ('phone_number', 'full_name', 'password', 'language')

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value

class OTPVerificationSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    otp = serializers.CharField(max_length=6)

class LoginSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    password = serializers.CharField(style={'input_type': 'password'})
    device_type = serializers.CharField(required=False, default='unknown')

class PasswordResetRequestSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()

class PasswordResetConfirmSerializer(serializers.Serializer):
    phone_number = PhoneNumberField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=8, style={'input_type': 'password'})
    confirm_password = serializers.CharField(min_length=8, style={'input_type': 'password'})

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords don't match")
        return data