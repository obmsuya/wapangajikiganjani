from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ..models import (
    Notification, NotificationPreference, SMSTemplate, SMSLog
)
from ..services.sms import SMSService
from ..services.notification import NotificationService
from .serializers import (
    NotificationSerializer, NotificationPreferenceSerializer,
    SMSTemplateSerializer, SMSLogSerializer
)

class NotificationViewSet(viewsets.ModelViewSet):
    """
    Viewset for handling system notifications
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = PageNumberPagination

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=['get'])
    def unread(self):
        """Get unread notifications"""
        notifications = NotificationService.get_unread_notifications(self.request.user)
        page = self.paginate_queryset(notifications)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def counts(self):
        """Get notification counts"""
        unread_count = NotificationService.get_notifications_count(self.request.user)
        return Response({
            'unread_count': unread_count
        })

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark notification as read"""
        success = NotificationService.mark_as_read(pk, request.user)
        if success:
            return Response({'status': 'notification marked as read'})
        return Response(
            {'error': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response({'status': 'all notifications marked as read'})

class NotificationPreferenceViewSet(mixins.RetrieveModelMixin,
                                  mixins.UpdateModelMixin,
                                  viewsets.GenericViewSet):
    """
    Viewset for managing notification preferences
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer

    def get_object(self):
        """Get or create notification preferences for user"""
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference

    @action(detail=False, methods=['patch'])
    def update_preferences(self, request):
        """Update specific notification preferences"""
        preference = self.get_object()
        serializer = self.get_serializer(
            preference,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
            
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

class SMSTemplateViewSet(viewsets.ModelViewSet):
    """
    Viewset for managing SMS templates
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SMSTemplateSerializer
    queryset = SMSTemplate.objects.all()

    @action(detail=True, methods=['post'])
    def test_template(self, request, pk=None):
        """Test SMS template with sample data"""
        template = self.get_object()
        test_phone = request.data.get('test_phone')
        
        if not test_phone:
            return Response(
                {'error': 'Test phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sample context for template testing
        context = {
            'tenant_name': 'Test Tenant',
            'amount': '1000',
            'due_date': timezone.now().strftime('%d/%m/%Y'),
            'unit_number': 'A-123'
        }

        sms_service = SMSService()
        success = sms_service.send_custom_sms(test_phone, template.name, context)

        if success:
            return Response({'status': 'test SMS sent successfully'})
        return Response(
            {'error': 'Failed to send test SMS'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class ReminderViewSet(viewsets.ViewSet):
    """
    Viewset for handling rent reminders and other notifications
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def send_rent_reminder(self, request):
        """Send rent reminder to tenant"""
        tenant_id = request.data.get('tenant_id')
        custom_message = request.data.get('custom_message')
        
        try:
            tenant = request.user.tenants.get(id=tenant_id)
            occupancy = tenant.current_occupancy
            
            if not occupancy:
                return Response(
                    {'error': 'No active occupancy found for tenant'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            sms_service = SMSService()
            if custom_message:
                success = sms_service.send_sms(
                    tenant.phone_number,
                    custom_message
                )
            else:
                success = sms_service.send_rent_reminder(
                    tenant,
                    occupancy.next_payment_date,
                    occupancy.rent_amount
                )

            if success:
                return Response({'status': 'reminder sent successfully'})
            return Response(
                {'error': 'Failed to send reminder'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def send_maintenance_update(self, request):
        """Send maintenance update to tenant"""
        tenant_id = request.data.get('tenant_id')
        status_update = request.data.get('status')
        description = request.data.get('description')
        
        try:
            tenant = request.user.tenants.get(id=tenant_id)
            
            sms_service = SMSService()
            success = sms_service.send_maintenance_update(
                tenant,
                status_update,
                description
            )

            if success:
                return Response({'status': 'maintenance update sent successfully'})
            return Response(
                {'error': 'Failed to send maintenance update'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def send_custom_notification(self, request):
        """Send custom notification to tenant"""
        tenant_id = request.data.get('tenant_id')
        message = request.data.get('message')
        notification_type = request.data.get('type', 'custom')
        
        if not all([tenant_id, message]):
            return Response(
                {'error': 'Tenant ID and message are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            tenant = request.user.tenants.get(id=tenant_id)
            
            # Send SMS
            sms_service = SMSService()
            sms_success = sms_service.send_sms(tenant.phone_number, message)

            # Create system notification
            NotificationService.create_notification(
                user=request.user,
                title=f"Notification Sent to {tenant.full_name}",
                message=message,
                notification_type=notification_type,
                related_object=tenant
            )

            return Response({
                'status': 'notification sent',
                'sms_sent': sms_success
            })

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )