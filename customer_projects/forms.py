from django import forms
from django.forms import inlineformset_factory
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
    """Form for logging time entries against tasks"""

    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Select the date when the work was done."
    )

    hours = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.25',
            'min': '0.25',
            'max': '24'
        }),
        min_value=0.25,
        max_value=24,
        help_text="Enter the number of hours worked (minimum: 0.25, maximum: 24)."
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Describe the work done'
        }),
        max_length=500,
        help_text="Provide a brief description of the work done (max 500 characters)."
    )

    is_billable = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Check if the time entry is billable."
    )

    class Meta:
        model = TimeEntry
        fields = ['date', 'hours', 'description', 'is_billable']

    def __init__(self, *args, **kwargs):
        """
        Custom initialization to allow task-based validation.
        """
        self.task = kwargs.pop('task', None)
        super().__init__(*args, **kwargs)

        # Set default date to today
        self.fields['date'].initial = timezone.now().date()

    def clean_date(self):
        """
        Validate that the date is not in the future and falls within the task's duration.
        """
        date = self.cleaned_data.get('date')
        if not date:
            raise ValidationError("Date is required.")

        today = timezone.now().date()
        if date > today:
            raise ValidationError("Cannot log time for future dates.")

        if self.task:
            if date < self.task.start_date:
                raise ValidationError("Cannot log time before task start date.")
            if self.task.due_date and date > self.task.due_date:
                raise ValidationError("Cannot log time after task due date.")

        return date

    def clean_hours(self):
        """
        Validate that the logged hours are within the allowed range.
        """
        hours = self.cleaned_data.get('hours')
        if not hours:
            raise ValidationError("Hours are required.")

        if hours < 0.25:
            raise ValidationError("Minimum time entry is 15 minutes (0.25 hours).")
        if hours > 24:
            raise ValidationError("Maximum time entry is 24 hours per day.")

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
    """Form for creating project risks"""

    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter risk title'
        }),
        help_text="Enter a brief title for the risk"
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the risk'
        }),
        help_text="Provide a detailed description of the risk"
    )

    risk_level = forms.ChoiceField(
        choices=ProjectRisk.RISK_LEVELS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Select the severity of the risk"
    )

    probability = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'placeholder': '0-100'
        }),
        help_text="Enter the likelihood of the risk occurring (0-100)"
    )

    impact = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'placeholder': '0-100'
        }),
        help_text="Enter the potential impact on the project (0-100)"
    )

    status = forms.ChoiceField(
        choices=ProjectRisk.RISK_STATUS,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Select the current status of the risk"
    )

    mitigation_plan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe how to mitigate this risk'
        }),
        help_text="Describe the plan to mitigate or manage the risk"
    )

    class Meta:
        model = ProjectRisk
        fields = ['title', 'description', 'risk_level', 'probability', 'impact', 'status', 'mitigation_plan']

    def clean_probability(self):
        probability = self.cleaned_data.get('probability')
        if not 0 <= probability <= 100:
            raise ValidationError("Probability must be between 0 and 100.")
        return probability

    def clean_impact(self):
        impact = self.cleaned_data.get('impact')
        if not 0 <= impact <= 100:
            raise ValidationError("Impact must be between 0 and 100.")
        return impact

    def clean(self):
        cleaned_data = super().clean()
        description = cleaned_data.get('description')
        mitigation_plan = cleaned_data.get('mitigation_plan')
        if not description and not mitigation_plan:
            raise ValidationError("Please provide a description or mitigation plan.")
        return cleaned_data


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
    """Form for creating and editing project reports"""

    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter report title',
            'id': 'id_title'
        }),
        label="Report Title",
        help_text="Enter a concise title for the report."
    )

    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 6,
            'placeholder': 'Enter the report content here...',
            'id': 'id_content'
        }),
        required=False,
        label="Report Content",
        help_text="Provide the main content or summary of the report."
    )

    report_type = forms.ChoiceField(
        choices=ProjectReport.REPORT_TYPES,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_report_type'
        }),
        label="Report Type",
        help_text="Select the type of report."
    )

    attachments = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'id': 'id_attachments'
        }),
        label="Attachments (Optional)",
        help_text="Upload supporting documents (PDF, DOC, XLS, TXT; max 10MB)."
    )

    include_tasks = forms.BooleanField(
        required=False,
        label="Include Task Summary",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_include_tasks'
        }),
        help_text="Check to include task statistics in the report."
    )

    include_risks = forms.BooleanField(
        required=False,
        label="Include Risk Summary",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_include_risks'
        }),
        help_text="Check to include risk statistics in the report."
    )

    generate_pdf = forms.BooleanField(
        required=False,
        label="Generate PDF Attachment",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_generate_pdf'
        }),
        help_text="Check to generate a PDF version of the report."
    )

    class Meta:
        model = ProjectReport
        fields = ['title', 'content', 'report_type', 'attachments', 'include_tasks', 'include_risks', 'generate_pdf']

    def clean_attachments(self):
        attachments = self.cleaned_data.get('attachments')
        if attachments:
            max_size = 10 * 1024 * 1024  # 10MB in bytes
            if attachments.size > max_size:
                raise ValidationError("File size cannot exceed 10MB.")
            allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            ext = os.path.splitext(attachments.name.lower())[1]
            if ext not in allowed_extensions:
                raise ValidationError(
                    f"File type not supported. Allowed types: {', '.join(allowed_extensions)}."
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


class IntegratedProjectForm(ProjectForm):
    """Extended form for creating a project with phases and tasks in one step"""

    # Add fields to specify how many phases to create
    num_phases = forms.IntegerField(
        initial=1,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'num_phases'
        }),
        help_text="Number of initial phases to add"
    )

    class Meta(ProjectForm.Meta):
        model = Project
        fields = ProjectForm.Meta.fields + ['num_phases']

# Create inline formsets for phases
ProjectPhaseFormSet = inlineformset_factory(
    Project,
    ProjectPhase,
    form=ProjectPhaseForm,
    extra=1,  # Start with one empty form
    can_delete=True
)

# Create inline formsets for tasks
PhaseTaskFormSet = inlineformset_factory(
    ProjectPhase,
    ProjectTask,
    form=ProjectTaskForm,
    extra=1,  # Start with one empty form
    can_delete=True
)
