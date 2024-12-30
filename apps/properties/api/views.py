from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.contrib.gis.geos import Point, Polygon, MultiPolygon, LinearRing
from django.utils.translation import gettext_lazy as _
import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon, box
from shapely.ops import unary_union
import cv2
from PIL import Image
import io

from apps.properties.models import Property, Floor, Unit, UnitType
from .serializers import (
    PropertyRegistrationSerializer, PropertyUpdateSerializer,
    FloorUpdateSerializer, UnitUpdateSerializer,
    UnitTypeSerializer
)

class PropertyLayoutManager:
    @staticmethod
    def handle_manual_drawing(geojson_data):
        """Process manually drawn layout from GeoJSON data."""
        try:
            coordinates = geojson_data['geometry']['coordinates'][0]
            return Polygon(coordinates)
        except Exception as e:
            raise ValueError(f"Invalid GeoJSON data: {str(e)}")

    @staticmethod
    def process_uploaded_plan(image_data, scale_factor):
        """Process uploaded floor plan image using CV."""
        # Convert image to numpy array
        img = Image.open(io.BytesIO(image_data))
        img_array = np.array(img)
        
        # Convert to grayscale and process
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Convert contours to polygons
        polygons = []
        for contour in contours:
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            coords = [(x[0][0] * scale_factor, x[0][1] * scale_factor) for x in approx]
            
            if len(coords) >= 3:
                polygons.append(Polygon(coords))
        
        return polygons

class PropertyRegistrationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PropertyRegistrationSerializer

    def get_queryset(self):
        return Property.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['post'])
    def add_floor(self, request, pk=None):
        """Add a new floor to an existing property."""
        property_instance = self.get_object()
        
        try:
            with transaction.atomic():
                # Create floor with layout creation method
                floor = Floor.objects.create(
                    property=property_instance,
                    floor_number=request.data.get('floor_number'),
                    total_units=request.data.get('total_units'),
                    layout_type=request.data.get('layout_type', 'rectangular'),
                    layout_creation_method=request.data.get('creation_method', 'auto'),
                    area=request.data.get('area')
                )
                
                # Generate units based on creation method
                self._generate_floor_units(floor, request.data)
                
                return Response({
                    "message": "Floor added successfully",
                    "floor_id": floor.id
                })
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def update_floor_layout(self, request, pk=None):
        """Update floor layout and regenerate units."""
        floor_id = request.data.get('floor_id')
        try:
            floor = Floor.objects.get(
                property=self.get_object(),
                id=floor_id
            )
        except Floor.DoesNotExist:
            return Response(
                {"error": "Floor not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FloorUpdateSerializer(
            floor,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            with transaction.atomic():
                floor = serializer.save()
                
                if 'layout_type' in request.data or 'layout_data' in request.data:
                    floor.units.all().delete()
                    self._generate_floor_units(floor, request.data)
                
                return Response({
                    "message": "Floor layout updated successfully"
                })
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    def _generate_floor_units(self, floor, data):
        """Generate units based on layout creation method."""
        creation_method = floor.layout_creation_method
        
        if creation_method == 'manual':
            # Process manually drawn layout
            layout_data = data.get('layout_data', {})
            unit_polygons = [
                PropertyLayoutManager.handle_manual_drawing(unit_data)
                for unit_data in layout_data.get('units', [])
            ]
        
        elif creation_method == 'upload':
            # Process uploaded floor plan
            image_data = data.get('floor_plan')
            scale_factor = data.get('scale_factor', 1.0)
            unit_polygons = PropertyLayoutManager.process_uploaded_plan(
                image_data, scale_factor
            )
        
        else:  # 'auto' or 'template'
            # Generate from templates
            unit_polygons = self._generate_unit_polygons(
                floor.layout_type,
                floor.property.boundary,
                floor.total_units
            )
        
        # Create units with generated polygons
        for i, polygon in enumerate(unit_polygons, 1):
            Unit.objects.create(
                floor=floor,
                unit_number=f"{floor.floor_number}-{i:02d}",
                location=polygon,
                area=polygon.area,
                rent_amount=data.get('default_rent', 0),
                payment_frequency=data.get('payment_frequency', 'monthly')
            )

    def _generate_unit_polygons(self, layout_type, boundary, total_units):
        """Generate unit polygons based on layout type."""
        if layout_type == 'rectangular':
            return self._generate_rectangular_units(boundary, total_units)
        elif layout_type == 'l_shaped':
            return self._generate_l_shaped_units(boundary, total_units)
        elif layout_type == 'u_shaped':
            return self._generate_u_shaped_units(boundary, total_units)
        else:
            return self._generate_custom_units(boundary, total_units)

    def _generate_rectangular_units(self, boundary, total_units):
        """Generate rectangular units within the boundary."""
        bounds = boundary.extent
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        # Calculate optimal grid dimensions
        ratio = width / height
        cols = int(np.sqrt(total_units * ratio))
        rows = int(np.ceil(total_units / cols))
        
        unit_width = width / cols
        unit_height = height / rows
        
        units = []
        for i in range(rows):
            for j in range(cols):
                if len(units) >= total_units:
                    break
                
                unit = box(
                    bounds[0] + j * unit_width,
                    bounds[1] + i * unit_height,
                    bounds[0] + (j + 1) * unit_width,
                    bounds[1] + (i + 1) * unit_height
                )
                units.append(Polygon(unit.exterior.coords))
        
        return units

    def _generate_l_shaped_units(self, boundary, total_units):
        """Generate L-shaped unit layout."""
        bounds = boundary.extent
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        vertical_units = total_units // 2
        horizontal_units = total_units - vertical_units
        
        units = []
        
        # Vertical section
        v_height = height / vertical_units
        for i in range(vertical_units):
            unit = box(
                bounds[0],
                bounds[1] + i * v_height,
                bounds[0] + width * 0.4,
                bounds[1] + (i + 1) * v_height
            )
            units.append(Polygon(unit.exterior.coords))
        
        # Horizontal section
        h_width = width / horizontal_units
        for i in range(horizontal_units):
            unit = box(
                bounds[0] + i * h_width,
                bounds[1],
                bounds[0] + (i + 1) * h_width,
                bounds[1] + height * 0.4
            )
            units.append(Polygon(unit.exterior.coords))
        
        return units

    def _generate_u_shaped_units(self, boundary, total_units):
        """Generate U-shaped unit layout."""
        bounds = boundary.extent
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        
        units_per_vertical = total_units // 3
        remaining_units = total_units - (2 * units_per_vertical)
        
        units = []
        
        # Left vertical section
        v_height = height / units_per_vertical
        for i in range(units_per_vertical):
            unit = box(
                bounds[0],
                bounds[1] + i * v_height,
                bounds[0] + width * 0.2,
                bounds[1] + (i + 1) * v_height
            )
            units.append(Polygon(unit.exterior.coords))
        
        # Right vertical section
        for i in range(units_per_vertical):
            unit = box(
                bounds[2] - width * 0.2,
                bounds[1] + i * v_height,
                bounds[2],
                bounds[1] + (i + 1) * v_height
            )
            units.append(Polygon(unit.exterior.coords))
        
        # Bottom horizontal section
        h_width = (width - 2 * (width * 0.2)) / remaining_units
        for i in range(remaining_units):
            unit = box(
                bounds[0] + width * 0.2 + i * h_width,
                bounds[1],
                bounds[0] + width * 0.2 + (i + 1) * h_width,
                bounds[1] + height * 0.2
            )
            units.append(Polygon(unit.exterior.coords))
        
        return units

    def _generate_custom_units(self, boundary, total_units):
        """Generate custom unit layout based on property shape."""
        shapely_boundary = ShapelyPolygon(boundary.coords[0])
        bounds = boundary.extent
        
        # Create a grid of potential units
        grid_size = int(np.sqrt(total_units * 2))
        cell_width = (bounds[2] - bounds[0]) / grid_size
        cell_height = (bounds[3] - bounds[1]) / grid_size
        
        potential_units = []
        for i in range(grid_size):
            for j in range(grid_size):
                cell = box(
                    bounds[0] + j * cell_width,
                    bounds[1] + i * cell_height,
                    bounds[0] + (j + 1) * cell_width,
                    bounds[1] + (i + 1) * cell_height
                )
                if shapely_boundary.contains(cell):
                    potential_units.append(cell)
        
        # Select best units based on area and position
        selected_units = []
        target_unit_area = shapely_boundary.area / total_units
        
        while len(selected_units) < total_units and potential_units:
            best_unit = None
            best_score = float('inf')
            
            for unit in potential_units:
                area_diff = abs(unit.area - target_unit_area)
                overlap_penalty = sum(
                    unit.intersection(selected).area 
                    for selected in selected_units
                )
                score = area_diff + overlap_penalty * 2
                
                if score < best_score:
                    best_score = score
                    best_unit = unit
            
            if best_unit:
                selected_units.append(Polygon(best_unit.exterior.coords))
                potential_units.remove(best_unit)
            else:
                break
        
        return selected_units