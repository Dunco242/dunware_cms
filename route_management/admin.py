from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import (
    ServiceArea, ServiceLocationType, ServiceLocation, ServiceType,
    ServiceRequest, TechnicianSkill, TechnicianProfile, TechnicianAvailability,
    RouteSchedule, Route, RouteStop, RouteLog, ServiceCompletion,
    ServicePhoto, CustomerNotification, CustomerFeedback, OptimizationSettings,
    GeocodeCache, DistanceMatrixCache, AnalyticsSnapshot
)


@admin.register(ServiceArea)
class ServiceAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'technician_count', 'location_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    filter_horizontal = ('technicians',)

    def technician_count(self, obj):
        return obj.technicians.count()
    technician_count.short_description = 'Technicians'

    def location_count(self, obj):
        return obj.locations.count()
    location_count.short_description = 'Locations'


@admin.register(ServiceLocationType)
class ServiceLocationTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')


@admin.register(ServiceLocation)
class ServiceLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'customer', 'city', 'state', 'service_area', 'has_coordinates', 'is_active')
    list_filter = ('is_active', 'service_area', 'location_type')
    search_fields = ('name', 'address', 'city', 'customer__company_name')
    raw_id_fields = ('customer', 'service_area')
    readonly_fields = ('created_at', 'updated_at')

    def has_coordinates(self, obj):
        return bool(obj.latitude and obj.longitude)
    has_coordinates.boolean = True
    has_coordinates.short_description = 'Geocoded'


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'estimated_duration_minutes', 'base_price', 'requires_certification', 'is_active')
    list_filter = ('is_active', 'requires_certification')
    search_fields = ('name', 'description')


class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    raw_id_fields = ('service_request',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ('request_number', 'customer', 'service_type', 'priority', 'status', 'preferred_date', 'assigned_technician')
    list_filter = ('status', 'priority', 'service_type', 'preferred_date')
    search_fields = ('request_number', 'description', 'customer__company_name')
    raw_id_fields = ('customer', 'service_location', 'assigned_technician', 'created_by')
    readonly_fields = ('request_number', 'created_at', 'updated_at', 'completed_at', 'cancelled_at')
    date_hierarchy = 'preferred_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('request_number', 'customer', 'service_location', 'service_type', 'description')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority')
        }),
        ('Scheduling', {
            'fields': ('preferred_date', 'preferred_time_start', 'preferred_time_end', 'estimated_duration_minutes',
                      'assigned_technician', 'scheduled_start_time', 'scheduled_end_time')
        }),
        ('Contact Information', {
            'fields': ('contact_name', 'contact_phone', 'contact_email')
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'updated_at', 'completed_at', 'cancelled_at')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'customer', 'service_location', 'service_type', 'assigned_technician'
        )


@admin.register(TechnicianSkill)
class TechnicianSkillAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')


@admin.register(TechnicianProfile)
class TechnicianProfileAdmin(admin.ModelAdmin):
    list_display = ('employee', 'get_skills', 'max_travel_distance_miles', 'last_location_update')
    list_filter = ('skills',)
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email')
    filter_horizontal = ('skills',)

    def get_skills(self, obj):
        return ", ".join([skill.name for skill in obj.skills.all()])
    get_skills.short_description = 'Skills'


@admin.register(TechnicianAvailability)
class TechnicianAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('technician', 'get_day_display', 'start_time', 'end_time', 'is_available')
    list_filter = ('is_available', 'day_of_week')
    search_fields = ('technician__first_name', 'technician__last_name')

    def get_day_display(self, obj):
        if obj.specific_date:
            return obj.specific_date.strftime('%Y-%m-%d')
        else:
            return obj.get_day_of_week_display()
    get_day_display.short_description = 'Day'


@admin.register(RouteSchedule)
class RouteScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'route_count', 'is_published', 'published_at', 'created_by')
    list_filter = ('is_published', 'date')
    search_fields = ('name',)
    readonly_fields = ('published_at', 'created_at', 'updated_at')

    def route_count(self, obj):
        return obj.routes.count()
    route_count.short_description = 'Routes'


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('route_id', 'name', 'technician', 'date', 'status', 'stop_count', 'is_optimized')
    list_filter = ('status', 'date', 'is_optimized')
    search_fields = ('route_id', 'name', 'technician__first_name', 'technician__last_name')
    raw_id_fields = ('schedule', 'technician')
    readonly_fields = ('route_id', 'created_at', 'updated_at', 'optimization_timestamp')
    date_hierarchy = 'date'
    inlines = [RouteStopInline]

    def stop_count(self, obj):
        return obj.stops.count()
    stop_count.short_description = 'Stops'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('technician', 'schedule')


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ('id', 'route_link', 'stop_number', 'service_request_link', 'status', 'scheduled_arrival_time')
    list_filter = ('status', 'route__date')
    search_fields = ('route__route_id', 'service_request__request_number')
    raw_id_fields = ('route', 'service_request')
    readonly_fields = ('created_at', 'updated_at', 'actual_arrival_time', 'actual_departure_time')

    def route_link(self, obj):
        url = reverse('admin:route_management_route_change', args=[obj.route.id])
        return format_html('<a href="{}">{}</a>', url, obj.route.route_id)
    route_link.short_description = 'Route'

    def service_request_link(self, obj):
        url = reverse('admin:route_management_servicerequest_change', args=[obj.service_request.id])
        return format_html('<a href="{}">{}</a>', url, obj.service_request.request_number)
    service_request_link.short_description = 'Service Request'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('route', 'service_request')


@admin.register(RouteLog)
class RouteLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'route', 'log_type', 'message', 'logged_by')
    list_filter = ('log_type', 'timestamp', 'route__date')
    search_fields = ('message', 'route__route_id')
    raw_id_fields = ('route', 'route_stop', 'logged_by')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'


@admin.register(ServiceCompletion)
class ServiceCompletionAdmin(admin.ModelAdmin):
    list_display = ('service_request', 'start_time', 'end_time', 'duration_minutes', 'billable_hours', 'total_amount')
    search_fields = ('service_request__request_number', 'work_performed')
    raw_id_fields = ('route_stop', 'service_request', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('before_photos', 'after_photos')
    date_hierarchy = 'end_time'


@admin.register(ServicePhoto)
class ServicePhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'service_request', 'photo_type', 'taken_at', 'image_preview')
    list_filter = ('photo_type', 'taken_at')
    search_fields = ('service_request__request_number', 'caption', 'notes')
    raw_id_fields = ('service_request', 'uploaded_by')
    readonly_fields = ('created_at', 'updated_at', 'image_preview')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Preview'


@admin.register(CustomerNotification)
class CustomerNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'notification_type', 'delivery_method', 'recipient_name', 'status', 'sent_time')
    list_filter = ('notification_type', 'delivery_method', 'status', 'sent_time')
    search_fields = ('recipient_name', 'recipient_contact', 'subject', 'message')
    raw_id_fields = ('service_request', 'route_stop')
    readonly_fields = ('created_at', 'updated_at', 'sent_time', 'delivery_time')
    date_hierarchy = 'created_at'


@admin.register(CustomerFeedback)
class CustomerFeedbackAdmin(admin.ModelAdmin):
    list_display = ('service_request', 'overall_rating', 'would_recommend', 'submitted_at', 'wants_follow_up')
    list_filter = ('overall_rating', 'would_recommend', 'wants_follow_up', 'submitted_at')
    search_fields = ('service_request__request_number', 'comments', 'submitted_by')
    raw_id_fields = ('service_request',)
    readonly_fields = ('submitted_at',)
    date_hierarchy = 'submitted_at'


@admin.register(OptimizationSettings)
class OptimizationSettingsAdmin(admin.ModelAdmin):
    list_display = ('name', 'prioritize', 'max_stops_per_route', 'is_default')
    list_filter = ('prioritize', 'is_default')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(GeocodeCache)
class GeocodeCacheAdmin(admin.ModelAdmin):
    list_display = ('address', 'latitude', 'longitude', 'created_at')
    search_fields = ('address', 'formatted_address')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(DistanceMatrixCache)
class DistanceMatrixCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'origin_coordinates', 'destination_coordinates', 'travel_mode', 'distance_meters', 'duration_seconds')
    list_filter = ('travel_mode',)
    readonly_fields = ('created_at', 'updated_at')

    def origin_coordinates(self, obj):
        return f"({obj.origin_latitude}, {obj.origin_longitude})"
    origin_coordinates.short_description = 'Origin'

    def destination_coordinates(self, obj):
        return f"({obj.destination_latitude}, {obj.destination_longitude})"
    destination_coordinates.short_description = 'Destination'


@admin.register(AnalyticsSnapshot)
class AnalyticsSnapshotAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_routes', 'completed_routes', 'avg_stops_per_route', 'avg_customer_rating')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')
