from django.urls import path
from . import views

app_name = 'route_management'

urlpatterns = [
    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Service Requests
    path('service-requests/', views.ServiceRequestListView.as_view(), name='service_request_list'),
    path('service-requests/create/', views.ServiceRequestCreateView.as_view(), name='service_request_create'),
    path('service-requests/<int:pk>/', views.ServiceRequestDetailView.as_view(), name='service_request_detail'),
    path('service-requests/<int:pk>/update/', views.ServiceRequestUpdateView.as_view(), name='service_request_update'),
    path('service-requests/bulk-add-to-route/', views.BulkAddToRouteView.as_view(), name='bulk_add_to_route'),
    path('service-requests/bulk-update-status/', views.BulkUpdateStatusView.as_view(), name='bulk_update_status'),
    path('service-requests/<int:pk>/duplicate/', views.duplicate_service_request, name='duplicate_service_request'),
    path('service-requests/<int:pk>/cancel/', views.cancel_service_request, name='cancel_service_request'),
    path('get_customer_locations/<int:customer_id>/', views.get_customer_locations, name='get_customer_locations'),
    path('service-requests/<int:pk>/pdf/', views.ServiceRequestPDFView.as_view(), name='service_request_pdf'),

    path('ajax/load-service-locations/', views.ajax_load_service_locations, name='ajax_load_service_locations'),
    path('get-customer-info/', views.get_customer_info, name='get_customer_info'),
    path('get-location-info/', views.get_location_info, name='get_location_info'),

    # Routes
    path('routes/', views.RouteListView.as_view(), name='route_list'),
    path('routes/create/', views.RouteCreateView.as_view(), name='route_create'),
    path('routes/<int:pk>/', views.RouteDetailView.as_view(), name='route_detail'),
    path('routes/<int:pk>/update/', views.RouteUpdateView.as_view(), name='route_update'),
    path('routes/<int:pk>/stops/', views.RouteStopsView.as_view(), name='route_stops'),
    path('routes/<int:pk>/map/', views.RouteMapView.as_view(), name='route_map'),
    path('routes/<int:pk>/optimize/', views.optimize_route, name='optimize_route'),

    # Route Stops
    path('stops/<int:pk>/move/<str:direction>/', views.reorder_stop, name='reorder_stop'),
    path('stops/<int:pk>/remove/', views.remove_stop, name='remove_stop'),
    path('stops/<int:pk>/status/<str:status>/', views.update_stop_status, name='update_stop_status'),

    # Service Completions
    path('completions/create/<int:stop_id>/', views.ServiceCompletionCreateView.as_view(), name='service_completion_create'),

    # Service Photos
    path('photos/upload/<int:service_request_id>/', views.ServicePhotoUploadView.as_view(), name='service_photo_upload'),

    # Technicians
    path('technicians/<int:pk>/schedule/', views.technician_schedule_view, name='technician_schedule'),
    path('technicians/<int:pk>/profile/', views.TechnicianProfileView.as_view(), name='technician_profile'),
    path('technicians/bulk-assign/', views.BulkAssignTechnicianView.as_view(), name='bulk_assign_technician'),


    # Service Areas
    path('service-areas/', views.ServiceAreaListView.as_view(), name='service_area_list'),
    path('service-areas/create/', views.ServiceAreaCreateView.as_view(), name='service_area_create'),

    # Route Schedules
    path('schedules/', views.RouteScheduleListView.as_view(), name='route_schedule_list'),
    path('schedules/<int:pk>/publish/', views.publish_schedule, name='publish_schedule'),
    path('schedules/create/', views.RouteScheduleCreateView.as_view(), name='route_schedule_create'),

    # Calendar
    path('calendar/', views.service_calendar_view, name='service_calendar'),

    # Analytics
    path('analytics/', views.AnalyticsView.as_view(), name='analytics'),

    # Utility functions
    path('geocode-locations/', views.geocode_locations, name='geocode_locations'),
]
