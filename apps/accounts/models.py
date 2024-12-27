from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from apps.utils.managers import CustomUserManager

class User(AbstractBaseUser, PermissionsMixin):
    phone_number = PhoneNumberField(unique=True)
    full_name = models.CharField(max_length=255)
    language = models.CharField(max_length=2, choices=[('en', 'English'), ('sw', 'Swahili')], default='sw')
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True)
    last_logout = models.DateTimeField(null=True)
    login_attempts = models.IntegerField(default=0)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['full_name']

class OTPVerification(models.Model):
    phone_number = PhoneNumberField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    type = models.CharField(max_length=20, default='registration')

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at

class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=40)
    device_type = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField()
    location = models.CharField(max_length=255, null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_activity']