from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from phonenumber_field.modelfields import PhoneNumberField
from apps.properties.models import Unit, Property

class Tenant(models.Model):
    """
    Main tenant model storing personal and contact information
    """
    TENANT_STATUS = [
        ('active', _('Active')),
        ('pending', _('Pending')),
        ('former', _('Former')),
        ('blacklisted', _('Blacklisted'))
    ]
    
    ID_TYPES = [
        ('nida', _('National ID')),
        ('voter', _('Voter ID')),
        ('passport', _('Passport')),
        ('driving_license', _('Driving License'))
    ]

    # Personal Information
    full_name = models.CharField(max_length=255)
    phone_number = PhoneNumberField(unique=True)
    alternative_phone = PhoneNumberField(null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    id_type = models.CharField(max_length=20, choices=ID_TYPES)
    id_number = models.CharField(max_length=50)
    id_image = models.ImageField(upload_to='tenant_ids/', null=True, blank=True)
    profile_image = models.ImageField(upload_to='tenant_profiles/', null=True, blank=True)

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=255)
    emergency_contact_phone = PhoneNumberField()
    emergency_contact_relationship = models.CharField(max_length=50)

    # Occupation Information
    occupation = models.CharField(max_length=255, null=True, blank=True)
    employer_name = models.CharField(max_length=255, null=True, blank=True)
    employer_contact = PhoneNumberField(null=True, blank=True)

    # Status and Preferences
    status = models.CharField(max_length=20, choices=TENANT_STATUS, default='pending')
    language = models.CharField(
        max_length=2, 
        choices=[('en', 'English'), ('sw', 'Swahili')], 
        default='sw'
    )
    preferred_contact_method = models.CharField(
        max_length=10,
        choices=[('sms', 'SMS'), ('email', 'Email'), ('call', 'Phone Call')],
        default='sms'
    )

    # System Fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Tenant")
        verbose_name_plural = _("Tenants")

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    def soft_delete(self, reason=None):
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.deactivation_reason = reason
        self.save()

class TenantOccupancy(models.Model):
    """
    Tracks tenant occupancy in units, including contract details
    """
    PAYMENT_FREQUENCIES = [
        ('monthly', _('Monthly')),
        ('quarterly', _('Quarterly')),
        ('biannual', _('Bi-Annual')),
        ('annual', _('Annual')),
        ('custom', _('Custom'))
    ]

    OCCUPANCY_STATUS = [
        ('active', _('Active')),
        ('pending', _('Pending Move-in')),
        ('ended', _('Ended')),
        ('terminated', _('Terminated Early'))
    ]

    # Core Relations
    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='occupancies'
    )
    unit = models.ForeignKey(
        Unit, 
        on_delete=models.CASCADE, 
        related_name='occupancies'
    )
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE
    )

    # Contract Details
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2)
    key_deposit = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0
    )
    utilities_included = models.JSONField(
        default=dict,
        help_text=_("Dictionary of included utilities and their monthly costs")
    )

    # Payment Settings
    payment_frequency = models.CharField(max_length=20, choices=PAYMENT_FREQUENCIES)
    payment_day = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text=_("Day of month when rent is due")
    )
    grace_period_days = models.PositiveIntegerField(
        default=5,
        help_text=_("Number of days after due date before rent is considered late")
    )
    late_fee_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0
    )

    # Contract and Documents
    contract_document = models.FileField(
        upload_to='tenant_contracts/',
        null=True, 
        blank=True
    )
    move_in_checklist = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Move-in inspection checklist")
    )
    move_out_checklist = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Move-out inspection checklist")
    )

    # Status Fields
    status = models.CharField(
        max_length=20,
        choices=OCCUPANCY_STATUS,
        default='pending'
    )
    is_active = models.BooleanField(default=True)
    move_out_date = models.DateField(null=True, blank=True)
    move_out_reason = models.TextField(null=True, blank=True)
    deposit_refunded = models.BooleanField(default=False)
    deposit_refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    deposit_deduction_reason = models.TextField(null=True, blank=True)

    # Additional Information
    allowed_occupants = models.PositiveIntegerField(
        default=1,
        help_text=_("Number of people allowed to occupy the unit")
    )
    actual_occupants = models.JSONField(
        null=True,
        blank=True,
        help_text=_("List of people actually occupying the unit")
    )
    special_conditions = models.TextField(
        null=True,
        blank=True,
        help_text=_("Any special conditions or agreements")
    )

    # System Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Tenant Occupancy")
        verbose_name_plural = _("Tenant Occupancies")

    def __str__(self):
        return f"{self.tenant.full_name} - {self.unit.unit_number}"

    def calculate_next_payment_date(self):
        """Calculate the next payment due date based on frequency."""
        if not self.is_active:
            return None

        last_payment = self.payments.order_by('-payment_date').first()
        if not last_payment:
            return self.start_date

        if self.payment_frequency == 'monthly':
            delta = timedelta(days=30)
        elif self.payment_frequency == 'quarterly':
            delta = timedelta(days=90)
        elif self.payment_frequency == 'biannual':
            delta = timedelta(days=180)
        elif self.payment_frequency == 'annual':
            delta = timedelta(days=365)
        else:
            return None

        return last_payment.payment_date + delta

class TenantDocument(models.Model):
    """
    Stores documents related to tenants
    """
    DOCUMENT_TYPES = [
        ('contract', _('Rental Contract')),
        ('id', _('Identification')),
        ('employment', _('Employment Verification')),
        ('reference', _('Reference Letter')),
        ('inspection', _('Inspection Report')),
        ('notice', _('Notice')),
        ('other', _('Other Documents'))
    ]

    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='documents'
    )
    occupancy = models.ForeignKey(
        TenantOccupancy, 
        on_delete=models.CASCADE
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='tenant_documents/')
    description = models.TextField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = _("Tenant Document")
        verbose_name_plural = _("Tenant Documents")

    def __str__(self):
        return f"{self.tenant.full_name} - {self.document_type}"

class TenantNote(models.Model):
    """
    Stores notes and comments about tenants
    """
    NOTE_TYPES = [
        ('general', _('General Note')),
        ('complaint', _('Complaint')),
        ('maintenance', _('Maintenance')),
        ('payment', _('Payment')),
        ('violation', _('Violation')),
        ('warning', _('Warning'))
    ]

    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='notes'
    )
    occupancy = models.ForeignKey(
        TenantOccupancy, 
        on_delete=models.CASCADE
    )
    note_type = models.CharField(max_length=20, choices=NOTE_TYPES)
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_private = models.BooleanField(
        default=True,
        help_text=_("If True, only property owner can see this note")
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Tenant Note")
        verbose_name_plural = _("Tenant Notes")