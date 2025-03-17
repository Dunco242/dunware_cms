from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import (
    ServiceArea, ServiceLocationType, ServiceLocation, ServiceType,
    ServiceRequest, TechnicianSkill, TechnicianProfile, TechnicianAvailability,
    RouteSchedule, Route, RouteStop, RouteLog, ServiceCompletion,
    ServicePhoto, ServicePhotoUpload, CustomerNotification, CustomerFeedback, OptimizationSettings
)
from core.models import Employee, Customer

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(f) for f in data]
        else:
            result = single_file_clean(data)
        return result

class ServiceRequestForm(forms.ModelForm):
    """Form for creating and updating service requests"""

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Make certain fields optional
        self.fields['preferred_date'].required = True
        self.fields['priority'].widget = forms.RadioSelect(choices=ServiceRequest.PRIORITY_CHOICES)

        # Filter service locations based on selected customer
        if 'customer' in self.data:
            try:
                customer_id = int(self.data.get('customer'))
                self.fields['service_location'].queryset = ServiceLocation.objects.filter(
                    customer_id=customer_id
                )
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.customer:
            self.fields['service_location'].queryset = ServiceLocation.objects.filter(
                customer=self.instance.customer
            )
        else:
            self.fields['service_location'].queryset = ServiceLocation.objects.none()

    class Meta:
        model = ServiceRequest
        fields = [
            'customer', 'service_location', 'service_type', 'description',
            'priority', 'preferred_date', 'preferred_time_start', 'preferred_time_end',
            'estimated_duration_minutes', 'contact_name', 'contact_phone', 'contact_email',
            'assigned_technician'
        ]
        widgets = {
            'preferred_date': forms.DateInput(attrs={'type': 'date'}),
            'preferred_time_start': forms.TimeInput(attrs={'type': 'time'}),
            'preferred_time_end': forms.TimeInput(attrs={'type': 'time'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Check that preferred time range makes sense
        start_time = cleaned_data.get('preferred_time_start')
        end_time = cleaned_data.get('preferred_time_end')

        if start_time and end_time and start_time >= end_time:
            self.add_error('preferred_time_end', 'End time must be after start time')

        # Check that preferred date is not in the past
        preferred_date = cleaned_data.get('preferred_date')
        if preferred_date and preferred_date < timezone.now().date():
            self.add_error('preferred_date', 'Preferred date cannot be in the past')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Set created_by if this is a new instance
        if not instance.pk and self.user:
            instance.created_by = self.user

        if commit:
            instance.save()

        return instance

class RouteForm(forms.ModelForm):
    """Form for creating and updating routes"""

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.schedule = kwargs.pop('schedule', None)
        super().__init__(*args, **kwargs)

        # Set initial values if schedule was provided
        if self.schedule and not self.instance.pk:
            self.fields['schedule'].initial = self.schedule
            self.fields['date'].initial = self.schedule.date

    class Meta:
        model = Route
        fields = [
            'name', 'schedule', 'technician', 'date',
            'start_location', 'start_latitude', 'start_longitude',
            'end_location', 'end_latitude', 'end_longitude',
            'estimated_start_time', 'estimated_end_time',
            'notes'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'estimated_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'estimated_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Check that date is not in the past
        date = cleaned_data.get('date')
        if date and date < timezone.now().date():
            self.add_error('date', 'Route date cannot be in the past')

        # Check that start/end times make sense
        start_time = cleaned_data.get('estimated_start_time')
        end_time = cleaned_data.get('estimated_end_time')

        if start_time and end_time and start_time >= end_time:
            self.add_error('estimated_end_time', 'End time must be after start time')

        # Check if technician is available on this date
        technician = cleaned_data.get('technician')
        route_date = cleaned_data.get('date')

        if technician and route_date:
            # Check specific date availability
            specific_availability = TechnicianAvailability.objects.filter(
                technician=technician,
                specific_date=route_date,
                is_available=True
            )

            # If no specific availability, check weekly availability
            if not specific_availability.exists():
                weekday = route_date.weekday()
                weekly_availability = TechnicianAvailability.objects.filter(
                    technician=technician,
                    day_of_week=weekday,
                    is_available=True
                )

                if not weekly_availability.exists():
                    self.add_error('technician', 'This technician is not available on the selected date')

            # Check if technician already has a route on this date
            existing_routes = Route.objects.filter(
                technician=technician,
                date=route_date
            )

            if self.instance.pk:
                existing_routes = existing_routes.exclude(pk=self.instance.pk)

            if existing_routes.exists():
                self.add_error('technician', 'This technician already has a route scheduled for this date')

        return cleaned_data

    def save(self, commit=True):
        route = super().save(commit=False)

        if commit:
            route.save()

            # Create a log entry for new routes
            if not self.instance.pk:
                RouteLog.objects.create(
                    route=route,
                    log_type='system',
                    message=f"Route created by {self.user.get_full_name() if self.user else 'system'}",
                    logged_by=self.user
                )

        return route

class RouteStopForm(forms.ModelForm):
    """Form for adding stops to a route"""

    def __init__(self, *args, **kwargs):
        self.route = kwargs.pop('route', None)
        super().__init__(*args, **kwargs)

        # Filter service requests to those that are pending
        # and in the same service area as the route's technician
        if self.route and self.route.technician:
            technician = self.route.technician
            service_areas = technician.service_areas.all()

            self.fields['service_request'].queryset = ServiceRequest.objects.filter(
                status__in=['pending', 'scheduled'],
                service_location__service_area__in=service_areas,
                route_stops__isnull=True,
                preferred_date=self.route.date
            ).select_related('customer', 'service_location', 'service_type')
        else:
            self.fields['service_request'].queryset = ServiceRequest.objects.none()

    class Meta:
        model = RouteStop
        fields = [
            'service_request', 'scheduled_arrival_time',
            'scheduled_departure_time', 'estimated_duration_minutes',
            'notes'
        ]
        widgets = {
            'scheduled_arrival_time': forms.TimeInput(attrs={'type': 'time'}),
            'scheduled_departure_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Check that times make sense
        arrival_time = cleaned_data.get('scheduled_arrival_time')
        departure_time = cleaned_data.get('scheduled_departure_time')

        if arrival_time and departure_time and arrival_time >= departure_time:
            self.add_error('scheduled_departure_time', 'Departure time must be after arrival time')

        # Check that service request isn't already assigned to another route
        service_request = cleaned_data.get('service_request')
        if service_request:
            existing_stops = RouteStop.objects.filter(service_request=service_request)
            if self.instance.pk:
                existing_stops = existing_stops.exclude(pk=self.instance.pk)

            if existing_stops.exists():
                self.add_error('service_request', 'This service request is already assigned to another route')

        return cleaned_data

class ServiceCompletionForm(forms.ModelForm):
    """Form for recording service completions"""

    # Replace FileField with MultipleFileField
    before_photos = MultipleFileField(
        required=False,
        help_text='Select multiple before service photos'
    )

    after_photos = MultipleFileField(
        required=False,
        help_text='Select multiple after service photos'
    )

    class Meta:
        model = ServiceCompletion
        fields = [
            'route_stop', 'service_request', 'work_performed', 'materials_used',
            'start_time', 'end_time', 'duration_minutes', 'billable_hours',
            'total_amount', 'customer_name', 'customer_signature', 'customer_email',
            'notes', 'technician_comments', 'follow_up_required', 'follow_up_notes'
        ]
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'work_performed': forms.Textarea(attrs={'rows': 4}),
            'materials_used': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'technician_comments': forms.Textarea(attrs={'rows': 3}),
            'follow_up_notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make certain fields required
        self.fields['route_stop'].widget = forms.HiddenInput()
        self.fields['service_request'].widget = forms.HiddenInput()

        # Add placeholder for signature
        self.fields['customer_signature'].help_text = 'Customer signature will be collected via the mobile app.'

        # If we have route_stop initial data, calculate duration
        if 'initial' in kwargs and 'route_stop' in kwargs['initial']:
            route_stop = kwargs['initial']['route_stop']
            if route_stop.actual_arrival_time and route_stop.actual_departure_time:
                duration = (route_stop.actual_departure_time - route_stop.actual_arrival_time).total_seconds() / 60
                self.fields['duration_minutes'].initial = int(duration)
                self.fields['billable_hours'].initial = round(duration / 60, 2)

    def clean(self):
        cleaned_data = super().clean()

        # Calculate duration if not provided
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        duration_minutes = cleaned_data.get('duration_minutes')

        if start_time and end_time and not duration_minutes:
            duration = (end_time - start_time).total_seconds() / 60
            cleaned_data['duration_minutes'] = int(duration)

        # Validate that end time is after start time
        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', 'End time must be after start time')

        return cleaned_data

    def save(self, commit=True):
        service_completion = super().save(commit=False)

        # Calculate duration if not set
        if not service_completion.duration_minutes and service_completion.start_time and service_completion.end_time:
            duration = service_completion.end_time - service_completion.start_time
            service_completion.duration_minutes = int(duration.total_seconds() / 60)

        if commit:
            service_completion.save()

            # Process before/after photos
            if 'before_photos' in self.files:
                for photo_file in self.files.getlist('before_photos'):
                    photo = ServicePhoto.objects.create(
                        service_request=service_completion.service_request,
                        image=photo_file,
                        photo_type='before',
                        caption='Before service',
                        taken_at=service_completion.start_time
                    )
                    service_completion.before_photos.add(photo)

            if 'after_photos' in self.files:
                for photo_file in self.files.getlist('after_photos'):
                    photo = ServicePhoto.objects.create(
                        service_request=service_completion.service_request,
                        image=photo_file,
                        photo_type='after',
                        caption='After service',
                        taken_at=service_completion.end_time
                    )
                    service_completion.after_photos.add(photo)

        return service_completion

class ServicePhotoUploadForm(forms.Form):
    """Form for uploading service photos"""
    service_request = forms.ModelChoiceField(
        queryset=ServiceRequest.objects.all()
    )

    photo_type = forms.ChoiceField(
        choices=[
            ('before', 'Before Service'),
            ('after', 'After Service'),
            ('issue', 'Issue Documentation'),
            ('other', 'Other')
        ]
    )

    images = MultipleFileField(
        help_text='Select multiple images to upload'
    )

    caption = forms.CharField(max_length=255, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)

class TechnicianProfileForm(forms.ModelForm):
    """Form for managing technician profiles"""

    # Add skills as a MultipleChoiceField
    skills = forms.ModelMultipleChoiceField(
        queryset=TechnicianSkill.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = TechnicianProfile
        fields = [
            'skills', 'vehicle_type', 'license_plate', 'max_travel_distance_miles',
            'certifications', 'enable_location_tracking'
        ]
        widgets = {
            'certifications': forms.Textarea(attrs={'rows': 3}),
        }

class TechnicianAvailabilityForm(forms.ModelForm):
    """Form for managing technician availability"""

    class Meta:
        model = TechnicianAvailability
        fields = [
            'technician', 'day_of_week', 'specific_date', 'start_time',
            'end_time', 'is_available', 'unavailability_reason'
        ]
        widgets = {
            'specific_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Check that either day_of_week or specific_date is provided
        day_of_week = cleaned_data.get('day_of_week')
        specific_date = cleaned_data.get('specific_date')

        if day_of_week is None and specific_date is None:
            self.add_error(None, 'Either day of week or specific date must be provided')

        if day_of_week is not None and specific_date is not None:
            self.add_error(None, 'Cannot provide both day of week and specific date')

        # Check that times make sense
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', 'End time must be after start time')

        # Check for overlapping availability
        technician = cleaned_data.get('technician')
        is_available = cleaned_data.get('is_available')

        if technician and is_available:
            if day_of_week is not None:
                # Check for overlapping weekly availability
                overlapping = TechnicianAvailability.objects.filter(
                    technician=technician,
                    day_of_week=day_of_week,
                    is_available=True,
                    start_time__lt=end_time,
                    end_time__gt=start_time
                )

                if self.instance.pk:
                    overlapping = overlapping.exclude(pk=self.instance.pk)

                if overlapping.exists():
                    self.add_error(None, 'This availability overlaps with existing availability')

            elif specific_date is not None:
                # Check for overlapping specific date availability
                overlapping = TechnicianAvailability.objects.filter(
                    technician=technician,
                    specific_date=specific_date,
                    is_available=True,
                    start_time__lt=end_time,
                    end_time__gt=start_time
                )

                if self.instance.pk:
                    overlapping = overlapping.exclude(pk=self.instance.pk)

                if overlapping.exists():
                    self.add_error(None, 'This availability overlaps with existing availability')

        return cleaned_data

class CustomerFeedbackForm(forms.ModelForm):
    """Form for collecting customer feedback"""

    class Meta:
        model = CustomerFeedback
        fields = [
            'service_request', 'overall_rating', 'technician_rating',
            'punctuality_rating', 'quality_rating', 'comments',
            'would_recommend', 'wants_follow_up', 'follow_up_contact_method',
            'submitted_by'
        ]
        widgets = {
            'overall_rating': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]),
            'technician_rating': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]),
            'punctuality_rating': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]),
            'quality_rating': forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]),
            'comments': forms.Textarea(attrs={'rows': 4}),
            'would_recommend': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No')]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make service_request a hidden field if it's passed in the initial data
        if 'initial' in kwargs and 'service_request' in kwargs['initial']:
            self.fields['service_request'].widget = forms.HiddenInput()

        # Conditionally show follow_up_contact_method
        self.fields['follow_up_contact_method'].widget.attrs['class'] = 'follow-up-field'

    def clean(self):
        cleaned_data = super().clean()

        # Validate ratings
        for rating_field in ['overall_rating', 'technician_rating', 'punctuality_rating', 'quality_rating']:
            rating = cleaned_data.get(rating_field)
            if rating is not None and (rating < 1 or rating > 5):
                self.add_error(rating_field, 'Rating must be between 1 and 5')

        # Validate follow-up contact method if follow-up is requested
        wants_follow_up = cleaned_data.get('wants_follow_up')
        follow_up_method = cleaned_data.get('follow_up_contact_method')

        if wants_follow_up and not follow_up_method:
            self.add_error('follow_up_contact_method', 'Please select a follow-up contact method')

        return cleaned_data


class OptimizationSettingsForm(forms.ModelForm):
    """Form for managing route optimization settings"""

    class Meta:
        model = OptimizationSettings
        fields = [
            'name', 'description', 'prioritize', 'max_stops_per_route',
            'max_drive_time_minutes', 'max_route_duration_minutes',
            'service_time_buffer_minutes', 'travel_time_buffer_percent',
            'use_historical_traffic', 'consider_technician_skills',
            'consider_customer_priority', 'is_default'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'prioritize': forms.Select(),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Validate max stops per route
        max_stops = cleaned_data.get('max_stops_per_route')
        if max_stops is not None and max_stops <= 0:
            self.add_error('max_stops_per_route', 'Must be a positive number')

        # Validate max drive time
        max_drive_time = cleaned_data.get('max_drive_time_minutes')
        if max_drive_time is not None and max_drive_time <= 0:
            self.add_error('max_drive_time_minutes', 'Must be a positive number')

        # Validate max route duration
        max_route_duration = cleaned_data.get('max_route_duration_minutes')
        if max_route_duration is not None and max_route_duration <= 0:
            self.add_error('max_route_duration_minutes', 'Must be a positive number')

        # Validate service time buffer
        service_time_buffer = cleaned_data.get('service_time_buffer_minutes')
        if service_time_buffer is not None and service_time_buffer < 0:
            self.add_error('service_time_buffer_minutes', 'Cannot be negative')

        # Validate travel time buffer percentage
        travel_time_buffer = cleaned_data.get('travel_time_buffer_percent')
        if travel_time_buffer is not None and (travel_time_buffer < 0 or travel_time_buffer > 100):
            self.add_error('travel_time_buffer_percent', 'Must be between 0 and 100')

        # If this is set as default, clear other defaults
        is_default = cleaned_data.get('is_default')
        if is_default:
            OptimizationSettings.objects.filter(is_default=True).update(is_default=False)

        return cleaned_data

    def save(self, commit=True):
        # Ensure only one default setting exists
        instance = super().save(commit=False)

        if instance.is_default:
            # Clear other default settings
            OptimizationSettings.objects.exclude(pk=instance.pk).update(is_default=False)

        if commit:
            instance.save()

        return instance


from django import forms
from core.models import Employee

class BulkAssignTechnicianForm(forms.Form):
    """Form for bulk assigning technicians to service requests"""
    technician = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        required=True,
        label="Technician"
    )
    service_requests = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter technicians to only those with appropriate skills if needed
        self.fields['technician'].queryset = Employee.objects.filter(
            is_active=True,
            service_areas__isnull=False
        ).distinct()

    def clean_service_requests(self):
        """Validate that service_requests contains valid IDs"""
        service_requests = self.cleaned_data.get('service_requests', '')
        if not service_requests:
            raise forms.ValidationError("You must select at least one service request.")

        # Check if the string contains valid IDs
        request_ids = service_requests.split(',')
        if not all(rid.strip().isdigit() for rid in request_ids if rid.strip()):
            raise forms.ValidationError("Invalid service request IDs provided.")

        return service_requests
