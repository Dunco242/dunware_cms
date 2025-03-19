from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
from django.views.generic.edit import FormView
from django.urls import reverse_lazy, reverse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.utils import timezone
from django.db.models import Q, Count, Avg, Sum, F, ExpressionWrapper, fields
from django.db import transaction, models
from django.template.loader import get_template
from django.db.models.functions import ExtractHour
from weasyprint import HTML, CSS
from django.conf import settings
import tempfile

from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required

from .models import (
    ServiceArea, ServiceLocationType, ServiceLocation, ServiceType, AnalyticsSnapshot,
    ServiceRequest, TechnicianSkill, TechnicianProfile, TechnicianAvailability,
    RouteSchedule, Route, RouteStop, RouteLog, ServiceCompletion,
    ServicePhoto, CustomerNotification, CustomerFeedback, OptimizationSettings, ServicePhotoUpload
)
from .forms import (
    ServiceRequestForm, RouteForm, RouteStopForm, ServiceCompletionForm,
    TechnicianProfileForm, TechnicianAvailabilityForm, CustomerFeedbackForm, BulkUpdateStatusForm,
    OptimizationSettingsForm, ServicePhotoUploadForm, BulkAssignTechnicianForm, BulkAddToRouteForm
)
from core.models import Employee, Customer
from .services.geocoding import GeocodingService
from .services.optimization import RouteOptimizationService
from .services.analytics import AnalyticsService


class DashboardView(LoginRequiredMixin, ListView):
    """Main dashboard view for route management"""
    template_name = 'route_management/dashboard.html'
    context_object_name = 'service_requests'

    def get_queryset(self):
        """Get pending service requests"""
        return ServiceRequest.objects.filter(
            status__in=['pending', 'scheduled']
        ).order_by('preferred_date', 'priority', 'created_at')[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Today's routes
        today = timezone.now().date()
        context['today_routes'] = Route.objects.filter(
            date=today
        ).prefetch_related('stops', 'technician')

        # Technicians on duty today
        context['technicians_on_duty'] = Employee.objects.filter(
            availability__specific_date=today,
            availability__is_available=True
        ).distinct()

        # Pending service requests without routes
        context['unscheduled_requests'] = ServiceRequest.objects.filter(
            status__in=['pending'],
            route_stops__isnull=True
        ).count()

        # Get efficiency metrics
        today_completed_routes = Route.objects.filter(
            date=today,
            status='completed'
        )

        if today_completed_routes.exists():
            context['avg_stops_per_route'] = RouteStop.objects.filter(
                route__in=today_completed_routes
            ).count() / today_completed_routes.count()

            # Get average service duration
            completed_stops = RouteStop.objects.filter(
                route__in=today_completed_routes,
                status='completed',
                actual_arrival_time__isnull=False,
                actual_departure_time__isnull=False
            )

            if completed_stops.exists():
                total_duration = sum([
                    (stop.actual_departure_time - stop.actual_arrival_time).total_seconds() / 60
                    for stop in completed_stops
                ])
                context['avg_service_duration'] = total_duration / completed_stops.count()

        return context


class ServiceRequestListView(LoginRequiredMixin, ListView):
    """List of service requests with filtering options"""
    model = ServiceRequest
    template_name = 'route_management/service_request_list.html'
    context_object_name = 'service_requests'
    paginate_by = 25

    def get_queryset(self):
        queryset = ServiceRequest.objects.all()

        # Filter by status if specified
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Filter by priority if specified
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # Filter by service type if specified
        service_type = self.request.GET.get('service_type')
        if service_type:
            queryset = queryset.filter(service_type_id=service_type)

        # Filter by date range if specified
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(preferred_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(preferred_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(preferred_date__lte=end_date)

        # Search by customer or description
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(customer__company_name__icontains=search) |
                Q(description__icontains=search) |
                Q(service_location__address__icontains=search) |
                Q(request_number__icontains=search)
            )

        return queryset.select_related(
            'customer', 'service_location', 'service_type', 'assigned_technician'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['service_types'] = ServiceType.objects.filter(is_active=True)
        context['filter_form_data'] = {
            'status': self.request.GET.get('status', ''),
            'priority': self.request.GET.get('priority', ''),
            'service_type': self.request.GET.get('service_type', ''),
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'search': self.request.GET.get('search', ''),
        }
        return context


class ServiceRequestDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a service request"""
    model = ServiceRequest
    template_name = 'route_management/service_request_detail.html'
    context_object_name = 'service_request'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service_request = self.get_object()

        # Get route stops associated with this service request
        context['route_stops'] = RouteStop.objects.filter(
            service_request=service_request
        ).select_related('route', 'route__technician')

        # Get service completions
        context['service_completion'] = ServiceCompletion.objects.filter(
            service_request=service_request
        ).first()

        # Get photos
        context['photos'] = ServicePhoto.objects.filter(
            service_request=service_request
        ).order_by('photo_type', '-created_at')

        # Get customer feedback
        context['feedback'] = CustomerFeedback.objects.filter(
            service_request=service_request
        ).first()

        # Get potential technicians for assignment
        if service_request.service_location and service_request.service_location.service_area:
            context['available_technicians'] = Employee.objects.filter(
                service_areas=service_request.service_location.service_area,
                is_active=True
            )

        return context


class ServiceRequestCreateView(LoginRequiredMixin, CreateView):
    """Create a new service request"""
    model = ServiceRequest
    form_class = ServiceRequestForm
    template_name = 'route_management/service_request_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass the user to the form
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Prefill customer if specified in URL
        customer_id = self.request.GET.get('customer')
        if customer_id:
            try:
                # Store the ID, not the object
                initial['customer'] = int(customer_id)
            except ValueError:
                pass

        return initial

    def form_valid(self, form):
        # Set created_by to current user
        form.instance.created_by = self.request.user

        # Save the instance
        response = super().form_valid(form)

        # Show a success message
        messages.success(self.request, f"Service request {self.object.request_number} created successfully.")

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context data needed by the template
        context['customers'] = Customer.objects.filter(is_active=True)
        context['service_types'] = ServiceType.objects.filter(is_active=True)

        # If a customer is preselected, add available service locations
        customer_id = self.request.GET.get('customer')
        if customer_id:
            try:
                context['available_locations'] = ServiceLocation.objects.filter(
                    customer_id=int(customer_id)
                )
            except ValueError:
                pass

        return context

    def get_success_url(self):
        return self.object.get_absolute_url()


class ServiceRequestUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing service request"""
    model = ServiceRequest
    form_class = ServiceRequestForm
    template_name = 'route_management/service_request_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # If we have an existing object, make sure the initial data includes the customer ID
        if self.object:
            initial['customer'] = self.object.customer_id
        return initial

    def form_valid(self, form):
        # Save the form
        response = super().form_valid(form)

        # Show success message
        messages.success(self.request, f"Service request {self.object.request_number} updated successfully.")

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context data needed by the template
        context['customers'] = Customer.objects.filter(is_active=True)
        context['service_types'] = ServiceType.objects.filter(is_active=True)

        # Add available service locations for the current customer
        if self.object and self.object.customer:
            context['available_locations'] = ServiceLocation.objects.filter(
                customer_id=self.object.customer_id
            )

        return context

class RouteListView(LoginRequiredMixin, ListView):
    """List of routes with filtering options"""
    model = Route
    template_name = 'route_management/route_list.html'
    context_object_name = 'routes'
    paginate_by = 20

    def get_queryset(self):
        queryset = Route.objects.all()

        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        else:
            # Default to showing today and future routes
            queryset = queryset.filter(date__gte=timezone.now().date())

        # Filter by technician if specified
        technician_id = self.request.GET.get('technician')
        if technician_id:
            queryset = queryset.filter(technician_id=technician_id)

        # Filter by status if specified
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(route_id__icontains=search) |
                Q(technician__first_name__icontains=search) |
                Q(technician__last_name__icontains=search)
            )

        return queryset.select_related('technician').prefetch_related(
            'stops'
        ).annotate(
            stop_count=Count('stops')
        ).order_by('date', 'estimated_start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['technicians'] = Employee.objects.filter(
            assigned_routes__isnull=False
        ).distinct()

        context['filter_form_data'] = {
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'technician': self.request.GET.get('technician', ''),
            'status': self.request.GET.get('status', ''),
            'search': self.request.GET.get('search', ''),
        }

        # Get today's routes for quick access
        context['today_routes'] = Route.objects.filter(
            date=timezone.now().date()
        ).select_related('technician').prefetch_related('stops')

        return context


class RouteDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a route with map"""
    model = Route
    template_name = 'route_management/route_detail.html'
    context_object_name = 'route'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        route = self.get_object()

        # Get stops in order
        context['stops'] = RouteStop.objects.filter(
            route=route
        ).select_related(
            'service_request',
            'service_request__service_location',
            'service_request__customer',
            'service_request__service_type'
        ).order_by('stop_number')

        # Get route logs
        context['logs'] = RouteLog.objects.filter(
            route=route
        ).order_by('-timestamp')[:30]

        # Calculate metrics
        completed_stops = context['stops'].filter(status='completed').count()
        total_stops = context['stops'].count()
        context['completion_percent'] = (completed_stops / total_stops * 100) if total_stops > 0 else 0

        # Get coordinates for map
        context['map_data'] = self.get_map_data(route, context['stops'])

        return context

    def get_map_data(self, route, stops):
        """Prepare data for the route map"""
        map_data = {
            'center': None,
            'stops': [],
            'route_line': []
        }

        # Start location
        if route.start_latitude and route.start_longitude:
            start_point = {
                'lat': float(route.start_latitude),
                'lng': float(route.start_longitude),
                'name': 'Start: ' + route.start_location,
                'type': 'start'
            }
            map_data['stops'].append(start_point)
            map_data['route_line'].append([float(route.start_latitude), float(route.start_longitude)])

        # Service stops
        for stop in stops:
            location = stop.service_request.service_location
            if location.latitude and location.longitude:
                stop_data = {
                    'lat': float(location.latitude),
                    'lng': float(location.longitude),
                    'name': f"Stop #{stop.stop_number}: {location.name}",
                    'address': location.get_full_address(),
                    'status': stop.status,
                    'scheduled_time': stop.scheduled_arrival_time.strftime('%H:%M') if stop.scheduled_arrival_time else 'TBD',
                    'type': 'stop',
                    'stop_id': stop.id
                }
                map_data['stops'].append(stop_data)
                map_data['route_line'].append([float(location.latitude), float(location.longitude)])

        # End location
        if route.end_latitude and route.end_longitude:
            end_point = {
                'lat': float(route.end_latitude),
                'lng': float(route.end_longitude),
                'name': 'End: ' + route.end_location,
                'type': 'end'
            }
            map_data['stops'].append(end_point)
            map_data['route_line'].append([float(route.end_latitude), float(route.end_longitude)])

        # Find center point for map (average of all coordinates)
        if map_data['stops']:
            lat_sum = sum(float(stop['lat']) for stop in map_data['stops'])
            lng_sum = sum(float(stop['lng']) for stop in map_data['stops'])
            map_data['center'] = {
                'lat': lat_sum / len(map_data['stops']),
                'lng': lng_sum / len(map_data['stops'])
            }

        return map_data


class RouteCreateView(LoginRequiredMixin, CreateView):
    """Create a new route"""
    model = Route
    form_class = RouteForm
    template_name = 'route_management/route_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        # If we have a schedule ID in the URL, pass it to the form
        schedule_id = self.request.GET.get('schedule')
        if schedule_id:
            try:
                schedule = RouteSchedule.objects.get(id=schedule_id)
                kwargs['schedule'] = schedule
            except RouteSchedule.DoesNotExist:
                pass

        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Route {self.object.route_id} created successfully.")

        # If technician_id and date were specified, look for unassigned service requests
        technician = self.object.technician
        route_date = self.object.date

        service_areas = technician.service_areas.all()
        if service_areas:
            # Find unassigned service requests for this technician's areas
            unassigned_requests = ServiceRequest.objects.filter(
                status='pending',
                service_location__service_area__in=service_areas,
                preferred_date=route_date,
                assigned_technician__isnull=True,
                route_stops__isnull=True
            )

            if unassigned_requests.exists():
                messages.info(
                    self.request,
                    f"Found {unassigned_requests.count()} unassigned service requests for this technician's areas."
                )

        return response

    def get_success_url(self):
        return reverse('route_management:route_stops', kwargs={'pk': self.object.pk})


class RouteUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing route"""
    model = Route
    form_class = RouteForm
    template_name = 'route_management/route_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Route {self.object.route_id} updated successfully.")
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()


class RouteStopsView(LoginRequiredMixin, DetailView):
    """View to manage stops for a route"""
    model = Route
    template_name = 'route_management/route_stops.html'
    context_object_name = 'route'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        route = self.get_object()

        # Get existing stops in order
        context['stops'] = RouteStop.objects.filter(
            route=route
        ).select_related(
            'service_request',
            'service_request__service_location',
            'service_request__customer',
            'service_request__service_type'
        ).order_by('stop_number')

        # Get potential service requests for this route
        technician = route.technician
        route_date = route.date

        service_areas = technician.service_areas.all()

        # Find service requests that could be added to this route
        potential_requests = ServiceRequest.objects.filter(
            status__in=['pending', 'scheduled'],
            service_location__service_area__in=service_areas,
            preferred_date=route_date,
            route_stops__isnull=True
        ).select_related(
            'service_location',
            'customer',
            'service_type'
        ).order_by('priority', 'created_at')

        context['potential_requests'] = potential_requests

        # Add form for adding stops
        context['stop_form'] = RouteStopForm(route=route)

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests to add stops"""
        route = self.get_object()
        form = RouteStopForm(request.POST, route=route)

        if form.is_valid():
            stop = form.save(commit=False)
            stop.route = route

            # Set stop number to next available
            next_stop_number = RouteStop.objects.filter(route=route).count() + 1
            stop.stop_number = next_stop_number

            # Save the stop
            stop.save()

            # Update the service request status
            service_request = stop.service_request
            service_request.status = 'scheduled'
            service_request.assigned_technician = route.technician
            service_request.save()

            messages.success(request, f"Stop #{stop.stop_number} added to route.")

            # Reoptimize route if requested
            if 'optimize' in request.POST:
                route.optimize()
                messages.info(request, "Route stops have been reordered for maximum efficiency.")

            return redirect('route_management:route_stops', pk=route.pk)
        else:
            # If form is invalid, show errors
            messages.error(request, "Error adding stop to route. Please check the form.")
            return self.get(request, *args, **kwargs)


@login_required
def optimize_route(request, pk):
    """Optimize the route stops ordering"""
    route = get_object_or_404(Route, pk=pk)

    # Call the optimization service
    try:
        RouteOptimizationService.optimize_route(route)
        messages.success(request, "Route optimized successfully.")
    except Exception as e:
        messages.error(request, f"Error optimizing route: {str(e)}")

    return redirect('route_management:route_stops', pk=route.pk)


@login_required
def reorder_stop(request, pk, direction):
    """Move a stop up or down in the route order"""
    stop = get_object_or_404(RouteStop, pk=pk)
    route = stop.route

    # Get all stops in order
    stops = list(route.stops.all().order_by('stop_number'))
    current_index = next((i for i, s in enumerate(stops) if s.id == stop.id), None)

    if current_index is not None:
        # Calculate target index based on direction
        target_index = current_index - 1 if direction == 'up' else current_index + 1

        # Check if target index is valid
        if 0 <= target_index < len(stops):
            # Swap stop numbers
            stops[current_index].stop_number, stops[target_index].stop_number = \
                stops[target_index].stop_number, stops[current_index].stop_number

            # Save both stops
            stops[current_index].save()
            stops[target_index].save()

            messages.success(request, f"Stop #{stop.stop_number} moved {direction}.")
        else:
            messages.error(request, f"Cannot move stop {direction}.")
    else:
        messages.error(request, "Stop not found in route.")

    return redirect('route_management:route_stops', pk=route.pk)


@login_required
def remove_stop(request, pk):
    """Remove a stop from a route"""
    stop = get_object_or_404(RouteStop, pk=pk)
    route = stop.route
    service_request = stop.service_request
    stop_number = stop.stop_number

    # Delete the stop
    stop.delete()

    # Reorder remaining stops
    for i, remaining_stop in enumerate(route.stops.all().order_by('stop_number'), 1):
        if remaining_stop.stop_number != i:
            remaining_stop.stop_number = i
            remaining_stop.save()

    # Update service request status
    service_request.status = 'pending'
    service_request.assigned_technician = None
    service_request.save()

    messages.success(request, f"Stop #{stop_number} removed from route.")
    return redirect('route_management:route_stops', pk=route.pk)


@login_required
def update_stop_status(request, pk, status):
    """Update the status of a route stop"""
    stop = get_object_or_404(RouteStop, pk=pk)

    if status not in dict(RouteStop.STATUS_CHOICES):
        messages.error(request, f"Invalid status: {status}")
    else:
        stop.update_status(status)
        messages.success(request, f"Stop status updated to {status}.")

    return redirect('route_management:route_detail', pk=stop.route.pk)


class ServiceCompletionCreateView(LoginRequiredMixin, CreateView):
    """Create a service completion record"""
    model = ServiceCompletion
    form_class = ServiceCompletionForm
    template_name = 'route_management/service_completion_form.html'

    def get_initial(self):
        initial = super().get_initial()

        # Get route stop ID from URL
        stop_id = self.kwargs.get('stop_id')
        if stop_id:
            try:
                stop = RouteStop.objects.get(pk=stop_id)
                initial['route_stop'] = stop
                initial['service_request'] = stop.service_request

                # Set initial start/end times based on actual arrival/departure
                if stop.actual_arrival_time:
                    initial['start_time'] = stop.actual_arrival_time

                if stop.actual_departure_time:
                    initial['end_time'] = stop.actual_departure_time
                elif stop.actual_arrival_time:
                    # Default to current time if we have arrival but no departure
                    initial['end_time'] = timezone.now()

                # Calculate duration if we have both times
                if initial.get('start_time') and initial.get('end_time'):
                    duration = (initial['end_time'] - initial['start_time']).total_seconds() / 60
                    initial['duration_minutes'] = int(duration)
                    initial['billable_hours'] = round(duration / 60, 2)

                # Set customer contact info
                sr = stop.service_request
                if sr.contact_name:
                    initial['customer_name'] = sr.contact_name
                else:
                    initial['customer_name'] = sr.customer.primary_contact_name

                if sr.contact_email:
                    initial['customer_email'] = sr.contact_email
                else:
                    initial['customer_email'] = sr.customer.email

            except RouteStop.DoesNotExist:
                pass

        return initial

    def form_valid(self, form):
        response = super().form_valid(form)

        # Update route stop status
        route_stop = self.object.route_stop
        route_stop.update_status('completed')

        # Update service request status
        service_request = self.object.service_request
        service_request.status = 'completed'
        service_request.completed_at = timezone.now()
        service_request.save()

        messages.success(self.request, "Service completion recorded successfully.")

        # Send email to customer if requested
        if 'send_email' in self.request.POST:
            try:
                # Create notification
                notification = CustomerNotification.objects.create(
                    service_request=service_request,
                    route_stop=route_stop,
                    notification_type='service_complete',
                    delivery_method='email',
                    recipient_name=self.object.customer_name,
                    recipient_contact=self.object.customer_email,
                    subject=f"Service Completion: {service_request.service_type.name}",
                    message=f"Your service has been completed. Details: {self.object.work_performed}"
                )

                # Send immediately
                notification.send()
                messages.success(self.request, f"Completion notification sent to {self.object.customer_email}")
            except Exception as e:
                messages.error(self.request, f"Error sending notification: {str(e)}")

        return response

    def get_success_url(self):
        return reverse('route_management:route_detail', kwargs={'pk': self.object.route_stop.route.pk})


class ServicePhotoUploadView(LoginRequiredMixin, FormView):
    """View to upload service photos"""
    template_name = 'route_management/service_photo_upload.html'
    form_class = ServicePhotoUploadForm

    def get_initial(self):
        initial = super().get_initial()

        # Get service request ID from URL
        service_request_id = self.kwargs.get('service_request_id')
        if service_request_id:
            initial['service_request'] = service_request_id

        return initial

    def form_valid(self, form):
        service_request = form.cleaned_data['service_request']
        photo_type = form.cleaned_data['photo_type']
        caption = form.cleaned_data['caption']
        notes = form.cleaned_data['notes']

        # Process each uploaded image
        for image_file in self.request.FILES.getlist('images'):
            photo = ServicePhoto(
                service_request=service_request,
                image=image_file,
                photo_type=photo_type,
                caption=caption,
                notes=notes,
                taken_at=timezone.now(),
                uploaded_by=self.request.user
            )
            photo.save()

        messages.success(self.request, f"{len(self.request.FILES.getlist('images'))} photos uploaded successfully.")
        return redirect('route_management:service_request_detail', pk=service_request.pk)


@login_required
def service_calendar_view(request):
    """Calendar view of service requests and routes"""
    # Get date range from request or default to current month
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Create calendar data
    import calendar
    cal = calendar.monthcalendar(year, month)

    # Get first and last day of month
    first_day = timezone.datetime(year, month, 1).date()
    last_day = (timezone.datetime(year, month, 1) + timezone.timedelta(days=32)).replace(day=1).date() - timezone.timedelta(days=1)

    # Get service requests for this month
    service_requests = ServiceRequest.objects.filter(
        preferred_date__gte=first_day,
        preferred_date__lte=last_day
    ).select_related('service_type', 'customer')

    # Get routes for this month
    routes = Route.objects.filter(
        date__gte=first_day,
        date__lte=last_day
    ).select_related('technician')

    # Build calendar data
    calendar_data = []
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                # Day outside current month
                week_data.append({
                    'day': None,
                    'service_requests': [],
                    'routes': []
                })
            else:
                current_date = timezone.datetime(year, month, day).date()
                day_service_requests = [sr for sr in service_requests if sr.preferred_date == current_date]
                day_routes = [r for r in routes if r.date == current_date]

                week_data.append({
                    'day': day,
                    'date': current_date,
                    'is_today': current_date == today,
                    'service_requests': day_service_requests,
                    'routes': day_routes
                })
        calendar_data.append(week_data)

    # Get previous and next month links
    prev_month = timezone.datetime(year, month, 1) - timezone.timedelta(days=1)
    next_month = timezone.datetime(year, month, 28) + timezone.timedelta(days=5)

    context = {
        'calendar_data': calendar_data,
        'month_name': timezone.datetime(year, month, 1).strftime('%B'),
        'year': year,
        'prev_month_link': f'?year={prev_month.year}&month={prev_month.month}',
        'next_month_link': f'?year={next_month.year}&month={next_month.month}',
        'service_types': ServiceType.objects.filter(is_active=True)
    }

    return render(request, 'route_management/service_calendar.html', context)


class TechnicianProfileView(LoginRequiredMixin, DetailView):
    """View technician profile details"""
    model = TechnicianProfile
    template_name = 'route_management/technician_profile.html'
    context_object_name = 'profile'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()

        # Get upcoming routes
        today = timezone.now().date()
        context['upcoming_routes'] = Route.objects.filter(
            technician=profile.employee,
            date__gte=today
        ).order_by('date')[:10]

        # Get recent service completions
        context['recent_completions'] = ServiceCompletion.objects.filter(
            route_stop__route__technician=profile.employee
        ).order_by('-end_time')[:10]

        # Get availability schedule
        context['weekly_availability'] = TechnicianAvailability.objects.filter(
            technician=profile.employee,
            day_of_week__isnull=False
        ).order_by('day_of_week', 'start_time')

        context['specific_availability'] = TechnicianAvailability.objects.filter(
            technician=profile.employee,
            specific_date__isnull=False,
            specific_date__gte=today
        ).order_by('specific_date', 'start_time')

        return context


class RouteMapView(LoginRequiredMixin, DetailView):
    """Full-screen map view of a route"""
    model = Route
    template_name = 'route_management/route_map.html'
    context_object_name = 'route'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        route = self.get_object()

        # Get stops in order
        stops = RouteStop.objects.filter(
            route=route
        ).select_related(
            'service_request',
            'service_request__service_location'
        ).order_by('stop_number')

        # Prepare map data
        map_data = {
            'center': None,
            'stops': [],
            'route_line': []
        }

        # Start location
        if route.start_latitude and route.start_longitude:
            start_point = {
                'lat': float(route.start_latitude),
                'lng': float(route.start_longitude),
                'name': 'Start: ' + route.start_location,
                'type': 'start'
            }
            map_data['stops'].append(start_point)
            map_data['route_line'].append([float(route.start_latitude), float(route.start_longitude)])

        # Service stops
        for stop in stops:
            location = stop.service_request.service_location
            if location.latitude and location.longitude:
                stop_data = {
                    'lat': float(location.latitude),
                    'lng': float(location.longitude),
                    'name': f"Stop #{stop.stop_number}: {location.name}",
                    'address': location.get_full_address(),
                    'status': stop.status,
                    'scheduled_time': stop.scheduled_arrival_time.strftime('%H:%M') if stop.scheduled_arrival_time else 'TBD',
                    'service_type': stop.service_request.service_type.name,
                    'customer': stop.service_request.customer.company_name,
                    'type': 'stop',
                    'stop_id': stop.id
                }
                map_data['stops'].append(stop_data)
                map_data['route_line'].append([float(location.latitude), float(location.longitude)])

        # End location
        if route.end_latitude and route.end_longitude:
            end_point = {
                'lat': float(route.end_latitude),
                'lng': float(route.end_longitude),
                'name': 'End: ' + route.end_location,
                'type': 'end'
            }
            map_data['stops'].append(end_point)
            map_data['route_line'].append([float(route.end_latitude), float(route.end_longitude)])

        # Find center point for map (average of all coordinates)
        if map_data['stops']:
            lat_sum = sum(float(stop['lat']) for stop in map_data['stops'])
            lng_sum = sum(float(stop['lng']) for stop in map_data['stops'])
            map_data['center'] = {
                'lat': lat_sum / len(map_data['stops']),
                'lng': lng_sum / len(map_data['stops'])
            }

        context['map_data'] = map_data
        context['api_key'] = settings.HERE_MAPS_API_KEY

        return context


class RouteScheduleListView(LoginRequiredMixin, ListView):
    """List view of route schedules"""
    model = RouteSchedule
    template_name = 'route_management/route_schedule_list.html'
    context_object_name = 'schedules'
    paginate_by = 20

    def get_queryset(self):
        queryset = RouteSchedule.objects.all()

        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        else:
            # Default to showing recent and upcoming schedules
            today = timezone.now().date()
            month_ago = today - timezone.timedelta(days=30)
            queryset = queryset.filter(date__gte=month_ago)

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search))

        return queryset.select_related(
            'created_by'
        ).annotate(
            route_count=Count('routes')
        ).order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form_data'] = {
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'search': self.request.GET.get('search', ''),
        }
        return context


@login_required
def publish_schedule(request, pk):
    """Publish a route schedule and all its routes"""
    schedule = get_object_or_404(RouteSchedule, pk=pk)

    # Check if there are routes in this schedule
    if not schedule.routes.exists():
        messages.error(request, "Cannot publish a schedule with no routes.")
        return redirect('route_management:route_schedule_detail', pk=schedule.pk)

    # Publish the schedule
    schedule.publish()

    # Publish all routes in the schedule
    for route in schedule.routes.all():
        route.status = 'published'
        route.save()

        # Update service requests to scheduled
        for stop in route.stops.all():
            service_request = stop.service_request
            service_request.status = 'scheduled'
            service_request.scheduled_start_time = timezone.datetime.combine(
                route.date,
                stop.scheduled_arrival_time if stop.scheduled_arrival_time else timezone.now().time()
            )
            service_request.save()

    # Send notifications to technicians
    technicians = set(route.technician for route in schedule.routes.all())

    for technician in technicians:
        routes = schedule.routes.filter(technician=technician)
        route_count = routes.count()
        stop_count = RouteStop.objects.filter(route__in=routes).count()

        # Create notification for each technician
        email = technician.user.email if hasattr(technician, 'user') and technician.user else technician.email

        if email:
            CustomerNotification.objects.create(
                notification_type='appointment_scheduled',
                delivery_method='email',
                recipient_name=technician.get_full_name(),
                recipient_contact=email,
                subject=f"New Route Schedule for {schedule.date}",
                message=f"You have been assigned {route_count} routes with a total of {stop_count} stops for {schedule.date}. Please check your schedule.",
                status='pending',
                scheduled_time=timezone.now()
            )

    messages.success(request, f"Schedule published successfully with {schedule.routes.count()} routes.")
    return redirect('route_management:route_schedule_detail', pk=schedule.pk)


class ServiceAreaListView(LoginRequiredMixin, ListView):
    """List view of service areas"""
    model = ServiceArea
    template_name = 'route_management/service_area_list.html'
    context_object_name = 'service_areas'

    def get_queryset(self):
        queryset = ServiceArea.objects.prefetch_related('technicians')

        # Filter by active status
        active_only = self.request.GET.get('active_only') == 'on'
        if active_only:
            queryset = queryset.filter(is_active=True)

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.annotate(
            location_count=Count('locations', distinct=True),
            technician_count=Count('technicians', distinct=True)
        ).order_by('name')


class AnalyticsView(LoginRequiredMixin, TemplateView):
    """View for analytics dashboard"""
    template_name = 'route_management/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get date range from GET parameters or use default (last 30 days)
        today = timezone.now().date()
        end_date = self.request.GET.get('end_date')
        end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else today

        start_date = self.request.GET.get('start_date')
        start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else (end_date - timezone.timedelta(days=30))

        # Get completed routes for date range
        completed_routes = Route.objects.filter(
            date__range=[start_date, end_date],
            status='completed'
        )

        # Get completed service requests for date range
        completed_service_requests = ServiceRequest.objects.filter(
            completed_at__date__range=[start_date, end_date],
            status='completed'
        )

        # Calculate route metrics
        route_count = completed_routes.count()

        # Calculate average stops per route - explicitly set output_field
        from django.db.models import FloatField
        if route_count > 0:
            avg_stops_per_route = RouteStop.objects.filter(
                route__in=completed_routes
            ).count() / route_count
        else:
            avg_stops_per_route = 0

        # Get average service duration with explicit output_field
        completed_stops = RouteStop.objects.filter(
            route__in=completed_routes,
            status='completed',
            actual_arrival_time__isnull=False,
            actual_departure_time__isnull=False
        )

        avg_service_duration = 0
        if completed_stops.exists():
            # Calculate duration for each stop manually to avoid field type issues
            total_duration = 0
            count = 0
            for stop in completed_stops:
                if stop.actual_departure_time and stop.actual_arrival_time:
                    duration = (stop.actual_departure_time - stop.actual_arrival_time).total_seconds() / 60
                    total_duration += duration
                    count += 1

            if count > 0:
                avg_service_duration = total_duration / count

        # Get average customer rating
        customer_feedback = CustomerFeedback.objects.filter(
            service_request__in=completed_service_requests
        )

        avg_rating = 0
        if customer_feedback.exists():
            # Use aggregate with explicit output_field
            avg_rating_result = customer_feedback.aggregate(
                avg_rating=models.Avg('rating', output_field=FloatField())
            )
            avg_rating = avg_rating_result['avg_rating'] or 0

        # Prepare data points by day
        date_range = (end_date - start_date).days + 1
        daily_data = []

        for i in range(date_range):
            current_date = start_date + timezone.timedelta(days=i)

            # Get routes completed on this day
            day_routes = completed_routes.filter(date=current_date)
            day_route_count = day_routes.count()

            # Get service requests completed on this day
            day_requests = completed_service_requests.filter(completed_at__date=current_date)
            day_request_count = day_requests.count()

            # Get day's average stops per route
            day_avg_stops = 0
            if day_route_count > 0:
                day_stops = RouteStop.objects.filter(route__in=day_routes).count()
                day_avg_stops = day_stops / day_route_count

            # Get day's average service duration
            day_completed_stops = RouteStop.objects.filter(
                route__in=day_routes,
                status='completed',
                actual_arrival_time__isnull=False,
                actual_departure_time__isnull=False
            )

            day_avg_duration = 0
            if day_completed_stops.exists():
                # Calculate duration for each stop manually
                day_total_duration = 0
                day_stop_count = 0
                for stop in day_completed_stops:
                    if stop.actual_departure_time and stop.actual_arrival_time:
                        duration = (stop.actual_departure_time - stop.actual_arrival_time).total_seconds() / 60
                        day_total_duration += duration
                        day_stop_count += 1

                if day_stop_count > 0:
                    day_avg_duration = day_total_duration / day_stop_count

            # Get day's average customer rating
            day_feedback = CustomerFeedback.objects.filter(
                service_request__in=day_requests
            )

            day_avg_rating = 0
            if day_feedback.exists():
                # Use aggregate with explicit output_field
                day_avg_rating_result = day_feedback.aggregate(
                    avg_rating=models.Avg('rating', output_field=FloatField())
                )
                day_avg_rating = day_avg_rating_result['avg_rating'] or 0

            # Add data point
            daily_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'completed_routes': day_route_count,
                'completed_requests': day_request_count,
                'avg_stops_per_route': day_avg_stops,
                'avg_service_duration': day_avg_duration,
                'avg_customer_rating': day_avg_rating
            })

        # Extract data for charts
        dates = [item['date'] for item in daily_data]
        completed_routes_data = [item['completed_routes'] for item in daily_data]
        avg_stops_data = [item['avg_stops_per_route'] for item in daily_data]
        avg_duration_data = [item['avg_service_duration'] for item in daily_data]
        avg_rating_data = [item['avg_customer_rating'] for item in daily_data]

        # Add context data
        context.update({
            'chart_dates': dates,
            'chart_completed_routes': completed_routes_data,
            'chart_avg_stops_per_route': avg_stops_data,
            'chart_avg_service_duration': avg_duration_data,
            'chart_avg_customer_rating': avg_rating_data,
            'start_date': start_date,
            'end_date': end_date,

            # Summary metrics
            'total_completed_routes': route_count,
            'total_completed_service_requests': completed_service_requests.count(),
            'avg_stops_per_route': round(avg_stops_per_route, 2),
            'avg_service_duration': round(avg_service_duration, 1),
            'avg_rating': round(avg_rating, 2),
            'date_range_days': date_range,
        })

        return context



@login_required
def technician_schedule_view(request, pk):
    """View a technician's weekly schedule"""
    employee = get_object_or_404(Employee, pk=pk)

    # Get date range from GET parameters or use current week
    today = timezone.now().date()
    week_start = today - timezone.timedelta(days=today.weekday())
    week_end = week_start + timezone.timedelta(days=6)

    start_date = request.GET.get('start_date')
    if start_date:
        try:
            start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
            # Adjust to start of week (Monday)
            week_start = start_date - timezone.timedelta(days=start_date.weekday())
            week_end = week_start + timezone.timedelta(days=6)
        except ValueError:
            pass

    # Get technician's routes for this week
    routes = Route.objects.filter(
        technician=employee,
        date__range=[week_start, week_end]
    ).prefetch_related('stops').order_by('date', 'estimated_start_time')

    # Get technician's weekly availability
    weekly_availability = TechnicianAvailability.objects.filter(
        technician=employee,
        day_of_week__isnull=False
    ).order_by('day_of_week', 'start_time')

    # Get any specific date availability for this week
    specific_availability = TechnicianAvailability.objects.filter(
        technician=employee,
        specific_date__range=[week_start, week_end]
    ).order_by('specific_date', 'start_time')

    # Build schedule for each day
    schedule = []
    for i in range(7):
        day_date = week_start + timezone.timedelta(days=i)
        day_name = day_date.strftime('%A')

        # Get routes for this day
        day_routes = [r for r in routes if r.date == day_date]

        # Get availability for this day (either weekly or specific)
        day_availability = [a for a in weekly_availability if a.day_of_week == i]
        day_specific = [a for a in specific_availability if a.specific_date == day_date]

        # If there's specific availability for this day, it overrides weekly
        availability = day_specific if day_specific else day_availability

        schedule.append({
            'date': day_date,
            'day_name': day_name,
            'is_today': day_date == today,
            'routes': day_routes,
            'availability': availability,
            'is_available': any(a.is_available for a in availability) if availability else False
        })

    # Previous and next week links
    prev_week = week_start - timezone.timedelta(days=7)
    next_week = week_start + timezone.timedelta(days=7)

    context = {
        'employee': employee,
        'schedule': schedule,
        'week_start': week_start,
        'week_end': week_end,
        'prev_week': prev_week,
        'next_week': next_week,
        'has_technician_profile': hasattr(employee, 'technician_profile'),
        'total_stops_this_week': sum(route.stops.count() for route in routes),
        'total_routes_this_week': len(routes)
    }

    # Get profile if it exists
    if hasattr(employee, 'technician_profile'):
        context['profile'] = employee.technician_profile

    return render(request, 'route_management/technician_schedule.html', context)


@login_required
def geocode_locations(request):
    """Bulk geocode service locations that don't have coordinates"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)

    # Get locations that need geocoding
    locations = ServiceLocation.objects.filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    )

    if not locations.exists():
        messages.info(request, "No locations need geocoding.")
        return JsonResponse({'success': True, 'message': 'No locations need geocoding'})

    # Limit to processing max 50 at a time to avoid timeout
    locations = locations[:50]

    # Process each location
    success_count = 0
    error_count = 0

    for location in locations:
        try:
            success = GeocodingService.geocode_location(location)
            if success:
                success_count += 1
            else:
                error_count += 1
        except Exception:
            error_count += 1

    # Return results
    messages.success(request, f"Geocoded {success_count} locations successfully. {error_count} had errors.")
    return JsonResponse({
        'success': True,
        'success_count': success_count,
        'error_count': error_count,
        'remaining': ServiceLocation.objects.filter(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        ).count()
    })

@login_required
def service_calendar_view(request):
    """Calendar view of service requests and routes"""
    # Get date range from request or default to current month
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Create calendar data
    import calendar
    cal = calendar.monthcalendar(year, month)

    # Get first and last day of month
    first_day = timezone.datetime(year, month, 1).date()
    last_day = (timezone.datetime(year, month, 1) + timezone.timedelta(days=32)).replace(day=1).date() - timezone.timedelta(days=1)

    # Get service requests for this month
    service_requests = ServiceRequest.objects.filter(
        preferred_date__gte=first_day,
        preferred_date__lte=last_day
    ).select_related('service_type', 'customer')

    # Get routes for this month
    routes = Route.objects.filter(
        date__gte=first_day,
        date__lte=last_day
    ).select_related('technician')

    # Build calendar data
    calendar_data = []
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                # Day outside current month
                week_data.append({
                    'day': None,
                    'service_requests': [],
                    'routes': []
                })
            else:
                current_date = timezone.datetime(year, month, day).date()
                day_service_requests = [sr for sr in service_requests if sr.preferred_date == current_date]
                day_routes = [r for r in routes if r.date == current_date]

                week_data.append({
                    'day': day,
                    'date': current_date,
                    'is_today': current_date == today,
                    'service_requests': day_service_requests,
                    'routes': day_routes
                })
        calendar_data.append(week_data)

    # Get previous and next month links
    prev_month = timezone.datetime(year, month, 1) - timezone.timedelta(days=1)
    next_month = timezone.datetime(year, month, 28) + timezone.timedelta(days=5)

    context = {
        'calendar_data': calendar_data,
        'month_name': timezone.datetime(year, month, 1).strftime('%B'),
        'year': year,
        'prev_month_link': f'?year={prev_month.year}&month={prev_month.month}',
        'next_month_link': f'?year={next_month.year}&month={next_month.month}',
        'service_types': ServiceType.objects.filter(is_active=True)
    }

    return render(request, 'route_management/service_calendar.html', context)


class TechnicianProfileView(LoginRequiredMixin, DetailView):
    """View technician profile details"""
    model = TechnicianProfile
    template_name = 'route_management/technician_profile.html'
    context_object_name = 'profile'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()

        # Get upcoming routes
        today = timezone.now().date()
        context['upcoming_routes'] = Route.objects.filter(
            technician=profile.employee,
            date__gte=today
        ).order_by('date')[:10]

        # Get recent service completions
        context['recent_completions'] = ServiceCompletion.objects.filter(
            route_stop__route__technician=profile.employee
        ).order_by('-end_time')[:10]

        # Get availability schedule
        context['weekly_availability'] = TechnicianAvailability.objects.filter(
            technician=profile.employee,
            day_of_week__isnull=False
        ).order_by('day_of_week', 'start_time')

        context['specific_availability'] = TechnicianAvailability.objects.filter(
            technician=profile.employee,
            specific_date__isnull=False,
            specific_date__gte=today
        ).order_by('specific_date', 'start_time')

        return context


class RouteMapView(LoginRequiredMixin, DetailView):
    """Full-screen map view of a route with robust geocoding"""
    model = Route
    template_name = 'route_management/route_map.html'
    context_object_name = 'route'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        route = self.get_object()

        # Print debug info
        print(f"RouteMapView: Processing Route #{route.id}")
        print(f"Route start: {route.start_location}, coords: {route.start_latitude}, {route.start_longitude}")
        print(f"Route end: {route.end_location}, coords: {route.end_latitude}, {route.end_longitude}")

        # Attempt geocoding if needed
        geocoding_performed = self.attempt_geocoding(route)
        if geocoding_performed:
            messages.info(self.request, "Some locations were automatically geocoded.")

        # Get stops in order
        stops = RouteStop.objects.filter(
            route=route
        ).select_related(
            'service_request',
            'service_request__service_location',
            'service_request__service_type',
            'service_request__customer'
        ).order_by('stop_number')

        print(f"Found {stops.count()} stops for this route")

        # Prepare map data
        map_data = {
            'center': None,
            'stops': [],
            'route_line': []
        }

        # Track valid points for debugging
        valid_point_count = 0

        # Start location
        if route.start_latitude and route.start_longitude:
            try:
                start_point = {
                    'lat': float(route.start_latitude),
                    'lng': float(route.start_longitude),
                    'name': 'Start: ' + route.start_location,
                    'type': 'start'
                }
                map_data['stops'].append(start_point)
                map_data['route_line'].append([float(route.start_latitude), float(route.start_longitude)])
                valid_point_count += 1
                print(f"Added start point: {route.start_latitude}, {route.start_longitude}")
            except (ValueError, TypeError) as e:
                print(f"Error adding start point: {str(e)}")

        # Service stops
        for stop in stops:
            location = stop.service_request.service_location
            if location.latitude and location.longitude:
                try:
                    stop_data = {
                        'lat': float(location.latitude),
                        'lng': float(location.longitude),
                        'name': f"Stop #{stop.stop_number}: {location.name}",
                        'address': location.get_full_address(),
                        'status': stop.status,
                        'scheduled_time': stop.scheduled_arrival_time.strftime('%H:%M') if stop.scheduled_arrival_time else 'TBD',
                        'service_type': stop.service_request.service_type.name,
                        'customer': stop.service_request.customer.company_name,
                        'type': 'stop',
                        'stop_id': stop.id,
                        'service_request_id': stop.service_request.id
                    }
                    map_data['stops'].append(stop_data)
                    map_data['route_line'].append([float(location.latitude), float(location.longitude)])
                    valid_point_count += 1
                    print(f"Added stop #{stop.stop_number} point: {location.latitude}, {location.longitude}")
                except (ValueError, TypeError) as e:
                    print(f"Error adding stop #{stop.stop_number} point: {str(e)}")

        # End location
        if route.end_latitude and route.end_longitude:
            try:
                end_point = {
                    'lat': float(route.end_latitude),
                    'lng': float(route.end_longitude),
                    'name': 'End: ' + route.end_location,
                    'type': 'end'
                }
                map_data['stops'].append(end_point)
                map_data['route_line'].append([float(route.end_latitude), float(route.end_longitude)])
                valid_point_count += 1
                print(f"Added end point: {route.end_latitude}, {route.end_longitude}")
            except (ValueError, TypeError) as e:
                print(f"Error adding end point: {str(e)}")

        # Find center point for map (average of all coordinates)
        if map_data['stops']:
            try:
                lat_sum = sum(float(stop['lat']) for stop in map_data['stops'])
                lng_sum = sum(float(stop['lng']) for stop in map_data['stops'])
                map_data['center'] = {
                    'lat': lat_sum / len(map_data['stops']),
                    'lng': lng_sum / len(map_data['stops'])
                }
                print(f"Map center calculated: {map_data['center']}")
            except (ValueError, TypeError) as e:
                print(f"Error calculating map center: {str(e)}")
                # Fallback to New York coordinates as default
                map_data['center'] = {'lat': 40.7128, 'lng': -74.0060}
                print("Using fallback map center")
        else:
            # Fallback center if no points are available
            print("No valid map points, using fallback center")
            map_data['center'] = {'lat': 40.7128, 'lng': -74.0060}  # New York coordinates

        # Calculate completion percentage
        completed_stops = stops.filter(status='completed').count()
        total_stops = stops.count()
        context['completion_percent'] = (completed_stops / total_stops * 100) if total_stops > 0 else 0

        # Add map data to context
        context['map_data'] = map_data
        context['stops'] = stops

        # Add the HERE Maps API key
        context['here_maps_api_key'] = settings.HERE_MAPS_API_KEY
        print(f"HERE Maps API key present: {bool(settings.HERE_MAPS_API_KEY)}")

        # Check for any missing coordinates
        missing_coordinates = self.check_missing_coordinates(route, stops)
        context['missing_coordinates'] = missing_coordinates
        if missing_coordinates:
            print(f"Missing coordinates detected: {len(missing_coordinates)} locations")
            for location in missing_coordinates:
                print(f"- {location}")

        # Final validation
        print(f"Map data summary: center={bool(map_data['center'])}, points={len(map_data['stops'])}, valid_points={valid_point_count}")

        return context

    def attempt_geocoding(self, route):
        """Simplified geocoding that doesn't use temporary ServiceLocation objects"""
        geocoding_performed = False

        # Geocode route start location
        if route.start_location and (not route.start_latitude or not route.start_longitude):
            try:
                print(f"Geocoding start location: {route.start_location}")
                from .services.geocoding import GeocodingService
                coords = GeocodingService.get_coordinates(route.start_location)
                if coords:
                    route.start_latitude = coords['lat']
                    route.start_longitude = coords['lng']
                    route.save(update_fields=['start_latitude', 'start_longitude'])
                    geocoding_performed = True
                    print(f"Successfully geocoded start location: {coords}")
            except Exception as e:
                print(f"Error geocoding start location: {str(e)}")

        # Geocode route end location
        if route.end_location and (not route.end_latitude or not route.end_longitude):
            try:
                print(f"Geocoding end location: {route.end_location}")
                from .services.geocoding import GeocodingService
                coords = GeocodingService.get_coordinates(route.end_location)
                if coords:
                    route.end_latitude = coords['lat']
                    route.end_longitude = coords['lng']
                    route.save(update_fields=['end_latitude', 'end_longitude'])
                    geocoding_performed = True
                    print(f"Successfully geocoded end location: {coords}")
            except Exception as e:
                print(f"Error geocoding end location: {str(e)}")

        # For existing stops, use the original method
        for stop in RouteStop.objects.filter(route=route).select_related('service_request__service_location'):
            location = stop.service_request.service_location
            if not location.latitude or not location.longitude:
                try:
                    print(f"Geocoding stop location: {location.get_full_address()}")
                    success = GeocodingService.geocode_location(location)
                    if success:
                        geocoding_performed = True
                except Exception as e:
                    print(f"Error geocoding stop location: {str(e)}")

        return geocoding_performed
    def check_missing_coordinates(self, route, stops):
        """Check for any missing coordinates that would prevent the map from displaying properly"""
        missing = []

        # Check route start coordinates
        if route.start_location and (not route.start_latitude or not route.start_longitude):
            missing.append(f"Start location: {route.start_location}")

        # Check route end coordinates
        if route.end_location and (not route.end_latitude or not route.end_longitude):
            missing.append(f"End location: {route.end_location}")

        # Check stop coordinates
        for stop in stops:
            location = stop.service_request.service_location
            if not location.latitude or not location.longitude:
                missing.append(f"Stop #{stop.stop_number}: {location.name}")

        return missing

class RouteScheduleListView(LoginRequiredMixin, ListView):
    """List view of route schedules"""
    model = RouteSchedule
    template_name = 'route_management/route_schedule_list.html'
    context_object_name = 'schedules'
    paginate_by = 20

    def get_queryset(self):
        queryset = RouteSchedule.objects.all()

        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        else:
            # Default to showing recent and upcoming schedules
            today = timezone.now().date()
            month_ago = today - timezone.timedelta(days=30)
            queryset = queryset.filter(date__gte=month_ago)

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search))

        return queryset.select_related(
            'created_by'
        ).annotate(
            route_count=Count('routes')
        ).order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form_data'] = {
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'search': self.request.GET.get('search', ''),
        }
        return context


@login_required
def publish_schedule(request, pk):
    """Publish a route schedule and all its routes"""
    schedule = get_object_or_404(RouteSchedule, pk=pk)

    # Check if there are routes in this schedule
    if not schedule.routes.exists():
        messages.error(request, "Cannot publish a schedule with no routes.")
        return redirect('route_management:route_schedule_detail', pk=schedule.pk)

    # Publish the schedule
    schedule.publish()

    # Publish all routes in the schedule
    for route in schedule.routes.all():
        route.status = 'published'
        route.save()

        # Update service requests to scheduled
        for stop in route.stops.all():
            service_request = stop.service_request
            service_request.status = 'scheduled'
            service_request.scheduled_start_time = timezone.datetime.combine(
                route.date,
                stop.scheduled_arrival_time if stop.scheduled_arrival_time else timezone.now().time()
            )
            service_request.save()

    # Send notifications to technicians
    technicians = set(route.technician for route in schedule.routes.all())

    for technician in technicians:
        routes = schedule.routes.filter(technician=technician)
        route_count = routes.count()
        stop_count = RouteStop.objects.filter(route__in=routes).count()

        # Create notification for each technician
        email = technician.user.email if hasattr(technician, 'user') and technician.user else technician.email

        if email:
            CustomerNotification.objects.create(
                notification_type='appointment_scheduled',
                delivery_method='email',
                recipient_name=technician.get_full_name(),
                recipient_contact=email,
                subject=f"New Route Schedule for {schedule.date}",
                message=f"You have been assigned {route_count} routes with a total of {stop_count} stops for {schedule.date}. Please check your schedule.",
                status='pending',
                scheduled_time=timezone.now()
            )

    messages.success(request, f"Schedule published successfully with {schedule.routes.count()} routes.")
    return redirect('route_management:route_schedule_detail', pk=schedule.pk)


class ServiceAreaListView(LoginRequiredMixin, ListView):
    """List view of service areas"""
    model = ServiceArea
    template_name = 'route_management/service_area_list.html'
    context_object_name = 'service_areas'

    def get_queryset(self):
        queryset = ServiceArea.objects.prefetch_related('technicians')

        # Filter by active status
        active_only = self.request.GET.get('active_only') == 'on'
        if active_only:
            queryset = queryset.filter(is_active=True)

        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.annotate(
            location_count=Count('locations', distinct=True),
            technician_count=Count('technicians', distinct=True)
        ).order_by('name')


class AnalyticsView(LoginRequiredMixin, TemplateView):
    """View for analytics dashboard"""
    template_name = 'route_management/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get date range from GET parameters or use default (last 30 days)
        today = timezone.now().date()
        end_date = self.request.GET.get('end_date')
        end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else today

        start_date = self.request.GET.get('start_date')
        start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else (end_date - timezone.timedelta(days=30))

        # Get analytics snapshots for date range
        snapshots = AnalyticsSnapshot.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')

        # If no snapshots exist, generate them
        if not snapshots.exists():
            date_range = (end_date - start_date).days + 1
            if date_range <= 90:  # Limit to generating max 90 days of data
                for i in range(date_range):
                    current_date = start_date + timezone.timedelta(days=i)
                    AnalyticsSnapshot.generate_for_date(current_date)

                # Fetch the newly generated snapshots
                snapshots = AnalyticsSnapshot.objects.filter(
                    date__range=[start_date, end_date]
                ).order_by('date')

        # Prepare data for charts
        dates = [snapshot.date.strftime('%Y-%m-%d') for snapshot in snapshots]
        completed_routes = [snapshot.completed_routes for snapshot in snapshots]
        avg_stops_per_route = [float(snapshot.avg_stops_per_route) for snapshot in snapshots]
        avg_service_duration = [float(snapshot.avg_service_duration_minutes) for snapshot in snapshots]
        avg_customer_rating = [float(snapshot.avg_customer_rating) if snapshot.avg_customer_rating else 0 for snapshot in snapshots]

        # Calculate summary metrics
        if snapshots:
            total_completed_routes = sum(snapshot.completed_routes for snapshot in snapshots)
            total_completed_service_requests = sum(snapshot.completed_service_requests for snapshot in snapshots)
            avg_rating = sum(avg_customer_rating) / len(avg_customer_rating) if any(avg_customer_rating) else 0

            context.update({
                'total_completed_routes': total_completed_routes,
                'total_completed_service_requests': total_completed_service_requests,
                'avg_rating': round(avg_rating, 2),
                'date_range_days': (end_date - start_date).days + 1,
            })

        # Add chart data to context
        context.update({
            'chart_dates': dates,
            'chart_completed_routes': completed_routes,
            'chart_avg_stops_per_route': avg_stops_per_route,
            'chart_avg_service_duration': avg_service_duration,
            'chart_avg_customer_rating': avg_customer_rating,
            'start_date': start_date,
            'end_date': end_date,
        })

        return context


@login_required
def technician_schedule_view(request, pk):
    """View a technician's weekly schedule"""
    employee = get_object_or_404(Employee, pk=pk)

    # Get date range from GET parameters or use current week
    today = timezone.now().date()
    week_start = today - timezone.timedelta(days=today.weekday())
    week_end = week_start + timezone.timedelta(days=6)

    start_date = request.GET.get('start_date')
    if start_date:
        try:
            start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
            # Adjust to start of week (Monday)
            week_start = start_date - timezone.timedelta(days=start_date.weekday())
            week_end = week_start + timezone.timedelta(days=6)
        except ValueError:
            pass

    # Get technician's routes for this week
    routes = Route.objects.filter(
        technician=employee,
        date__range=[week_start, week_end]
    ).prefetch_related('stops').order_by('date', 'estimated_start_time')

    # Get technician's weekly availability
    weekly_availability = TechnicianAvailability.objects.filter(
        technician=employee,
        day_of_week__isnull=False
    ).order_by('day_of_week', 'start_time')

    # Get any specific date availability for this week
    specific_availability = TechnicianAvailability.objects.filter(
        technician=employee,
        specific_date__range=[week_start, week_end]
    ).order_by('specific_date', 'start_time')

    # Build schedule for each day
    schedule = []
    for i in range(7):
        day_date = week_start + timezone.timedelta(days=i)
        day_name = day_date.strftime('%A')

        # Get routes for this day
        day_routes = [r for r in routes if r.date == day_date]

        # Get availability for this day (either weekly or specific)
        day_availability = [a for a in weekly_availability if a.day_of_week == i]
        day_specific = [a for a in specific_availability if a.specific_date == day_date]

        # If there's specific availability for this day, it overrides weekly
        availability = day_specific if day_specific else day_availability

        schedule.append({
            'date': day_date,
            'day_name': day_name,
            'is_today': day_date == today,
            'routes': day_routes,
            'availability': availability,
            'is_available': any(a.is_available for a in availability) if availability else False
        })

    # Previous and next week links
    prev_week = week_start - timezone.timedelta(days=7)
    next_week = week_start + timezone.timedelta(days=7)

    context = {
        'employee': employee,
        'schedule': schedule,
        'week_start': week_start,
        'week_end': week_end,
        'prev_week': prev_week,
        'next_week': next_week,
        'has_technician_profile': hasattr(employee, 'technician_profile'),
        'total_stops_this_week': sum(route.stops.count() for route in routes),
        'total_routes_this_week': len(routes)
    }

    # Get profile if it exists
    if hasattr(employee, 'technician_profile'):
        context['profile'] = employee.technician_profile

    return render(request, 'route_management/technician_schedule.html', context)


@login_required
def geocode_locations(request):
    """Bulk geocode service locations that don't have coordinates"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)

    # Get locations that need geocoding
    locations = ServiceLocation.objects.filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    )

    if not locations.exists():
        messages.info(request, "No locations need geocoding.")
        return JsonResponse({'success': True, 'message': 'No locations need geocoding'})

    # Limit to processing max 50 at a time to avoid timeout
    locations = locations[:50]

    # Process each location
    success_count = 0
    error_count = 0

    for location in locations:
        try:
            success = GeocodingService.geocode_location(location)
            if success:
                success_count += 1
            else:
                error_count += 1
        except Exception:
            error_count += 1

    # Return results
    messages.success(request, f"Geocoded {success_count} locations successfully. {error_count} had errors.")
    return JsonResponse({
        'success': True,
        'success_count': success_count,
        'error_count': error_count,
        'remaining': ServiceLocation.objects.filter(
            Q(latitude__isnull=True) | Q(longitude__isnull=True)
        ).count()
    })


class RouteScheduleCreateView(LoginRequiredMixin, CreateView):
    """Create a new route schedule"""
    model = RouteSchedule
    template_name = 'route_management/route_schedule_create.html'
    fields = ['name', 'date', 'description', 'notes']

    def form_valid(self, form):
        # Set created_by to current user
        form.instance.created_by = self.request.user
        form.instance.status = 'draft'

        response = super().form_valid(form)
        messages.success(self.request, f"Route schedule '{self.object.name}' created successfully.")
        return response

    def get_success_url(self):
        return reverse('route_management:route_schedule_detail', kwargs={'pk': self.object.pk})


class BulkAssignTechnicianView(LoginRequiredMixin, FormView):
    """View to bulk assign technicians to service requests"""
    template_name = 'route_management/bulk_assign_technician.html'
    form_class = BulkAssignTechnicianForm  # You'll need to create this form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters from GET request
        service_area_id = self.request.GET.get('service_area')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        status = self.request.GET.get('status', 'pending')

        # Build queryset based on filters
        queryset = ServiceRequest.objects.filter(status=status)

        if service_area_id:
            queryset = queryset.filter(service_location__service_area_id=service_area_id)

        if start_date and end_date:
            queryset = queryset.filter(preferred_date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(preferred_date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(preferred_date__lte=end_date)

        # Get the service requests
        context['service_requests'] = queryset.select_related(
            'customer', 'service_location', 'service_type'
        ).order_by('preferred_date', 'priority')

        # Get available technicians
        context['technicians'] = Employee.objects.filter(
            is_active=True,
            service_areas__isnull=False
        ).distinct()

        # Get service areas for filter
        context['service_areas'] = ServiceArea.objects.filter(is_active=True)

        # Pass filter values to template
        context['filter_values'] = {
            'service_area': service_area_id,
            'start_date': start_date,
            'end_date': end_date,
            'status': status,
        }

        return context

    def form_valid(self, form):
        technician_id = form.cleaned_data['technician']
        service_request_ids = form.cleaned_data['service_requests'].split(',')

        try:
            technician = Employee.objects.get(pk=technician_id)

            # Update each service request
            success_count = 0
            for req_id in service_request_ids:
                if req_id:
                    try:
                        service_request = ServiceRequest.objects.get(pk=req_id)
                        service_request.assigned_technician = technician
                        service_request.save()
                        success_count += 1
                    except ServiceRequest.DoesNotExist:
                        continue

            messages.success(
                self.request,
                f"Successfully assigned {success_count} service requests to {technician.get_full_name()}"
            )

        except Employee.DoesNotExist:
            messages.error(self.request, "Selected technician not found.")
            return self.form_invalid(form)

        return super().form_valid(form)

    def get_success_url(self):
        # Preserve filter parameters in redirect
        params = {
            'service_area': self.request.GET.get('service_area', ''),
            'start_date': self.request.GET.get('start_date', ''),
            'end_date': self.request.GET.get('end_date', ''),
            'status': self.request.GET.get('status', 'pending'),
        }

        base_url = reverse('route_management:bulk_assign_technician')
        query_string = '&'.join([f"{k}={v}" for k, v in params.items() if v])

        if query_string:
            return f"{base_url}?{query_string}"
        return base_url


class ServiceAreaCreateView(LoginRequiredMixin, CreateView):
    """Create a new service area"""
    model = ServiceArea
    template_name = 'route_management/service_area_form.html'
    fields = ['name', 'description', 'code', 'is_active', 'notes']

    def form_valid(self, form):
        # Set created_by to current user if the field exists
        if hasattr(form.instance, 'created_by'):
            form.instance.created_by = self.request.user

        response = super().form_valid(form)
        messages.success(self.request, f"Service area '{self.object.name}' created successfully.")
        return response

    def get_success_url(self):
        return reverse('route_management:service_area_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Service Area'
        context['submit_text'] = 'Create'
        return context


class BulkAddToRouteView(LoginRequiredMixin, FormView):
    """View to bulk add service requests to a route"""
    template_name = 'route_management/bulk_add_to_route.html'
    form_class = BulkAddToRouteForm  # You'll need to create this form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get selected service request IDs from the request
        service_request_ids = self.request.GET.get('service_requests', '').split(',')
        service_request_ids = [id for id in service_request_ids if id.strip().isdigit()]

        if not service_request_ids:
            messages.warning(self.request, "No service requests selected. Please select at least one service request.")
            return context

        # Get the service requests
        context['service_requests'] = ServiceRequest.objects.filter(
            id__in=service_request_ids
        ).select_related(
            'customer', 'service_location', 'service_type'
        )

        # Get available routes
        # By default, show routes for the next 7 days
        today = timezone.now().date()
        next_week = today + timezone.timedelta(days=7)

        context['routes'] = Route.objects.filter(
            date__range=[today, next_week],
            status__in=['draft', 'published']
        ).select_related('technician').order_by('date', 'estimated_start_time')

        # We'll also need a way to create a new route
        context['technicians'] = Employee.objects.filter(
            is_active=True,
            service_areas__isnull=False
        ).distinct()

        return context

    def form_valid(self, form):
        route_id = form.cleaned_data.get('route')
        service_request_ids = form.cleaned_data.get('service_requests', '').split(',')
        service_request_ids = [id for id in service_request_ids if id.strip().isdigit()]

        if not service_request_ids:
            messages.error(self.request, "No service requests selected.")
            return self.form_invalid(form)

        try:
            route = Route.objects.get(pk=route_id)

            # Get current max stop number for this route
            max_stop_number = RouteStop.objects.filter(route=route).aggregate(
                max_stop=models.Max('stop_number')
            )['max_stop'] or 0

            # Add each service request as a stop
            success_count = 0
            error_count = 0

            for i, req_id in enumerate(service_request_ids, 1):
                try:
                    service_request = ServiceRequest.objects.get(pk=req_id)

                    # Create a new route stop
                    stop = RouteStop(
                        route=route,
                        service_request=service_request,
                        stop_number=max_stop_number + i,
                        status='pending'
                    )
                    stop.save()

                    # Update service request status
                    service_request.status = 'scheduled'
                    service_request.assigned_technician = route.technician
                    service_request.save()

                    success_count += 1
                except Exception as e:
                    error_count += 1
                    messages.error(self.request, f"Error adding service request #{req_id}: {str(e)}")

            if success_count > 0:
                messages.success(
                    self.request,
                    f"Successfully added {success_count} service requests to route {route.route_id}."
                )

                # Redirect to route stops page
                return HttpResponseRedirect(reverse('route_management:route_stops', kwargs={'pk': route.pk}))

        except Route.DoesNotExist:
            messages.error(self.request, "Selected route not found.")
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f"Error: {str(e)}")
            return self.form_invalid(form)

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('route_management:service_request_list')


class BulkUpdateStatusView(LoginRequiredMixin, FormView):
    """View to bulk update status for multiple service requests"""
    template_name = 'route_management/bulk_update_status.html'
    form_class = BulkUpdateStatusForm  # We'll create this form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get selected service request IDs from the request
        service_request_ids = self.request.GET.get('service_requests', '').split(',')
        service_request_ids = [id for id in service_request_ids if id.strip().isdigit()]

        if not service_request_ids:
            messages.warning(self.request, "No service requests selected. Please select at least one service request.")
            return context

        # Get the service requests
        context['service_requests'] = ServiceRequest.objects.filter(
            id__in=service_request_ids
        ).select_related(
            'customer', 'service_location', 'service_type'
        )

        return context

    def form_valid(self, form):
        new_status = form.cleaned_data.get('status')
        notes = form.cleaned_data.get('notes', '')
        service_request_ids = form.cleaned_data.get('service_requests', '').split(',')
        service_request_ids = [id for id in service_request_ids if id.strip().isdigit()]

        if not service_request_ids:
            messages.error(self.request, "No service requests selected.")
            return self.form_invalid(form)

        try:
            # Update each service request
            success_count = 0
            for req_id in service_request_ids:
                try:
                    service_request = ServiceRequest.objects.get(pk=req_id)

                    # Store old status for logging
                    old_status = service_request.status

                    # Update the status
                    service_request.status = new_status

                    # Add notes if provided
                    if notes:
                        service_request.notes = (service_request.notes or '') + f"\n\n{timezone.now().strftime('%Y-%m-%d %H:%M')}: Status changed from {old_status} to {new_status}. {notes}"

                    service_request.save()

                    # Create activity log entry
                    # Assuming you have an activity log model, you could create an entry here

                    success_count += 1
                except ServiceRequest.DoesNotExist:
                    messages.error(self.request, f"Service request #{req_id} not found.")
                except Exception as e:
                    messages.error(self.request, f"Error updating service request #{req_id}: {str(e)}")

            if success_count > 0:
                messages.success(
                    self.request,
                    f"Successfully updated status for {success_count} service requests to '{new_status}'."
                )

                # Redirect to service request list
                return HttpResponseRedirect(reverse('route_management:service_request_list'))

        except Exception as e:
            messages.error(self.request, f"Error: {str(e)}")
            return self.form_invalid(form)

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('route_management:service_request_list')


class ServiceAreaUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing service area"""
    model = ServiceArea
    template_name = 'route_management/service_area_form.html'
    fields = ['name', 'description', 'code', 'is_active', 'notes']

    def form_valid(self, form):
        # Set modified_by to current user if the field exists
        if hasattr(form.instance, 'modified_by'):
            form.instance.modified_by = self.request.user

        response = super().form_valid(form)
        messages.success(self.request, f"Service area '{self.object.name}' updated successfully.")
        return response

    def get_success_url(self):
        return reverse('route_management:service_area_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Update Service Area'
        context['submit_text'] = 'Update'
        return context


@login_required
def load_service_locations(request):
    """AJAX view to load service locations for a customer"""
    customer_id = request.GET.get('customer_id')

    if not customer_id:
        return JsonResponse({'error': 'No customer ID provided'}, status=400)

    try:
        # Get all service locations for this customer
        locations = ServiceLocation.objects.filter(
            customer_id=customer_id
        ).values('id', 'name', 'address', 'city', 'state', 'zip_code')

        # Return as JSON
        return JsonResponse(list(locations), safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def duplicate_service_request(request, pk):
    """Duplicate an existing service request"""
    original_request = get_object_or_404(ServiceRequest, pk=pk)

    if request.method == 'POST':
        # Create a new service request based on the original
        new_request = ServiceRequest(
            customer=original_request.customer,
            service_location=original_request.service_location,
            service_type=original_request.service_type,
            description=original_request.description,
            priority=original_request.priority,
            preferred_date=request.POST.get('preferred_date') or timezone.now().date(),
            preferred_time_start=original_request.preferred_time_start,
            preferred_time_end=original_request.preferred_time_end,
            contact_name=original_request.contact_name,
            contact_phone=original_request.contact_phone,
            contact_email=original_request.contact_email,
            created_by=request.user
        )
        new_request.save()

        messages.success(request, f"Service request duplicated successfully. New request number: {new_request.request_number}")
        return redirect('route_management:service_request_detail', pk=new_request.pk)

    # GET request - show confirmation form
    return render(request, 'route_management/duplicate_service_request.html', {
        'original_request': original_request,
        'suggested_date': timezone.now().date() + timezone.timedelta(days=1)  # Suggest tomorrow as default
    })


@login_required
def ajax_load_service_locations(request):
    """AJAX view to load service locations for a customer"""
    customer_id = request.GET.get('customer_id')

    if not customer_id:
        return JsonResponse([], safe=False)

    try:
        locations = ServiceLocation.objects.filter(
            customer_id=customer_id
        ).values('id', 'name')

        # For debugging, log the number of locations found
        print(f"Found {len(locations)} locations for customer ID {customer_id}")

        return JsonResponse(list(locations), safe=False)
    except Exception as e:
        print(f"Error loading service locations: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def get_customer_info(request):
    """AJAX view to get customer information"""
    customer_id = request.GET.get('customer_id')

    if not customer_id:
        return JsonResponse({'success': False, 'error': 'No customer ID provided'})

    try:
        customer = Customer.objects.get(id=customer_id)

        # Return customer details
        return JsonResponse({
            'success': True,
            'customer': {
                'id': customer.id,
                'company_name': customer.company_name,
                'contact_name': customer.primary_contact_name,
                'contact_email': customer.email,
                'contact_phone': customer.phone
            }
        })
    except Customer.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Customer not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def cancel_service_request(request, pk):
    """Cancel a service request"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)

    try:
        service_request = get_object_or_404(ServiceRequest, pk=pk)

        # Check if the request can be cancelled
        if service_request.status == 'cancelled':
            return JsonResponse({'error': 'This request is already cancelled'}, status=400)

        # Update the status
        service_request.status = 'cancelled'
        service_request.cancelled_at = timezone.now()
        service_request.save()

        # Log the cancellation
        if hasattr(service_request, 'notes'):
            service_request.notes = (service_request.notes or '') + f"\n\n{timezone.now().strftime('%Y-%m-%d %H:%M')}: Cancelled by {request.user.get_full_name() or request.user.username}"
            service_request.save(update_fields=['notes'])

        # Return success
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_location_info(request):
    """AJAX view to get service location information"""
    location_id = request.GET.get('location_id')

    if not location_id:
        return JsonResponse({'success': False, 'error': 'No location ID provided'})

    try:
        location = ServiceLocation.objects.get(id=location_id)

        # Return location details
        return JsonResponse({
            'success': True,
            'location': {
                'id': location.id,
                'name': location.name,
                'address_line1': location.address,
                'address_line2': location.address_line2,
                'city': location.city,
                'state': location.state,
                'zip_code': location.zip_code,
                'latitude': float(location.latitude) if location.latitude else None,
                'longitude': float(location.longitude) if location.longitude else None
            }
        })
    except ServiceLocation.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Location not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def get_customer_locations(request, customer_id):
    """AJAX view to get service locations for a customer"""
    if not customer_id:
        return JsonResponse([], safe=False)

    try:
        locations = ServiceLocation.objects.filter(
            customer_id=customer_id
        ).values('id', 'name')

        # For debugging, log the number of locations found
        print(f"Found {len(locations)} locations for customer ID {customer_id}")

        return JsonResponse(list(locations), safe=False)
    except Exception as e:
        print(f"Error loading service locations: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


class ServiceRequestPDFView(LoginRequiredMixin, View):
    """Generate PDF for a service request using WeasyPrint"""

    def get(self, request, pk):
        # Get the service request
        service_request = get_object_or_404(ServiceRequest, pk=pk)

        # Get related data
        route_stops = RouteStop.objects.filter(
            service_request=service_request
        ).select_related('route', 'route__technician')

        service_completion = ServiceCompletion.objects.filter(
            service_request=service_request
        ).first()

        photos = ServicePhoto.objects.filter(
            service_request=service_request
        ).order_by('photo_type', '-created_at')

        feedback = CustomerFeedback.objects.filter(
            service_request=service_request
        ).first()

        # Render template to string
        template = get_template('route_management/service_request_pdf.html')
        html_string = template.render({
            'service_request': service_request,
            'route_stops': route_stops,
            'service_completion': service_completion,
            'photos': photos,
            'feedback': feedback,
            'now': timezone.now(),
        })

        # Create PDF using WeasyPrint
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="service_request_{service_request.request_number}.pdf"'

        # Create PDF
        html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
        html.write_pdf(response)

        return response


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'core/customer_detail.html'
    context_object_name = 'customer'


@login_required
def assign_technician_to_service_request(request, pk):
    """Assign a technician to a service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)

    if request.method == 'POST':
        technician_id = request.POST.get('technician_id')
        notify_technician = 'notify_technician' in request.POST
        notify_customer = 'notify_customer' in request.POST

        if technician_id:
            try:
                technician = Employee.objects.get(pk=technician_id)

                # Update service request
                service_request.assigned_technician = technician
                service_request.save()

                # Send notifications if requested
                if notify_technician:
                    # Logic to notify technician
                    pass

                if notify_customer:
                    # Logic to notify customer
                    pass

                messages.success(request, f"Technician {technician.get_full_name()} assigned to service request successfully.")
            except Employee.DoesNotExist:
                messages.error(request, "Selected technician not found.")
        else:
            messages.error(request, "No technician selected.")

    return redirect('route_management:service_request_detail', pk=service_request.pk)


@login_required
def request_feedback_for_service_request(request, pk):
    """Send a feedback request to the customer for a service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)

    if request.method == 'POST':
        recipient_name = request.POST.get('recipient_name')
        recipient_email = request.POST.get('recipient_email')
        feedback_message = request.POST.get('feedback_message', '')

        if recipient_email:
            try:
                # Create a notification for feedback request
                notification = CustomerNotification.objects.create(
                    service_request=service_request,
                    notification_type='feedback_request',
                    delivery_method='email',
                    recipient_name=recipient_name,
                    recipient_contact=recipient_email,
                    subject=f"Feedback Request for Service #{service_request.request_number}",
                    message=f"We would appreciate your feedback regarding the recent service. {feedback_message}",
                    status='pending',
                    scheduled_time=timezone.now()
                )

                # Send the notification
                success = notification.send()

                if success:
                    messages.success(request, f"Feedback request sent to {recipient_email}")
                else:
                    messages.error(request, "Error sending feedback request. Please try again.")

            except Exception as e:
                messages.error(request, f"Error requesting feedback: {str(e)}")
        else:
            messages.error(request, "Recipient email is required")

    return redirect('route_management:service_request_detail', pk=service_request.pk)


@login_required
def cancel_service_request(request, pk):
    """Cancel a service request"""
    service_request = get_object_or_404(ServiceRequest, pk=pk)

    if request.method == 'POST':
        # Get form data
        cancellation_reason = request.POST.get('cancellation_reason', '')
        notify_technician = 'notify_technician' in request.POST
        notify_customer = 'notify_customer' in request.POST

        # Update the service request
        service_request.status = 'cancelled'
        service_request.cancelled_at = timezone.now()
        service_request.save()

        # Log the cancellation if we have a notes field
        if hasattr(service_request, 'notes'):
            service_request.notes = (service_request.notes or '') + f"\n\n{timezone.now().strftime('%Y-%m-%d %H:%M')}: Cancelled by {request.user.get_full_name() or request.user.username}\nReason: {cancellation_reason}"
            service_request.save(update_fields=['notes'])

        # Send notifications if requested
        if notify_technician and service_request.assigned_technician:
            # Logic to notify technician
            pass

        if notify_customer:
            # Logic to notify customer
            pass

        messages.success(request, "Service request cancelled successfully.")

    return redirect('route_management:service_request_detail', pk=service_request.pk)
