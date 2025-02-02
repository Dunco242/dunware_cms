# core/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Employee, Customer, Lead, Service,
    Note, Task, Meeting
)

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user

class EmployeeForm(forms.ModelForm):
    hire_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = Employee
        fields = ('employee_id', 'department', 'position', 'phone',
                 'hire_date', 'profile_picture')

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone.replace('-', '').replace('+', '').isdigit():
            raise ValidationError('Phone number can only contain digits, hyphens, and plus sign.')
        return phone

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ('company_name', 'contact_person', 'email', 'phone',
                 'address', 'city', 'state', 'zip_code', 'website',
                 'status', 'assigned_to')
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super(CustomerForm, self).__init__(*args, **kwargs)

        # ✅ Fetch employees properly
        employees = Employee.objects.all()

        # Check if employees exist in DB
        if employees.exists():
            self.fields['assigned_to'].queryset = employees
            self.fields['assigned_to'].label_from_instance = lambda obj: f"{obj.user.get_full_name()} ({obj.position})"
        else:
            self.fields['assigned_to'].queryset = Employee.objects.none()

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Customer.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A customer with this email already exists.')
        return email

class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ('company_name', 'contact_person', 'email', 'phone',
                 'source', 'status', 'notes', 'assigned_to')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('status') == 'converted':
            # Check if a customer with this email already exists
            email = cleaned_data.get('email')
            if Customer.objects.filter(email=email).exists():
                raise ValidationError('A customer with this email already exists.')
        return cleaned_data

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ('name', 'description', 'price', 'is_active')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'price': forms.NumberInput(attrs={'step': '0.01'}),
        }

class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ('title', 'content', 'note_type', 'customer', 'lead')
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        lead = cleaned_data.get('lead')
        if customer and lead:
            raise ValidationError('A note cannot be associated with both a customer and a lead.')
        if not customer and not lead:
            raise ValidationError('A note must be associated with either a customer or a lead.')
        return cleaned_data

class TaskForm(forms.ModelForm):
    due_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )

    class Meta:
        model = Task
        fields = ('title', 'description', 'due_date', 'priority',
                 'status', 'assigned_to', 'customer', 'lead')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        lead = cleaned_data.get('lead')
        if customer and lead:
            raise ValidationError('A task cannot be associated with both a customer and a lead.')
        due_date = cleaned_data.get('due_date')
        if due_date and due_date < timezone.now():
            raise ValidationError('Due date cannot be in the past.')
        return cleaned_data

class MeetingForm(forms.ModelForm):
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'})
    )
    attendees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Meeting
        fields = ('title', 'meeting_type', 'start_time', 'end_time',
                 'description', 'attendees', 'customers', 'leads')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'customers': forms.CheckboxSelectMultiple(),
            'leads': forms.CheckboxSelectMultiple(),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time:
            if start_time >= end_time:
                raise ValidationError('End time must be after start time.')
            if start_time < timezone.now():
                raise ValidationError('Start time cannot be in the past.')

        meeting_type = cleaned_data.get('meeting_type')
        if meeting_type == 'zoom':
            # Additional validation for Zoom meetings can be added here
            pass

        return cleaned_data

class MeetingSearchForm(forms.Form):
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    meeting_type = forms.ChoiceField(
        choices=[('', 'All')] + Meeting.MEETING_TYPES,
        required=False
    )

class TaskSearchForm(forms.Form):
    status = forms.ChoiceField(
        choices=[('', 'All')] + Task.STATUS_CHOICES,
        required=False
    )
    priority = forms.ChoiceField(
        choices=[('', 'All')] + Task.PRIORITY_CHOICES,
        required=False
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
