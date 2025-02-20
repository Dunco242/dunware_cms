from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.models import Customer, Employee
import uuid
from django.urls import reverse
from slugify import slugify
from django.apps import apps


def get_customer_model():
    return apps.get_model('core', 'Customer')

def get_employee_model():
    return apps.get_model('core', 'Employee')


class Project(models.Model):
    """
    Main project model that represents a customer project
    """

    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    # Basic Information
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    customer = models.ForeignKey('core.Customer', on_delete=models.CASCADE, related_name='projects')

    # Project Details
    project_code = models.CharField(max_length=20, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    # Dates
    start_date = models.DateField()
    target_end_date = models.DateField()
    actual_end_date = models.DateField(null=True, blank=True)

    # Management
    project_manager = models.ForeignKey('core.Employee', on_delete=models.SET_NULL, null=True, related_name='managed_projects')
    team_members = models.ManyToManyField('core.Employee', through='ProjectTeamMember', related_name='project_assignments')

    # Budget & Financials
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Progress Tracking
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='created_projects')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project_code} - {self.name}"

    def save(self, *args, **kwargs):
        """
        Auto-generate a unique project code if not provided.
        """
        if not self.project_code:
            base_code = slugify(self.name)[:10].upper()
            unique_code = base_code
            count = 1

            while Project.objects.filter(project_code=unique_code).exists():
                unique_code = f"{base_code}-{count}"
                count += 1

            self.project_code = unique_code

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Return the URL to view this project."""
        return reverse('customer_projects:project-detail', kwargs={'pk': self.pk})

    def update_progress(self):
        """Calculate and update project progress based on completed tasks"""
        all_tasks = ProjectTask.objects.filter(phase__project=self)
        total_tasks = all_tasks.count()

        if total_tasks > 0:
            completed_tasks = all_tasks.filter(status='done').count()
            self.progress = int((completed_tasks / total_tasks) * 100)
            self.save()

    def calculate_progress(self):
        """Calculate overall project progress based on phase progress"""
        phases = self.phases.all()
        if not phases.exists():
            return 0

        total_progress = sum(phase.progress for phase in phases)
        avg_progress = total_progress / phases.count()

        self.progress = int(avg_progress)
        self.save(update_fields=['progress'])
        return self.progress


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
        return f"{self.employee.get_full_name()} - {self.get_role_display()}"

class ProjectPhase(models.Model):
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold')
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    end_date = models.DateField()
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_completed = models.BooleanField(default=False)

    # Add the calculate_progress method here
    def calculate_progress(self):
        """Calculate and update phase progress based on task status"""
        try:
            phase_tasks = self.tasks.all()
            total_tasks = phase_tasks.count()

            if total_tasks == 0:
                # If no tasks, base progress on phase status
                progress = 100 if self.status == 'completed' else 0
            else:
                # Calculate based on task status
                completed_tasks = phase_tasks.filter(status='done').count()
                in_progress_tasks = phase_tasks.filter(status='in_progress').count()
                in_review_tasks = phase_tasks.filter(status='in_review').count()

                # Weight different statuses
                progress = (
                    (completed_tasks * 100) +
                    (in_review_tasks * 75) +
                    (in_progress_tasks * 50)
                ) / total_tasks

            # Round to nearest integer
            self.progress = round(progress)
            self.save(update_fields=['progress'])

            # Update project progress
            self.project.calculate_progress()

            return self.progress

        except Exception as e:
            logger.error(f"Error calculating phase progress: {str(e)}")
            return 0


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
    dependencies = models.ManyToManyField('self', symmetrical=False, related_name='dependent_tasks', blank=True)

    class Meta:
        ordering = ['due_date', 'priority']

    def __str__(self):
        return f"{self.phase.project.project_code} - {self.title}"


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
    upload_date = models.DateTimeField(auto_now_add=True)
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

    task = models.ForeignKey(
        ProjectTask,
        on_delete=models.CASCADE,
        related_name='time_entries'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='time_entries'
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)
    is_billable = models.BooleanField(default=True)  # ✅ Added missing field
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name_plural = 'Time entries'

    def __str__(self):
        return f"{self.task.phase.project.project_code} - {self.employee.get_full_name()} - {self.date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update task actual hours
        self.task.actual_hours = self.task.time_entries.aggregate(
            total=models.Sum('hours')
        )['total'] or 0
        self.task.save()
class ProjectComment(models.Model):
    """
    Comments on projects, tasks, and documents
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    author = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='project_comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Project Report"
        verbose_name_plural = "Project Reports"

    def __str__(self):
        return f"{self.title} - {self.project.name}"
