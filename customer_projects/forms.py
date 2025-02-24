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
    """Form for creating and editing projects"""
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter project name'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Enter project description'
        })
    )

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    project_manager = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    status = forms.ChoiceField(
        choices=Project.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    priority = forms.ChoiceField(
        choices=Project.PRIORITY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        help_text="Project start date"
    )

    target_end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        help_text="Expected completion date"
    )

    budget = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        }),
        help_text="Project budget (optional)"
    )

    hourly_rate = forms.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )

    class Meta:
        model = Project
        fields = [
            'name', 'description', 'customer', 'project_manager',
            'status', 'priority', 'start_date', 'target_end_date',
            'budget', 'hourly_rate'
        ]

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

class ProjectTeamMemberForm(forms.ModelForm):
    """Form for managing project team members"""
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    role = forms.ChoiceField(
        choices=ProjectTeamMember.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    allocation_percentage = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100'
        })
    )

    class Meta:
        model = ProjectTeamMember
        fields = ['employee', 'role', 'allocation_percentage']

    def __init__(self, *args, **kwargs):
        project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

        if project:
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
    """Form for project phases/milestones"""
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter phase name'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter phase description'
        })
    )

    status = forms.ChoiceField(
        choices=ProjectPhase.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-previous': ''
        })
    )

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    class Meta:
        model = ProjectPhase
        fields = ['name', 'description', 'start_date', 'end_date', 'status']

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

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
    """Form for project tasks"""
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter task title'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter task description'
        })
    )

    status = forms.ChoiceField(
        choices=ProjectTask.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    priority = forms.ChoiceField(
        choices=ProjectTask.PRIORITY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    assigned_to = forms.ModelChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'placeholder': 'Select team member'
        })
    )

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    due_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    estimated_hours = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.5',
            'min': '0'
        })
    )

    dependencies = forms.ModelMultipleChoiceField(
        queryset=ProjectTask.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Select Dependencies'
        })
    )

    class Meta:
        model = ProjectTask
        fields = [
            'title', 'description', 'status', 'priority',
            'assigned_to', 'start_date', 'due_date', 'estimated_hours',
            'dependencies'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].empty_label = "Select Employee"
        self.fields['dependencies'].help_text = "Hold Ctrl/Cmd to select multiple tasks"

class TimeEntryForm(forms.ModelForm):
    """Form for time entries"""
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )

    hours = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.25',
            'min': '0.25',
            'max': '24'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Describe the work done'
        })
    )

    is_billable = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = TimeEntry
        fields = ['date', 'hours', 'description', 'is_billable']

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

class ProjectDocumentForm(forms.ModelForm):
    """Form for project documents"""
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter document title'
        })
    )

    document_type = forms.ChoiceField(
        choices=ProjectDocument.DOCUMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    version = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 1.0'
        })
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Enter document description'
        })
    )

    class Meta:
        model = ProjectDocument
        fields = ['title', 'document_type', 'file', 'version', 'description']

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if file.size > 52428800:  # 50MB
                raise ValidationError("File size cannot exceed 50MB")

            allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            ext = file.name.lower()[-4:]
            if ext not in allowed_extensions:
                raise ValidationError(f"File type not supported. Allowed types: {', '.join(allowed_extensions)}")

        return file

class ProjectRiskForm(forms.ModelForm):
    """Form for project risks"""
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter risk title'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the risk'
        })
    )

    risk_level = forms.ChoiceField(
        choices=ProjectRisk.RISK_LEVELS,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    probability = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100'
        })
    )

    impact = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100'
        })
    )

    status = forms.ChoiceField(
        choices=ProjectRisk.RISK_STATUS,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    mitigation_plan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe how to mitigate this risk'
        })
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
            self.fields['project'] = forms.ModelChoiceField(
                queryset=Project.objects.filter(
                    Q(project_manager=user.employee_profile) |
                    Q(team_members=user.employee_profile)
                ).distinct(),
                empty_label="Select a Project",
                widget=forms.Select(attrs={'class': 'form-control'})
            )

class ProjectCommentForm(forms.ModelForm):
    """Form for project comments"""
    text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter your comment here...'
        })
    )

    class Meta:
        model = ProjectComment
        fields = ['text']

    def clean_text(self):
        text = self.cleaned_data.get('text')
        if text:
            if len(text.strip()) < 2:
                raise ValidationError("Comment must contain at least 2 characters")
        return text

class ProjectReportForm(forms.ModelForm):
    """Form for project reports"""
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter report title'
        })
    )

    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Enter report content here...'
        })
    )

    report_type = forms.ChoiceField(
        choices=ProjectReport.REPORT_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    attachments = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = ProjectReport
        fields = ['project', 'title', 'content', 'report_type', 'attachments']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['project'] = forms.ModelChoiceField(
                queryset=Project.objects.filter(
                    Q(project_manager=user.employee_profile) |
                    Q(team_members=user.employee_profile)
                ).distinct(),
                empty_label="Select a Project",
                widget=forms.Select(attrs={'class': 'form-control'})
            )

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

class BulkDocumentUploadForm(forms.Form):
    """Form for bulk document uploads"""
    document_type = forms.ChoiceField(
        choices=ProjectDocument.DOCUMENT_TYPES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Enter a common description for all uploaded files'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The actual file handling will be done in the view using request.FILES
