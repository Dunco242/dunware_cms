from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, F, Q, Case, When, DecimalField, Value
from core.models import Customer, Employee
import uuid
from decimal import Decimal
from django.urls import reverse
from slugify import slugify
from django.apps import apps
import logging


def get_customer_model():
    return apps.get_model('core', 'Customer')

def get_employee_model():
    return apps.get_model('core', 'Employee')


class Project(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('canceled', 'Canceled')
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    name = models.CharField(max_length=200)
    project_code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    customer = models.ForeignKey(
        'core.Customer',
        on_delete=models.CASCADE,
        related_name='projects'
    )
    project_manager = models.ForeignKey(
        'core.Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='managed_projects'
    )
    team_members = models.ManyToManyField(
        'core.Employee',
        through='ProjectTeamMember',
        related_name='project_assignments'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='planning'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    start_date = models.DateField(default=timezone.now)
    target_end_date = models.DateField()
    actual_end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('25.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Default hourly rate for billing project work"
    )
    progress = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Project completion percentage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.Employee',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_projects'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project_code']),
            models.Index(fields=['status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['project_manager', 'status']),
        ]
        permissions = [
            ("view_project_finances", "Can view project finances"),
            ("manage_project_team", "Can manage project team"),
        ]

    def __str__(self):
        return f"{self.project_code} - {self.name}"

    def save(self, *args, **kwargs):
        # Generate project code if not set
        if not self.project_code:
            year = timezone.now().strftime('%Y')
            count = Project.objects.filter(
                project_code__startswith=f'P{year}'
            ).count()
            self.project_code = f'P{year}{count + 1:04d}'

        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status in ['planning', 'in_progress']

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_overdue(self):
        if self.status not in ['completed', 'canceled']:
            return self.target_end_date < timezone.now().date()
        return False

    @property
    def total_hours(self):
        return self.phases.aggregate(
            total=models.Sum('tasks__time_entries__hours')
        )['total'] or 0

    @property
    def billable_hours(self):
        return self.phases.aggregate(
            billable=models.Sum(
                'tasks__time_entries__hours',
                filter=models.Q(tasks__time_entries__is_billable=True)
            )
        )['billable'] or 0

    def calculate_cost(self):
        return self.billable_hours * self.hourly_rate

    def get_team_members(self):
        return self.team_members.select_related('user').all()

    def get_active_tasks(self):
        return self.phases.filter(
            tasks__status__in=['todo', 'in_progress']
        ).values('tasks__id', 'tasks__title', 'tasks__due_date')

    def get_overdue_tasks(self):
        today = timezone.now().date()
        return self.phases.filter(
            tasks__status__in=['todo', 'in_progress'],
            tasks__due_date__lt=today
        ).values('tasks__id', 'tasks__title', 'tasks__due_date')

    def calculate_progress(self):
        """Calculate and update project progress based on phases"""
        try:
            phases = self.phases.all()
            if not phases.exists():
                return 0

            # Calculate average progress from all phases
            total_progress = sum(phase.progress for phase in phases)
            project_progress = round(total_progress / phases.count())

            # Update project progress
            self.progress = project_progress
            self.save(update_fields=['progress'])

            return project_progress
        except Exception as e:
            logger.error(f"Error calculating project progress: {str(e)}")
            return 0


class ProjectTeamMember(models.Model):
    """
    Through model for project team members with additional attributes
    """
    ROLE_CHOICES = [
        ('lead', 'Team Lead'),
        ('developer', 'Developer'),
        ('designer', 'Designer'),
        ('analyst', 'Analyst'),
        ('tester', 'Tester'),
        ('other', 'Other')
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    employee = models.ForeignKey('core.Employee', on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    allocation_percentage = models.IntegerField(default=100, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        unique_together = ['project', 'employee']

    def __str__(self):
        user = getattr(self.employee, 'user', None)
        full_name = user.get_full_name() if user else "Unassigned"
        return f"{full_name()} - {self.get_role_display()}"

logger = logging.getLogger(__name__)


class ProjectPhase(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold')
    ]

    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='phases')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    end_date = models.DateField()
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_completed = models.BooleanField(default=False)

    def calculate_progress(self):
        """Calculate and update phase progress based on task status"""
        try:
            phase_tasks = self.tasks.all()
            total_tasks = phase_tasks.count()

            if total_tasks == 0:
                progress = 100 if self.status == 'completed' else 0
            else:
                completed_tasks = phase_tasks.filter(status='done').count()
                in_progress_tasks = phase_tasks.filter(status='in_progress').count()
                in_review_tasks = phase_tasks.filter(status='in_review').count()

                progress = (
                    (completed_tasks * 100) +
                    (in_review_tasks * 75) +
                    (in_progress_tasks * 50)
                ) / total_tasks

            self.progress = round(progress)
            self.save(update_fields=['progress'])

            self.project.calculate_progress()
            return self.progress

        except Exception as e:

            logger.error(f"Error calculating phase progress: {str(e)}")
            return 0

    def get_all_time_entries(self):
        """Get summary of time entries for all tasks in this phase."""
        entries = TimeEntry.objects.filter(task__phase=self)

        return {
            'total_hours': entries.aggregate(total=Sum('hours'))['total'] or 0,
            'billable_hours': entries.filter(is_billable=True).aggregate(total=Sum('hours'))['total'] or 0,
            'non_billable_hours': entries.filter(is_billable=False).aggregate(total=Sum('hours'))['total'] or 0,
        }

    def get_tasks_with_time_entries(self):
        """Get all tasks in this phase that have time entries with summary statistics."""
        tasks = self.tasks.annotate(
            total_hours=Sum('time_entries__hours'),
            billable_hours=Sum(Case(
                When(time_entries__is_billable=True, then=F('time_entries__hours')),
                default=Value(0),
                output_field=DecimalField()
            )),
            non_billable_hours=Sum(Case(
                When(time_entries__is_billable=False, then=F('time_entries__hours')),
                default=Value(0),
                output_field=DecimalField()
            ))
        ).filter(total_hours__gt=0)

        for task in tasks:
            if task.estimated_hours and task.estimated_hours > 0:
                task.progress_percentage = min(100, round((task.total_hours / task.estimated_hours) * 100))
            else:
                task.progress_percentage = 0

        return tasks

    def get_recent_time_entries(self, limit=10):
        """Get the most recent time entries for all tasks in this phase."""
        return TimeEntry.objects.filter(
            task__phase=self
        ).select_related('task', 'employee').order_by('-date', '-created_at')[:limit]

    def __str__(self):
        return f"{self.project.project_code} - {self.name}"

class ProjectTask(models.Model):
    """
    Tasks within project phases
    """
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('in_review', 'In Review'),
        ('done', 'Done'),
        ('blocked', 'Blocked')
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    phase = models.ForeignKey(ProjectPhase, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    assigned_to = models.ForeignKey('core.Employee', on_delete=models.SET_NULL, null=True, related_name='project_tasks')
    start_date = models.DateField()
    due_date = models.DateField()
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    dependencies = models.ManyToManyField('self', symmetrical=False, related_name='dependent_tasks', blank=True)

    class Meta:
        ordering = ['due_date', 'priority']

    def __str__(self):
        return f"{self.phase.project.project_code} - {self.title}"

    def update_actual_hours(self):
        """Update the total actual hours logged for the task."""
        self.actual_hours = self.time_entries.aggregate(total=Sum('hours'))['total'] or 0
        self.save(update_fields=['actual_hours'])

    def save(self, *args, **kwargs):
        """Override save to ensure progress updates."""
        super().save(*args, **kwargs)
        self.phase.calculate_progress()

class ProjectDocument(models.Model):
    """
    Project-related documents and files
    """

    DOCUMENT_TYPES = [
        ('requirement', 'Requirements Document'),
        ('design', 'Design Document'),
        ('specification', 'Technical Specification'),
        ('proposal', 'Project Proposal'),
        ('contract', 'Contract'),
        ('report', 'Report'),
        ('other', 'Other')
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='project_documents/%Y/%m/')
    version = models.CharField(max_length=10)
    uploaded_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)
    upload_date = models.DateTimeField(auto_now_add=True, null=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-upload_date']

    def __str__(self):
        return f"{self.project.project_code} - {self.title} (v{self.version})"
class ProjectRisk(models.Model):
    """
    Project risk management
    """

    RISK_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ]

    RISK_STATUS = [
        ('identified', 'Identified'),
        ('assessed', 'Assessed'),
        ('mitigated', 'Mitigated'),
        ('closed', 'Closed')
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='risks')
    title = models.CharField(max_length=200)
    description = models.TextField()
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS)
    probability = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    impact = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    status = models.CharField(max_length=20, choices=RISK_STATUS, default='identified')
    mitigation_plan = models.TextField(blank=True)
    identified_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)
    identified_date = models.DateField(auto_now_add=True)
    last_updated = models.DateField(auto_now=True)

    class Meta:
        ordering = ['-risk_level', '-probability']

    def __str__(self):
        return f"{self.project.project_code} - {self.title}"

    @property
    def risk_score(self):
        return (self.probability * self.impact) / 100

class TimeEntry(models.Model):
    """
    Time tracking for project tasks
    """

    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='time_entries')
    employee = models.ForeignKey('core.Employee', on_delete=models.CASCADE, related_name='time_entries')
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0.25), MaxValueValidator(24)])
    description = models.TextField(blank=True)
    is_billable = models.BooleanField(default=True)
    is_invoiced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Time entries'

    def __str__(self):
        user = getattr(self.employee, 'user', None)  # Get User from Employee
        full_name = user.get_full_name() if user else "Unassigned"
        return f"{self.task.phase.project.project_code} - {full_name} - {self.date}"


    def clean(self):
        """Prevent future time entries"""
        if self.date > timezone.now().date():
            raise ValidationError("Time entry date cannot be in the future.")

    def save(self, *args, **kwargs):
        """Override save to update task, phase, and project progress."""
        super().save(*args, **kwargs)

        # Update task's actual hours
        self.task.update_actual_hours()

        # Update phase progress
        self.task.phase.calculate_progress()

        # Update project progress
        self.task.phase.project.calculate_progress()


class ProjectComment(models.Model):
    """
    Comments on projects, tasks, and documents
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    author = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='project_comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, null=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.author.get_full_name()}"


class ProjectReport(models.Model):
    """
    Stores reports generated for projects.
    """
    REPORT_TYPES = [
        ('progress', 'Progress Report'),
        ('status', 'Status Update'),
        ('financial', 'Financial Report'),
        ('risk', 'Risk Assessment'),
        ('milestone', 'Milestone Report'),
        ('technical', 'Technical Report'),
        ('other', 'Other')
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="reports"
    )
    title = models.CharField(max_length=255, help_text="Report title")
    content = models.TextField(help_text="Report content")
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPES,
        help_text="Type of report"
    )
    attachments = models.FileField(
        upload_to="project_reports/%Y/%m/",
        help_text="Supporting documents",
        null=True,
        blank=True
    )
    generated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Project Report"
        verbose_name_plural = "Project Reports"

    def __str__(self):
        return f"{self.title} - {self.project.name}"
