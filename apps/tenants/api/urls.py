from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TenantViewSet

app_name = 'tenants'

router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')

urlpatterns = [
    # Base router URLs
    path('', include(router.urls)),

    # Custom tenant management endpoints
    path('tenants/<int:pk>/assign/', 
         TenantViewSet.as_view({'post': 'assign_tenant'}),
         name='assign-tenant'),
    
    path('tenants/<int:pk>/vacate/',
         TenantViewSet.as_view({'post': 'vacate_tenant'}),
         name='vacate-tenant'),
    
    # History and documents
    path('tenants/<int:pk>/history/',
         TenantViewSet.as_view({'get': 'occupancy_history'}),
         name='tenant-history'),
    
    path('tenants/<int:pk>/documents/',
         TenantViewSet.as_view({'get': 'documents', 'post': 'upload_document'}),
         name='tenant-documents'),
    
    # Notes management
    path('tenants/<int:pk>/notes/',
         TenantViewSet.as_view({'get': 'notes', 'post': 'add_note'}),
         name='tenant-notes'),
    
    # Communication endpoints
    path('tenants/<int:pk>/send-reminder/',
         TenantViewSet.as_view({'post': 'send_reminder'}),
         name='send-reminder'),
]

# The router automatically creates the following URLs:
# GET /tenants/ - List all tenants (with filtering)
# POST /tenants/ - Create a new tenant
# GET /tenants/{id}/ - Retrieve a tenant
# PUT /tenants/{id}/ - Update a tenant
# PATCH /tenants/{id}/ - Partially update a tenant
# DELETE /tenants/{id}/ - Delete a tenant

# Full list of available endpoints:
AVAILABLE_ENDPOINTS = """
List of available endpoints:

Tenant Management:
GET     /api/v1/tenants/                    - List all tenants
POST    /api/v1/tenants/                    - Create new tenant
GET     /api/v1/tenants/{id}/              - Get tenant details
PUT     /api/v1/tenants/{id}/              - Update tenant details
PATCH   /api/v1/tenants/{id}/              - Partial update tenant
DELETE  /api/v1/tenants/{id}/              - Delete tenant

Tenant Assignment:
POST    /api/v1/tenants/{id}/assign/       - Assign tenant to unit

Tenant Vacation:
POST    /api/v1/tenants/{id}/vacate/       - Process tenant vacation

History and Documents:
GET     /api/v1/tenants/{id}/history/      - Get tenant occupancy history
GET     /api/v1/tenants/{id}/documents/    - List tenant documents
POST    /api/v1/tenants/{id}/documents/    - Upload tenant document

Notes Management:
GET     /api/v1/tenants/{id}/notes/        - List tenant notes
POST    /api/v1/tenants/{id}/notes/        - Add tenant note

Communication:
POST    /api/v1/tenants/{id}/send-reminder/ - Send reminder to tenant

Query Parameters for GET /tenants/:
- search: Search by name, phone, or email
- status: Filter by tenant status
- property: Filter by property ID
- payment_status: Filter by payment status
- ordering: Sort by created_at, full_name, status
- page: Page number for pagination
- page_size: Number of items per page
"""

# Add the router's URLs to our urlpatterns
urlpatterns += router.urls