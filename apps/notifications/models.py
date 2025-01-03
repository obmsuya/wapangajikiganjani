from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class SMSTemplate(models.Model):
    """Templates for different types of SMS notifications"""
    TEMPLATE_TYPES = [
        ('rent_reminder', _('Rent Reminder')),
        ('payment_confirmation', _('Payment Confirmation')),
        ('maintenance', _('Maintenance Update')),
        ('welcome', _('Welcome Message')),
        ('custom', _('Custom Message'))
    ]

    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    template_text = models.TextField(
        help_text=_("Use {tenant_name}, {amount}, {due_date}, etc. as placeholders")
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.template_type})"

class SMSLog(models.Model):
    """Log of all sent SMS messages"""
    recipient_number = models.CharField(max_length=20)
    message = models.TextField()
    template = models.ForeignKey(
        SMSTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('sent', _('Sent')),
            ('failed', _('Failed')),
            ('delivered', _('Delivered'))
        ]
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    delivery_status = models.CharField(max_length=50, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']

class Notification(models.Model):
    """System notifications for users"""
    NOTIFICATION_TYPES = [
        ('payment_received', _('Payment Received')),
        ('tenant_assigned', _('New Tenant Assigned')),
        ('tenant_vacated', _('Tenant Vacated')),
        ('maintenance_request', _('Maintenance Request')),
        ('rent_overdue', _('Rent Overdue')),
        ('admin_alert', _('Admin Alert'))
    ]

    PRIORITY_LEVELS = [
        ('low', _('Low')),
        ('medium', _('Medium')),
        ('high', _('High'))
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    priority = models.CharField(
        max_length=20, 
        choices=PRIORITY_LEVELS,
        default='medium'
    )
    
    # For linking to related objects (payments, tenants, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at'])
        ]

class NotificationPreference(models.Model):
    """User preferences for notifications"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # SMS Preferences
    rent_reminder_days = models.PositiveIntegerField(
        default=3,
        help_text=_("Days before due date to send rent reminder")
    )
    payment_confirmation = models.BooleanField(default=True)
    maintenance_updates = models.BooleanField(default=True)
    tenant_updates = models.BooleanField(default=True)
    
    # System Notification Preferences
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    notification_types = models.JSONField(
        default=dict,
        help_text=_("Specific notification types to receive")
    )

    class Meta:
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")