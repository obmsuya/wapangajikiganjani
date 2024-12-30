from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as django_filters

from apps.tenants.models import (
    Tenant, TenantOccupancy, TenantDocument, TenantNote
)
from apps.properties.models import Unit, Property
from apps.notifications.services.sms import SMSService
from .serializers import (
    TenantSerializer, TenantListSerializer, TenantOccupancySerializer,
    TenantAssignmentSerializer, TenantVacateSerializer,
    TenantDocumentSerializer, TenantNoteSerializer
)

sms_service = SMSService()

class TenantFilter(django_filters.FilterSet):
    """Filter set for tenant searching and filtering"""
    search = django_filters.CharFilter(method='filter_search')
    status = django_filters.ChoiceFilter(choices=Tenant.TENANT_STATUS)
    property = django_filters.NumberFilter(field_name='occupancies__property')
    payment_status = django_filters.ChoiceFilter(
        choices=[('paid', 'Paid'), ('overdue', 'Overdue')],
        method='filter_payment_status'
    )
    
    class Meta:
        model = Tenant
        fields = ['search', 'status', 'property', 'payment_status']
    
    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(full_name__icontains=value) |
            Q(phone_number__icontains=value) |
            Q(email__icontains=value)
        )
    
    def filter_payment_status(self, queryset, name, value):
        # Implementation for payment status filtering
        # This would be linked to a payment tracking system
        pass

class TenantViewSet(viewsets.ModelViewSet):
    """
    Comprehensive viewset for tenant management
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [django_filters.DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = TenantFilter
    ordering_fields = ['created_at', 'full_name', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get tenants for properties owned by current user"""
        return Tenant.objects.filter(
            occupancies__property__owner=self.request.user
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'list':
            return TenantListSerializer
        return TenantSerializer

    @transaction.atomic
    @action(detail=False, methods=['post'])
    def assign_tenant(self, request):
        """
        Assign a tenant to a unit with full contract details
        """
        serializer = TenantAssignmentSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Get or create tenant
                tenant_data = serializer.validated_data
                tenant_id = tenant_data.get('tenant_id')
                
                if tenant_id:
                    tenant = Tenant.objects.get(id=tenant_id)
                else:
                    # Create new tenant
                    tenant = Tenant.objects.create(
                        full_name=tenant_data['full_name'],
                        phone_number=tenant_data['phone_number'],
                        email=tenant_data.get('email'),
                        id_type=tenant_data['id_type'],
                        id_number=tenant_data['id_number'],
                        status='active'
                    )

                # Get unit and verify ownership
                unit = Unit.objects.get(
                    id=tenant_data['unit_id'],
                    floor__property__owner=request.user
                )

                # Create occupancy
                occupancy = TenantOccupancy.objects.create(
                    tenant=tenant,
                    unit=unit,
                    property=unit.floor.property,
                    start_date=tenant_data['start_date'],
                    end_date=tenant_data.get('end_date'),
                    rent_amount=tenant_data['rent_amount'],
                    deposit_amount=tenant_data['deposit_amount'],
                    key_deposit=tenant_data.get('key_deposit', 0),
                    payment_frequency=tenant_data['payment_frequency'],
                    payment_day=tenant_data['payment_day'],
                    utilities_included=tenant_data.get('utilities_included', {}),
                    allowed_occupants=tenant_data.get('allowed_occupants', 1),
                    actual_occupants=tenant_data.get('actual_occupants', []),
                    special_conditions=tenant_data.get('special_conditions'),
                    status='active'
                )

                # Handle contract document if provided
                if 'contract_document' in request.FILES:
                    TenantDocument.objects.create(
                        tenant=tenant,
                        occupancy=occupancy,
                        document_type='contract',
                        title='Rental Agreement',
                        file=request.FILES['contract_document']
                    )

                # Update unit status
                unit.status = 'occupied'
                unit.save()

                # Send welcome SMS
                self._send_welcome_sms(tenant, occupancy)

                return Response({
                    'message': 'Tenant assigned successfully',
                    'tenant_id': tenant.id,
                    'occupancy_id': occupancy.id
                })

            except Unit.DoesNotExist:
                return Response(
                    {'error': 'Invalid unit or unauthorized access'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    @action(detail=True, methods=['post'])
    def vacate_tenant(self, request, pk=None):
        """
        Process tenant vacation from a unit
        """
        serializer = TenantVacateSerializer(data=request.data)
        if serializer.is_valid():
            tenant = self.get_object()
            try:
                # Get active occupancy
                occupancy = tenant.occupancies.get(is_active=True)
                
                # Update occupancy
                occupancy.status = 'ended'
                occupancy.is_active = False
                occupancy.move_out_date = serializer.validated_data['move_out_date']
                occupancy.move_out_reason = serializer.validated_data.get('move_out_reason')
                occupancy.move_out_checklist = serializer.validated_data.get('move_out_checklist')
                occupancy.deposit_refund_amount = serializer.validated_data.get('deposit_refund_amount')
                occupancy.deposit_deduction_reason = serializer.validated_data.get('deposit_deduction_reason')
                occupancy.save()

                # Update unit status
                unit = occupancy.unit
                unit.status = 'available'
                unit.save()

                # Create vacation note
                TenantNote.objects.create(
                    tenant=tenant,
                    occupancy=occupancy,
                    note_type='general',
                    title='Tenant Vacation',
                    content=f"Tenant vacated on {occupancy.move_out_date}. "
                           f"Reason: {occupancy.move_out_reason}",
                    created_by=request.user
                )

                # Send confirmation SMS
                self._send_vacation_confirmation(tenant, occupancy)

                return Response({
                    'message': 'Tenant vacated successfully',
                    'deposit_refund_amount': occupancy.deposit_refund_amount
                })

            except TenantOccupancy.DoesNotExist:
                return Response(
                    {'error': 'No active occupancy found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def occupancy_history(self, request, pk=None):
        """
        Get tenant's occupancy history
        """
        tenant = self.get_object()
        occupancies = tenant.occupancies.all()
        serializer = TenantOccupancySerializer(occupancies, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """
        Get tenant's documents
        """
        tenant = self.get_object()
        documents = tenant.documents.all()
        serializer = TenantDocumentSerializer(documents, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def notes(self, request, pk=None):
        """
        Get tenant's notes
        """
        tenant = self.get_object()
        notes = tenant.notes.filter(
            Q(is_private=False) | Q(created_by=request.user)
        )
        serializer = TenantNoteSerializer(notes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """
        Add a note to tenant's record
        """
        tenant = self.get_object()
        serializer = TenantNoteSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save(tenant=tenant)
            return Response(serializer.data)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        """
        Upload a document for the tenant
        """
        tenant = self.get_object()
        serializer = TenantDocumentSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(tenant=tenant)
            return Response(serializer.data)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def send_reminder(self, request, pk=None):
        """
        Send a reminder SMS to tenant
        """
        tenant = self.get_object()
        message_type = request.data.get('type', 'rent')
        custom_message = request.data.get('message')

        try:
            if message_type == 'rent':
                message = self._generate_rent_reminder(tenant)
            else:
                message = custom_message

            # Send SMS
            success = sms_service.send_sms(
                phone_number=str(tenant.phone_number),
                message=message
            )

            if success:
                return Response({'message': 'Reminder sent successfully'})
            else:
                return Response(
                    {'error': 'Failed to send reminder'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _send_welcome_sms(self, tenant, occupancy):
        """Send welcome SMS to new tenant"""
        message = _(
            "Welcome {tenant_name} to {property_name}! "
            "Your unit number is {unit_number}. "
            "Rent of {rent_amount} is due on day {payment_day} "
            "of each {frequency}."
        ).format(
            tenant_name=tenant.full_name,
            property_name=occupancy.property.name,
            unit_number=occupancy.unit.unit_number,
            rent_amount=occupancy.rent_amount,
            payment_day=occupancy.payment_day,
            frequency=occupancy.get_payment_frequency_display().lower()
        )
        
        sms_service.send_sms(str(tenant.phone_number), message)

    def _send_vacation_confirmation(self, tenant, occupancy):
        """Send vacation confirmation SMS"""
        message = _(
            "Dear {tenant_name}, your vacation from {unit_number} "
            "has been processed. Your deposit refund of {refund_amount} "
            "will be processed within 7 working days."
        ).format(
            tenant_name=tenant.full_name,
            unit_number=occupancy.unit.unit_number,
            refund_amount=occupancy.deposit_refund_amount or occupancy.deposit_amount
        )
        
        sms_service.send_sms(str(tenant.phone_number), message)

    def _generate_rent_reminder(self, tenant):
        """Generate rent reminder message"""
        occupancy = tenant.occupancies.filter(is_active=True).first()
        if not occupancy:
            raise ValueError("No active occupancy found")

        next_payment = occupancy.calculate_next_payment_date()
        
        message = _(
            "Dear {tenant_name}, your rent of {amount} "
            "for {unit_number} is due on {due_date}. "
            "Please ensure timely payment to avoid late fees."
        ).format(
            tenant_name=tenant.full_name,
            amount=occupancy.rent_amount,
            unit_number=occupancy.unit.unit_number,
            due_date=next_payment.strftime("%d/%m/%Y")
        )
        
        return message