from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q

from core.models import Employee, Customer
from .models import (
    Project, ProjectTeamMember, ProjectPhase, ProjectTask,
    ProjectDocument, ProjectRisk, TimeEntry, ProjectComment,
    ProjectReport
)

class ProjectForm(forms.ModelForm):
    """
    Form for creating and editing projects
    """
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Project start date"
    )
    target_end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Expected completion date"
    )
    budget = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Project budget (optional)"
    )

    class Meta:
        model = Project
        fields = [
            'name', 'description', 'customer', 'project_manager',
            'status', 'priority', 'start_date', 'target_end_date',
            'budget', 'hourly_rate'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Filter project managers to active employees
        self.fields['project_manager'].queryset = Employee.objects.filter(is_active=True)

        # Filter customers based on user's permissions
        if user and not user.is_superuser:
            self.fields['customer'].queryset = Customer.objects.filter(
                assigned_to=user.employee_profile
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        target_end_date = cleaned_data.get('target_end_date')

        if start_date and target_end_date:
            if target_end_date < start_date:
                raise ValidationError("End date cannot be before start date")

            if start_date < timezone.now().date():
                raise ValidationError("Start date cannot be in the past")

        return cleaned_data

class ProjectTeamMemberForm(forms.ModelForm):
    """
    Form for managing project team members
    """
    class Meta:
        model = ProjectTeamMember
        fields = ['employee', 'role', 'allocation_percentage']
        widgets = {
            'allocation_percentage': forms.NumberInput(attrs={'min': '0', 'max': '100'})
        }

    def __init__(self, *args, **kwargs):
        project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

        if project:
            # Exclude existing team members from employee choices
            existing_members = project.team_members.all()
            self.fields['employee'].queryset = Employee.objects.filter(
                is_active=True
            ).exclude(id__in=existing_members.values_list('id', flat=True))

    def clean_allocation_percentage(self):
        allocation = self.cleaned_data.get('allocation_percentage')
        if allocation and (allocation < 0 or allocation > 100):
            raise ValidationError("Allocation must be between 0 and 100 percent")
        return allocation

class ProjectPhaseForm(forms.ModelForm):
    """
    Form for project phases/milestones
    """
    status = forms.ChoiceField(
        choices=ProjectPhase.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_status',
            'data-previous': ''  # For tracking status changes
        })
    )

    class Meta:
        model = ProjectPhase
        fields = ['name', 'description', 'start_date', 'end_date', 'status']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phase name'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Enter phase description'
            })
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

        # If instance exists, set previous status
        if self.instance and self.instance.pk:
            self.fields['status'].widget.attrs['data-previous'] = self.instance.status

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date cannot be before start date")

            if self.project:
                if start_date < self.project.start_date:
                    raise ValidationError("Phase cannot start before project start date")
                if end_date > self.project.target_end_date:
                    raise ValidationError("Phase cannot end after project end date")

        return cleaned_data
class ProjectTaskForm(forms.ModelForm):
    class Meta:
        model = ProjectTask
        fields = [
            'title', 'description', 'status', 'priority',
            'assigned_to', 'start_date', 'due_date', 'estimated_hours',
            'dependencies'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter task title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter task description'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Select team member'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '0'
            }),
            'dependencies': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'style': 'height: 100px;'  # Make multiple select box taller
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].empty_label = "Select Employee"
        self.fields['dependencies'].help_text = "Hold Ctrl/Cmd to select multiple tasks"
class ProjectDocumentForm(forms.ModelForm):
    """
    Form for project documents
    """
    class Meta:
        model = ProjectDocument
        fields = ['title', 'document_type', 'file', 'version', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Validate file size (max 50MB)
            if file.size > 52428800:
                raise ValidationError("File size cannot exceed 50MB")

            # Validate file extension
            allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            ext = file.name.lower()[-4:]
            if ext not in allowed_extensions:
                raise ValidationError(f"File type not supported. Allowed types: {', '.join(allowed_extensions)}")

        return file

class ProjectRiskForm(forms.ModelForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        empty_label="Select a Project",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = ProjectRisk
        fields = [
            'project', 'title', 'description', 'risk_level',
            'probability', 'impact', 'status', 'mitigation_plan'
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['project'].queryset = Project.objects.filter(
                Q(project_manager=user.employee_profile) |
                Q(team_members=user.employee_profile)
            ).distinct()

class TimeEntryForm(forms.ModelForm):
    """
    Form for time entries
    """
    class Meta:
        model = TimeEntry
        fields = ['date', 'hours', 'description', 'is_billable']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'hours': forms.NumberInput(attrs={'step': '0.25', 'min': '0.25'}),
            'description': forms.Textarea(attrs={'rows': 2})
        }

    def __init__(self, *args, **kwargs):
        self.task = kwargs.pop('task', None)
        super().__init__(*args, **kwargs)

    def clean_date(self):
        date = self.cleaned_data.get('date')
        if date:
            if date > timezone.now().date():
                raise ValidationError("Cannot log time for future dates")

            if self.task:
                if date < self.task.start_date:
                    raise ValidationError("Cannot log time before task start date")
                if self.task.due_date and date > self.task.due_date:
                    raise ValidationError("Cannot log time after task due date")

        return date

    def clean_hours(self):
        hours = self.cleaned_data.get('hours')
        if hours:
            if hours < 0.25:
                raise ValidationError("Minimum time entry is 15 minutes (0.25 hours)")
            if hours > 24:
                raise ValidationError("Maximum time entry is 24 hours per day")
        return hours

class ProjectCommentForm(forms.ModelForm):
    """
    Form for project comments
    """
    class Meta:
        model = ProjectComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter your comment here...'})
        }

    def clean_text(self):
        text = self.cleaned_data.get('text')
        if text:
            if len(text.strip()) < 2:
                raise ValidationError("Comment must contain at least 2 characters")
        return text


class ProjectReportForm(forms.ModelForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        empty_label="Select a Project",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = ProjectReport
        fields = ['project', 'title', 'content', 'report_type', 'attachments']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Enter report content here...'
            }),
            'report_type': forms.Select(attrs={'class': 'form-select'}),
            'attachments': forms.FileInput(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['project'].queryset = Project.objects.filter(
                Q(project_manager=user.employee_profile) |
                Q(team_members=user.employee_profile)
            ).distinct()

    def clean_attachments(self):
        attachments = self.cleaned_data.get('attachments')
        if attachments:
            if attachments.size > 10485760:  # 10MB limit
                raise ValidationError("File size cannot exceed 10MB")
            allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            ext = attachments.name.lower()[-4:]
            if ext not in allowed_extensions:
                raise ValidationError(
                    f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
                )
        return attachments

# forms.py
class BulkDocumentUploadForm(forms.Form):
    document_type = forms.ChoiceField(
        choices=ProjectDocument.DOCUMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control'
        })
    )
