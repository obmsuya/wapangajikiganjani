from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from django.db import transaction
from apps.properties.models import Property, Floor, Unit, UnitType, PropertyType, PropertyUnit, PropertyLayout

class UnitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitType
        fields = ['id', 'name', 'description', 'default_layout']

class UnitSerializer(GeoFeatureModelSerializer):
    floor_number = serializers.IntegerField(source='floor.floor_number', read_only=True)
    
    class Meta:
        model = Unit
        geo_field = 'location'
        fields = [
            'id', 'unit_number', 'floor_number', 'unit_type', 'area',
            'rent_amount', 'payment_frequency', 'status', 'is_active'
        ]

class FloorSerializer(serializers.ModelSerializer):
    units = UnitSerializer(many=True, read_only=True)
    
    class Meta:
        model = Floor
        fields = [
            'id', 'floor_number', 'total_units', 'layout_type',
            'layout_data', 'area', 'units'
        ]

class PropertyRegistrationSerializer(GeoFeatureModelSerializer):
    floors = FloorSerializer(many=True)
    
    class Meta:
        model = Property
        geo_field = 'location'
        fields = [
            'name', 'category', 'total_floors', 'address', 'boundary',
            'total_area', 'image', 'floors'
        ]

    @transaction.atomic
    def create(self, validated_data):
        floors_data = validated_data.pop('floors', [])
        
        # Create the property
        property_instance = Property.objects.create(**validated_data)
        
        # Create floors and units
        for floor_data in floors_data:
            units_data = floor_data.pop('units', [])
            floor = Floor.objects.create(property=property_instance, **floor_data)
            
            # Generate units based on layout
            self._generate_units(floor, units_data)
        
        return property_instance

    def _generate_units(self, floor, units_data):
        layout_type = floor.layout_type
        total_units = floor.total_units
        
        # Generate unit polygons based on floor layout
        unit_polygons = self._generate_unit_polygons(
            floor.layout_type,
            floor.property.boundary,
            total_units
        )
        
        # Create units with generated polygons
        for i, (unit_data, polygon) in enumerate(zip(units_data, unit_polygons), 1):
            Unit.objects.create(
                floor=floor,
                unit_number=f"{floor.floor_number}-{i:02d}",
                location=polygon,
                area=polygon.area,
                **unit_data
            )

    def _generate_unit_polygons(self, layout_type, boundary, total_units):
        # This would call the appropriate layout generation method
        # based on layout type
        if layout_type == 'rectangular':
            return self._generate_rectangular_units(boundary, total_units)
        elif layout_type == 'l_shaped':
            return self._generate_l_shaped_units(boundary, total_units)
        else:
            return self._generate_custom_units(boundary, total_units)

class PropertyUpdateSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Property
        geo_field = 'location'
        fields = [
            'name', 'address', 'image', 'is_active'
        ]

class FloorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = [
            'layout_type', 'layout_data', 'area'
        ]

class UnitUpdateSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Unit
        geo_field = 'location'
        fields = [
            'unit_type', 'rent_amount', 'payment_frequency',
            'status', 'is_active'
        ]

class PropertyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyType
        fields = ['id', 'name', 'description']

class PropertyUnitSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = PropertyUnit
        geo_field = 'location'
        fields = ['id', 'unit_number', 'floor_number', 'area', 'rent_amount', 
                 'status', 'is_active', 'created_at', 'updated_at']

class PropertyLayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyLayout
        fields = ['id', 'layout_data', 'version', 'is_current', 
                 'created_at', 'updated_at']

class PropertySerializer(GeoFeatureModelSerializer):
    units = PropertyUnitSerializer(many=True, read_only=True)
    layout = PropertyLayoutSerializer(read_only=True)
    property_type_name = serializers.CharField(source='property_type.name', read_only=True)

    class Meta:
        model = Property
        geo_field = 'location'
        fields = ['id', 'name', 'property_type', 'property_type_name', 
                 'layout_type', 'boundary', 'address', 'total_units', 
                 'area', 'image', 'is_active', 'units', 'layout', 
                 'created_at', 'updated_at']

class PropertyCreateSerializer(GeoFeatureModelSerializer):
    layout_data = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = Property
        geo_field = 'location'
        fields = ['name', 'property_type', 'layout_type', 'boundary', 
                 'address', 'total_units', 'area', 'image', 'layout_data']

    def create(self, validated_data):
        layout_data = validated_data.pop('layout_data', None)
        property_instance = Property.objects.create(**validated_data)

        if layout_data:
            PropertyLayout.objects.create(
                property=property_instance,
                layout_data=layout_data
            )

        return property_instance

class PropertyUpdateSerializer(GeoFeatureModelSerializer):
    layout_data = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = Property
        geo_field = 'location'
        fields = ['name', 'layout_type', 'boundary', 'address', 
                 'total_units', 'area', 'image', 'layout_data']

    def update(self, instance, validated_data):
        layout_data = validated_data.pop('layout_data', None)
        
        if layout_data:
            # Create new version of layout
            PropertyLayout.objects.filter(property=instance).update(is_current=False)
            current_version = PropertyLayout.objects.filter(
                property=instance
            ).order_by('-version').first()
            
            new_version = current_version.version + 1 if current_version else 1
            
            PropertyLayout.objects.create(
                property=instance,
                layout_data=layout_data,
                version=new_version,
                is_current=True
            )

        return super().update(instance, validated_data)