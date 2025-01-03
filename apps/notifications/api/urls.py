from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet,
    NotificationPreferenceViewSet,
    SMSTemplateViewSet,
    ReminderViewSet
)

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'preferences', NotificationPreferenceViewSet, basename='preference')
router.register(r'sms-templates', SMSTemplateViewSet, basename='sms-template')
router.register(r'reminders', ReminderViewSet, basename='reminder')

urlpatterns = [
    path('', include(router.urls)),
]

# Available Endpoints:

"""
System Notifications:
GET     /api/v1/notifications/                - List all notifications
GET     /api/v1/notifications/unread/         - List unread notifications
GET     /api/v1/notifications/counts/         - Get unread notification counts
POST    /api/v1/notifications/{id}/mark_read/ - Mark notification as read
POST    /api/v1/notifications/mark_all_read/  - Mark all notifications as read

Notification Preferences:
GET     /api/v1/preferences/                  - Get user preferences
PATCH   /api/v1/preferences/                  - Update preferences
PATCH   /api/v1/preferences/update_preferences/ - Update specific preferences

SMS Templates:
GET     /api/v1/sms-templates/               - List all SMS templates
POST    /api/v1/sms-templates/               - Create new template
GET     /api/v1/sms-templates/{id}/          - Get template details
PUT     /api/v1/sms-templates/{id}/          - Update template
POST    /api/v1/sms-templates/{id}/test/     - Test SMS template

Reminders:
POST    /api/v1/reminders/send_rent_reminder/      - Send rent reminder
POST    /api/v1/reminders/send_maintenance_update/ - Send maintenance update
POST    /api/v1/reminders/send_custom_notification/ - Send custom notification
"""