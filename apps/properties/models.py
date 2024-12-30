from django.contrib.gis.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _

class Property(models.Model):
    PROPERTY_CATEGORIES = [
        ('apartment', _('Apartment Building')),
        ('villa', _('Villa')),
        ('rooms', _('Normal Rooms')),
        ('bungalow', _('Bungalow'))
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=PROPERTY_CATEGORIES)
    total_floors = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
        help_text=_("Number of floors including ground floor")
    )
    location = models.PointField(srid=4326)
    address = models.TextField()
    boundary = models.PolygonField(srid=4326)
    total_area = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text=_("Total area in square meters")
    )
    image = models.ImageField(upload_to='properties/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Properties"

    def __str__(self):
        return f"{self.name} - {self.get_category_display()}"

class Floor(models.Model):
    LAYOUT_TYPES = [
        ('rectangular', _('Rectangular')),
        ('l_shaped', _('L-Shaped')),
        ('u_shaped', _('U-Shaped')),
        ('custom', _('Custom'))
    ]
    
    LAYOUT_CREATION_METHODS = [
        ('auto', _('Auto-Generated')),
        ('manual', _('Manually Drawn')),
        ('upload', _('Uploaded Floor Plan')),
        ('template', _('From Template'))
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='floors')
    floor_number = models.IntegerField(validators=[MinValueValidator(0)])  # 0 for ground floor
    total_units = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    layout_type = models.CharField(
        max_length=20,
        choices=LAYOUT_TYPES,
        default='rectangular'
    )
    layout_creation_method = models.CharField(
        max_length=20,
        choices=LAYOUT_CREATION_METHODS,
        default='auto',
        help_text=_("Method used to create the floor layout")
    )
    layout_data = models.JSONField(
        null=True, 
        blank=True,
        help_text=_("Stores layout configuration, drawing data, or image processing results")
    )
    area = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text=_("Floor area in square meters")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['floor_number']
        unique_together = ['property', 'floor_number']

    def __str__(self):
        return f"{self.property.name} - Floor {self.floor_number}"

class UnitType(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    default_layout = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return self.name

class Unit(models.Model):
    UNIT_STATUS = [
        ('available', _('Available')),
        ('occupied', _('Occupied')),
        ('maintenance', _('Under Maintenance')),
        ('reserved', _('Reserved'))
    ]
    
    PAYMENT_FREQUENCY = [
        ('monthly', _('Monthly')),
        ('quarterly', _('Quarterly')),
        ('biannual', _('Bi-Annual')),
        ('annual', _('Annual')),
        ('custom', _('Custom'))
    ]

    # Core fields
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='units')
    unit_number = models.CharField(max_length=50)
    unit_type = models.ForeignKey(UnitType, on_delete=models.PROTECT, null=True)
    location = models.PolygonField(srid=4326)  # For storing unit boundary
    
    # Size and financial details
    area = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        help_text=_("Area in square meters"),
        default=0.0
    )
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    payment_frequency = models.CharField(
        max_length=20,
        choices=PAYMENT_FREQUENCY,
        default='monthly'
    )
    
    # Status and layout
    status = models.CharField(max_length=20, choices=UNIT_STATUS, default='available')
    layout_data = models.JSONField(null=True, blank=True)
    
    # Tenant management fields
    current_tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_unit'
    )
    occupancy_history = models.ManyToManyField(
        'tenants.TenantOccupancy',
        related_name='unit_history',
        blank=True
    )
    max_occupants = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of allowed occupants"
    )
    amenities = models.JSONField(
        default=dict,
        help_text="Unit-specific amenities and features"
    )
    
    # System fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit_number']
        unique_together = ['floor', 'unit_number']

    def __str__(self):
        return f"{self.floor.property.name} - Floor {self.floor.floor_number} - Unit {self.unit_number}"

class UnitUtility(models.Model):
    """Model for tracking utilities for each unit"""
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='utilities')
    utility_type = models.CharField(max_length=50)  # water, electricity, etc.
    included_in_rent = models.BooleanField(default=False)
    meter_number = models.CharField(max_length=50, null=True, blank=True)
    cost_allocation = models.CharField(
        max_length=20,
        choices=[('landlord', 'Landlord'), ('tenant', 'Tenant')],
        default='tenant'
    )
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Unit Utility"
        verbose_name_plural = "Unit Utilities"
        ordering = ['utility_type']

    def __str__(self):
        return f"{self.unit.unit_number} - {self.utility_type}"

class UnitMaintenance(models.Model):
    """Model for tracking maintenance issues and repairs"""
    ISSUE_PRIORITY = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('emergency', 'Emergency')
    ]
    
    ISSUE_STATUS = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='maintenance_issues')
    issue_type = models.CharField(max_length=100)
    description = models.TextField()
    reported_by = models.ForeignKey('tenants.Tenant', on_delete=models.SET_NULL, null=True)
    reported_date = models.DateTimeField(auto_now_add=True)
    priority = models.CharField(max_length=20, choices=ISSUE_PRIORITY, default='medium')
    status = models.CharField(max_length=20, choices=ISSUE_STATUS, default='pending')
    assigned_to = models.CharField(max_length=255, null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Unit Maintenance"
        verbose_name_plural = "Unit Maintenance Issues"
        ordering = ['-reported_date']

    def __str__(self):
        return f"{self.unit.unit_number} - {self.issue_type} ({self.status})"