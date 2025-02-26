from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView
)
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.db.models import (
    Q, Sum, Count, F, Avg, Max, Min,
    Prefetch, ExpressionWrapper, DecimalField
)
from django.db.models.functions import Coalesce
from django.db import transaction
from django.http import JsonResponse, HttpResponse, FileResponse
from django.utils import timezone
from django.core.exceptions import (
    PermissionDenied, ValidationError,
    ObjectDoesNotExist, MultipleObjectsReturned
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.views.generic import View
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.contrib.contenttypes.models import ContentType

# Core App Models and Forms
from core.models import Employee, Customer
from core.mixins import EmployeeRequiredMixin

# Local Models
from .models import (
    Project, ProjectTeamMember, ProjectPhase, ProjectTask,
    ProjectDocument, ProjectRisk, TimeEntry, ProjectComment, ProjectReport
)

from core.models import Task
from django.utils.text import slugify
from django.db.utils import IntegrityError
from django.contrib import messages
from .models import Project

# Local Forms
from .forms import (
    ProjectForm, ProjectTeamMemberForm, ProjectPhaseForm,
    ProjectTaskForm, ProjectDocumentForm, ProjectRiskForm,
    TimeEntryForm, ProjectCommentForm, ProjectReportForm,
    BulkDocumentUploadForm
)

# Third-party imports
import logging
import csv
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union

# Configure logging
logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class ProjectDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard showing project overview and key metrics"""
    template_name = 'customer_projects/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_profile

        try:
            # Get projects based on user role
            managed_projects = Project.objects.filter(project_manager=employee)
            team_projects = Project.objects.filter(team_members=employee)

            # Get the content type for Project model (to filter generic comments correctly)
            project_content_type = ContentType.objects.get_for_model(Project)

            context.update({
                'managed_projects': managed_projects,
                'team_projects': team_projects,
                'total_projects': managed_projects.count() + team_projects.count(),
                'projects_in_progress': Project.objects.filter(
                    Q(project_manager=employee) | Q(team_members=employee),
                    status='in_progress'
                ).distinct().count(),
                'overdue_tasks': ProjectTask.objects.filter(
                    Q(phase__project__project_manager=employee) |
                    Q(assigned_to=employee),
                    status__in=['todo', 'in_progress'],
                    due_date__lt=timezone.now().date()
                ).count(),
                'recent_activities': ProjectComment.objects.filter(
                    content_type=project_content_type,
                    object_id__in=managed_projects.values_list('id', flat=True)
                ).select_related('author').order_by('-created_at')[:5]
            })
        except Exception as e:
            logger.error(f"Error in project dashboard: {str(e)}")
            messages.error(self.request, "Error loading dashboard data")

        return context

from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q
from datetime import timedelta

class ProjectListView(LoginRequiredMixin, ListView):
    """List all projects the user has access to"""
    model = Project
    template_name = 'customer_projects/project_list.html'
    context_object_name = 'projects'
    paginate_by = 10

    def get_queryset(self):
        employee = self.request.user.employee_profile

        # Base queryset with time metrics
        queryset = Project.objects.filter(
            Q(project_manager=employee) |
            Q(team_members=employee)
        ).annotate(
            project_total_hours=Coalesce(
                Sum('phases__tasks__time_entries__hours'),
                0,
                output_field=DecimalField()
            ),
            project_billable_hours=Coalesce(
                Sum('phases__tasks__time_entries__hours',
                    filter=Q(phases__tasks__time_entries__is_billable=True)),
                0,
                output_field=DecimalField()
            ),
            project_non_billable_hours=Coalesce(
                Sum('phases__tasks__time_entries__hours',
                    filter=Q(phases__tasks__time_entries__is_billable=False)),
                0,
                output_field=DecimalField()
            )
        ).distinct()

        # Apply filters
        search_query = self.request.GET.get('search')
        status_filter = self.request.GET.get('status')
        customer_filter = self.request.GET.get('customer')

        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(project_code__icontains=search_query) |
                Q(customer__company_name__icontains=search_query)
            )

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if customer_filter:
            queryset = queryset.filter(customer_id=customer_filter)

        return queryset.select_related(
            'customer',
            'project_manager'
        ).prefetch_related(
            'phases',
            'phases__tasks',
            'phases__tasks__time_entries'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = self.get_queryset()

        # Calculate the metrics properly using direct aggregation on annotated fields
        metrics = {
            'total_projects': projects.count(),
            'total_hours': projects.aggregate(sum=Sum('project_total_hours'))['sum'] or 0,
            'total_billable': projects.aggregate(sum=Sum('project_billable_hours'))['sum'] or 0,
            'total_non_billable': projects.aggregate(sum=Sum('project_non_billable_hours'))['sum'] or 0,
            'avg_progress': projects.aggregate(avg=Avg('progress'))['avg'] or 0
        }

        context.update({
            'status_choices': Project.STATUS_CHOICES,
            'customers': Customer.objects.all(),
            'current_filters': {
                'search': self.request.GET.get('search', ''),
                'status': self.request.GET.get('status', ''),
                'customer': self.request.GET.get('customer', '')
            },
            'metrics': metrics
        })
        return context

class ProjectDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a project"""
    model = Project
    template_name = 'customer_projects/project_detail.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        # Get project phases with tasks
        phases = ProjectPhase.objects.filter(project=project).prefetch_related('tasks')

        # Modify tasks context to include phase information
        tasks = []
        for phase in phases:
            phase_tasks = phase.tasks.all()
            for task in phase_tasks:
                task.phase_id = phase.id  # Add phase_id to each task
                tasks.append(task)

        # Calculate project metrics
        task_metrics = ProjectTask.objects.filter(phase__project=project).aggregate(
            total_tasks=Count('id'),
            completed_tasks=Count('id', filter=Q(status='done')),
            overdue_tasks=Count('id', filter=Q(
                status__in=['todo', 'in_progress'],
                due_date__lt=timezone.now().date()
            ))
        )

        # Calculate time and cost metrics
        time_metrics = TimeEntry.objects.filter(task__phase__project=project).aggregate(
            total_hours=Sum('hours'),
            billable_hours=Sum('hours', filter=Q(is_billable=True)),
            non_billable_hours=Sum('hours', filter=Q(is_billable=False))
        )

        # Calculate completion percentage
        completion_percentage = (
            (task_metrics['completed_tasks'] / task_metrics['total_tasks'] * 100)
            if task_metrics['total_tasks'] > 0 else 0
        )

        # Time Entry Form
        time_entry_form = TimeEntryForm()

        context.update({
            'phases': phases,
            'tasks': tasks,
            'team_members': project.team_members.all(),
            'documents': project.documents.all().order_by('-upload_date')[:5],
            'risks': project.risks.all().order_by('-risk_level')[:5],
            'task_metrics': task_metrics,
            'time_metrics': time_metrics,
            'completion_percentage': completion_percentage,
            'recent_activities': ProjectComment.objects.filter(
                content_type__model='project',
                object_id=project.id
            ).select_related('author').order_by('-created_at')[:5],
            'time_entry_form': time_entry_form,
        })

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests for project actions, including time entry creation"""
        project = self.get_object()
        action = request.POST.get('action')

        if action == 'update_status':
            return self._handle_status_update(request, project)
        elif action == 'add_comment':
            return self._handle_add_comment(request, project)
        elif action == 'add_time_entry':
            return self._handle_add_time_entry(request, project)

        return redirect(request.path)

    def _handle_add_time_entry(self, request, project):
        """Handle adding a time entry to a task within the project"""
        time_entry_form = TimeEntryForm(request.POST)
        if time_entry_form.is_valid():
            try:
                time_entry = time_entry_form.save(commit=False)
                task_id = request.POST.get('task')
                task = get_object_or_404(ProjectTask, pk=task_id, phase__project=project)

                # Retrieve the Employee instance correctly
                employee = Employee.objects.filter(user=request.user).first()
                if not employee:
                    messages.error(request, "You are not associated with an employee profile.")
                    return redirect(request.path)

                time_entry.task = task
                time_entry.employee = employee
                time_entry.save()

                messages.success(request, "Time entry added successfully.")
                return redirect(request.path)

            except Exception as e:
                messages.error(request, f"Error adding time entry: {str(e)}")
                return redirect(request.path)

        messages.error(request, "There was an error with the time entry form.")
        return redirect(request.path)

    def _handle_status_update(self, request, project):
        """Handle project status updates"""
        employee = Employee.objects.filter(user=request.user).first()
        if not employee or project.project_manager != employee:
            messages.error(request, "Permission denied.")
            return redirect(request.path)

        new_status = request.POST.get('status')
        if new_status not in dict(Project.STATUS_CHOICES):
            messages.error(request, "Invalid project status selected.")
            return redirect(request.path)

        try:
            old_status = project.status
            project.status = new_status
            project.save()

            # Log the status change
            ProjectComment.objects.create(
                content_object=project,
                author=employee,
                text=f"Project status updated from {old_status} to {new_status}"
            )

            messages.success(request, f"Project status updated to {project.get_status_display()}")
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f"Error updating project status: {str(e)}")
            return redirect(request.path)

    def _handle_add_comment(self, request, project):
        """Handle adding comments to the project"""
        comment_text = request.POST.get('comment')
        if not comment_text:
            messages.error(request, "Comment text is required.")
            return redirect(request.path)

        try:
            employee = Employee.objects.filter(user=request.user).first()
            if not employee:
                messages.error(request, "You are not associated with an employee profile.")
                return redirect(request.path)

            ProjectComment.objects.create(
                content_object=project,
                author=employee,
                text=comment_text
            )

            messages.success(request, "Comment added successfully.")
            return redirect(request.path)
        except Exception as e:
            messages.error(request, f"Error adding comment: {str(e)}")
            return redirect(request.path)


class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'customer_projects/project_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not self.request.user.employee_profile:
            messages.error(self.request, "You must have an employee profile to create a project.")
            return self.form_invalid(form)

        form.instance.project_manager = self.request.user.employee_profile
        return super().form_valid(form)

    def form_invalid(self, form):
        errors = form.errors.as_json()
        logger.warning(f"Form errors: {errors}")
        messages.error(self.request, f"There was an error saving the project: {errors}")
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('customer_projects:project-detail', kwargs={'pk': self.object.pk})
# customer_projects/views.py

class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'customer_projects/project_form.html'

    def get_queryset(self):
        return Project.objects.filter(
            project_manager=self.request.user.employee_profile
        ).select_related('project_manager', 'customer')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_update'] = True
        context['project'] = self.get_object()
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Store old status for comparison
                old_status = self.get_object().status
                new_status = form.cleaned_data['status']

                response = super().form_valid(form)

                # Log the status change if it changed
                if old_status != new_status:
                    ProjectComment.objects.create(
                        content_object=self.object,
                        author=self.request.user.employee_profile,
                        text=f"Project status updated from {old_status} to {new_status}"
                    )

                messages.success(self.request, "Project updated successfully.")
                return response
        except Exception as e:
            logger.error(f"Error updating project: {str(e)}")
            messages.error(self.request, "Error updating project. Please try again.")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('customer_projects:project-detail', kwargs={'pk': self.object.pk})

class ProjectDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete a project"""
    model = Project
    template_name = 'customer_projects/project_confirm_delete.html'
    success_url = reverse_lazy('customer_projects:project-list')

    def test_func(self):
        project = self.get_object()
        return self.request.user.employee_profile == project.project_manager

    def delete(self, request, *args, **kwargs):
        project = self.get_object()
        try:
            # Check for active tasks
            active_tasks = ProjectTask.objects.filter(
                phase__project=project,
                status__in=['todo', 'in_progress']
            ).exists()

            if active_tasks:
                messages.error(request, "Cannot delete project with active tasks.")
                return redirect('customer_projects:project-detail', pk=project.pk)

            project.delete()
            messages.success(request, "Project deleted successfully.")
            return redirect(self.success_url)

        except Exception as e:
            logger.error(f"Error deleting project: {str(e)}")
            messages.error(request, "Error deleting project. Please try again.")
            return redirect('customer_projects:project-detail', pk=project.pk)

@login_required
def export_project_data(request, project_id):
    """Export project data to CSV"""
    project = get_object_or_404(Project, pk=project_id)

    # Verify permissions
    if not (project.project_manager == request.user.employee_profile or
            request.user.employee_profile in project.team_members.all()):
        raise PermissionDenied

    try:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{project.project_code}_export.csv"'

        writer = csv.writer(response)

        # Write project details
        writer.writerow(['Project Details'])
        writer.writerow(['Code', 'Name', 'Status', 'Progress', 'Start Date', 'Target End Date'])
        writer.writerow([
            project.project_code,
            project.name,
            project.get_status_display(),
            f"{project.progress}%",
            project.start_date,
            project.target_end_date
        ])

        # Write task details
        writer.writerow([])
        writer.writerow(['Tasks'])
        writer.writerow(['Phase', 'Task', 'Status', 'Assigned To', 'Due Date', 'Hours'])

        for phase in project.phases.all():
            for task in phase.tasks.all():
                writer.writerow([
                    phase.name,
                    task.title,
                    task.get_status_display(),
                    task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned',
                    task.due_date,
                    task.actual_hours or 0
                ])

        return response
    except Exception as e:
        logger.error(f"Error exporting project data: {str(e)}")
        messages.error(request, "Error exporting project data. Please try again.")
        return redirect('customer_projects:project-detail', pk=project_id)

# Team Management Views
class TeamManagementView(LoginRequiredMixin, UpdateView):
    """Manage project team members and their roles"""
    model = Project
    template_name = 'customer_projects/team_management.html'
    form_class = ProjectTeamMemberForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        context.update({
            'team_members': ProjectTeamMember.objects.filter(project=project)
                .select_related('employee')
                .order_by('role', 'employee__user__first_name'),
            'available_employees': Employee.objects.exclude(
                id__in=project.team_members.values_list('id', flat=True)
            ),
            'role_choices': ProjectTeamMember.ROLE_CHOICES
        })
        return context

    def post(self, request, *args, **kwargs):
        project = self.get_object()
        action = request.POST.get('action')

        if action == 'add_member':
            return self.add_team_member(request, project)
        elif action == 'remove_member':
            return self.remove_team_member(request, project)
        elif action == 'update_role':
            return self.update_member_role(request, project)

        return JsonResponse({'error': 'Invalid action'}, status=400)

    def add_team_member(self, request, project):
        try:
            employee_id = request.POST.get('employee_id')
            role = request.POST.get('role')

            if not all([employee_id, role]):
                return JsonResponse({'error': 'Missing required fields'}, status=400)

            employee = get_object_or_404(Employee, id=employee_id)

            team_member = ProjectTeamMember.objects.create(
                project=project,
                employee=employee,
                role=role
            )

            messages.success(request, f"{employee.get_full_name()} added to the project team.")
            return JsonResponse({'status': 'success'})

        except Exception as e:
            logger.error(f"Error adding team member: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)

    def remove_team_member(self, request, project):
        try:
            member_id = request.POST.get('member_id')
            team_member = get_object_or_404(ProjectTeamMember,
                id=member_id, project=project
            )

            # Check if member has any assigned tasks
            assigned_tasks = ProjectTask.objects.filter(
                assigned_to=team_member.employee,
                phase__project=project,
                status__in=['todo', 'in_progress']
            )

            if assigned_tasks.exists():
                return JsonResponse({
                    'error': 'Cannot remove member with assigned tasks'
                }, status=400)

            team_member.delete()
            messages.success(request, f"{team_member.employee.get_full_name()} removed from the project team.")
            return JsonResponse({'status': 'success'})

        except Exception as e:
            logger.error(f"Error removing team member: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)

    def update_member_role(self, request, project):
        try:
            member_id = request.POST.get('member_id')
            new_role = request.POST.get('role')

            team_member = get_object_or_404(ProjectTeamMember,
                id=member_id, project=project
            )
            old_role = team_member.get_role_display()

            team_member.role = new_role
            team_member.save()

            messages.success(
                request,
                f"Updated {team_member.employee.get_full_name()}'s role from {old_role} to {team_member.get_role_display()}"
            )
            return JsonResponse({'status': 'success'})

        except Exception as e:
            logger.error(f"Error updating team member role: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)

class TaskListView(LoginRequiredMixin, ListView):
    """List all tasks for a project phase"""
    model = ProjectTask
    template_name = 'customer_projects/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        self.phase = get_object_or_404(ProjectPhase, pk=self.kwargs['phase_id'])
        return ProjectTask.objects.filter(phase=self.phase)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phase'] = self.phase
        context['project'] = self.phase.project
        return context

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = ProjectTask
    form_class = ProjectTaskForm
    template_name = 'customer_projects/task_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.phase = get_object_or_404(ProjectPhase, pk=self.kwargs.get('phase_id'))
        self.project = self.phase.project
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form_class = self.get_form_class()
        form = form_class(**self.get_form_kwargs())

        # Get all employees for assignment
        employees = Employee.objects.filter(is_active=True)

        # Get existing tasks from this project for dependencies
        existing_tasks = ProjectTask.objects.filter(
            phase__project=self.project
        ).exclude(id=getattr(self, 'object_id', None))

        # Update form querysets
        form.fields['assigned_to'].queryset = employees
        form.fields['assigned_to'].empty_label = "Select Employee"

        form.fields['dependencies'].queryset = existing_tasks
        form.fields['dependencies'].widget.attrs.update({
            'class': 'form-control select2',  # Add select2 for better UX with multiple select
            'data-placeholder': 'Select Dependencies'
        })

        # Remove the phase field since we're setting it automatically
        if 'phase' in form.fields:
            del form.fields['phase']

        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'phase': self.phase,
            'project': self.project,
        })
        return context

    def form_valid(self, form):
        form.instance.phase = self.phase
        try:
            response = super().form_valid(form)
            messages.success(self.request, "Task added successfully.")
            return response
        except Exception as e:
            messages.error(self.request, f"Error saving task: {str(e)}")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('customer_projects:project-task-list', kwargs={'project_id': self.phase.project.id, 'phase_id': self.phase.id})


logger = logging.getLogger(__name__)

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectTask
    template_name = 'customer_projects/task_form.html'
    form_class = ProjectTaskForm

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.project = self.object.phase.project
        self.phase = self.object.phase
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        """
        Custom method to handle potential multiple object returns
        """
        try:
            # Use the queryset from get_queryset()
            queryset = self.get_queryset()
            pk = self.kwargs.get('pk')

            # Try to get a single object, with special handling for multiple returns
            try:
                return queryset.get(pk=pk)
            except MultipleObjectsReturned:
                # Log the issue
                logger.warning(f"Multiple tasks found with ID {pk}")

                # Return the first task from the filtered queryset
                task = queryset.filter(pk=pk).first()

                # Optional: add a message to inform about the issue
                messages.warning(self.request, "Multiple tasks were found. The first task is being edited.")

                return task

        except ProjectTask.DoesNotExist:
            # Raise a 404 if no task is found
            raise Http404("Task not found")

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return ProjectTask.objects.filter(
            Q(phase__project__project_manager=employee) |
            Q(phase__project__team_members=employee) |
            Q(assigned_to=employee)
        ).select_related(
            'phase',
            'phase__project',
            'assigned_to'
        ).distinct()

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        # Get all employees for assignment
        employees = Employee.objects.filter(is_active=True)

        # Get existing tasks from this project for dependencies
        existing_tasks = ProjectTask.objects.filter(
            phase__project=self.project
        ).exclude(id=self.object.id)

        # Update form querysets
        form.fields['assigned_to'].queryset = employees
        form.fields['assigned_to'].empty_label = "Select Employee"
        form.fields['dependencies'].queryset = existing_tasks
        form.fields['dependencies'].widget.attrs.update({
            'class': 'form-control select2',
            'data-placeholder': 'Select Dependencies'
        })

        return form

    def form_valid(self, form):
        try:
            old_status = self.object.status
            response = super().form_valid(form)

            # If status changed, recalculate progress
            if old_status != form.instance.status:
                self.calculate_phase_progress(self.object.phase)
                self.calculate_project_progress(self.object.phase.project)

            messages.success(self.request, f"Task '{form.instance.title}' updated successfully.")
            return response
        except Exception as e:
            logger.error(f"Error updating task: {str(e)}")
            messages.error(self.request, f"Error updating task: {str(e)}")
            return self.form_invalid(form)


    def calculate_phase_progress(self, phase):
        """Calculate and update phase progress"""
        try:
            phase_tasks = ProjectTask.objects.filter(phase=phase)
            total_tasks = phase_tasks.count()

            if total_tasks > 0:
                completed_tasks = phase_tasks.filter(status='done').count()
                in_progress_tasks = phase_tasks.filter(status='in_progress').count()
                in_review_tasks = phase_tasks.filter(status='in_review').count()

                # Calculate weighted progress
                progress = (
                    (completed_tasks * 100) +  # Done tasks count as 100%
                    (in_review_tasks * 75) +   # In Review tasks count as 75%
                    (in_progress_tasks * 50)    # In Progress tasks count as 50%
                ) / total_tasks

                phase.progress = round(progress)
                phase.save(update_fields=['progress'])
                return phase.progress
            return 0
        except Exception as e:
            logger.error(f"Error calculating phase progress: {str(e)}")
            return 0

    def calculate_project_progress(self, project):
        """Calculate and update project progress"""
        try:
            phases = project.phases.all()
            if not phases.exists():
                return 0

            total_progress = sum(phase.progress for phase in phases)
            project_progress = round(total_progress / phases.count())

            project.progress = project_progress
            project.save(update_fields=['progress'])

            return project_progress
        except Exception as e:
            logger.error(f"Error calculating project progress: {str(e)}")
            return 0

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'project': self.project,
            'phase': self.phase,
            'task': self.object,
            'is_update': True
        })
        return context

    def get_success_url(self):
        """Return to the project task detail view after successful update"""
        return reverse('customer_projects:project-task-detail', kwargs={
            'project_id': self.project.id,
            'phase_id': self.phase.id,
            'pk': self.object.id
        })


class TaskDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view for both generic and project-specific tasks
    """
    template_name = 'customer_projects/task_detail.html'
    context_object_name = 'task'

    def get_queryset(self):
        """
        Check and retrieve task from both Task and ProjectTask models
        """
        employee = self.request.user.employee_profile

        # Try ProjectTask first
        project_task_queryset = ProjectTask.objects.filter(
            Q(phase__project__project_manager=employee) |
            Q(phase__project__team_members=employee) |
            Q(assigned_to=employee)
        ).select_related(
            'phase',
            'phase__project',
            'assigned_to',
            'assigned_to__user'
        )

        # Try generic Task
        generic_task_queryset = Task.objects.filter(
            Q(assigned_to=employee) |
            Q(created_by=employee)
        ).select_related(
            'assigned_to',
            'assigned_to__user'
        )

        return project_task_queryset | generic_task_queryset

    def get_object(self, queryset=None):
        """
        Override get_object to try both Task and ProjectTask models
        """
        pk = self.kwargs.get('pk')

        try:
            # First, try to get a ProjectTask
            return ProjectTask.objects.get(pk=pk)
        except ProjectTask.DoesNotExist:
            try:
                # If not a ProjectTask, try a generic Task
                return Task.objects.get(pk=pk)
            except Task.DoesNotExist:
                raise Http404("No task found matching the query")

    def get_context_data(self, **kwargs):
        """
        Add additional context based on task type
        """
        context = super().get_context_data(**kwargs)
        task = self.get_object()

        if isinstance(task, ProjectTask):
            # Project task specific context
            context.update({
                'project': task.phase.project,
                'phase': task.phase,
                'time_entries': TimeEntry.objects.filter(task=task),
                'comments': ProjectComment.objects.filter(
                    content_type__model='projecttask',
                    object_id=task.id
                ).select_related('author', 'author__user')
            })
        elif isinstance(task, Task):
            # Generic task context
            context.update({
                'is_generic_task': True
            })

        # Check edit permissions
        employee = self.request.user.employee_profile
        context['can_edit'] = (
            (isinstance(task, ProjectTask) and
             (task.phase.project.project_manager == employee or
              employee in task.phase.project.team_members.all())) or
            (isinstance(task, Task) and
             (task.assigned_to == employee or task.created_by == employee))
        )

        # Determine update URL
        if isinstance(task, ProjectTask):
            context['update_url'] = reverse('customer_projects:task-update', kwargs={'pk': task.pk})
        else:
            context['update_url'] = reverse('task-update', kwargs={'pk': task.pk})

        return context


class TimeEntryCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new time entry for a task
    """
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'customer_projects/time_entry_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.task = get_object_or_404(ProjectTask, pk=self.kwargs['task_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['task'] = self.task
        return kwargs

    def form_valid(self, form):
        try:
            form.instance.task = self.task
            form.instance.employee = self.request.user.employee_profile

            response = super().form_valid(form)
            messages.success(
                self.request,
                f"Time entry of {form.instance.hours} hours recorded successfully."
            )
            return response

        except Exception as e:
            logger.error(f"Error creating time entry: {str(e)}")
            messages.error(self.request, "Error recording time entry. Please try again.")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('customer_projects:task-detail', kwargs={'pk': self.task.pk})

class TimeEntryUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing time entry
    """
    model = TimeEntry
    form_class = TimeEntryForm
    template_name = 'customer_projects/time_entry_form.html'

    def get_queryset(self):
        return TimeEntry.objects.filter(employee=self.request.user.employee_profile)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['task'] = self.object.task
        return kwargs

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            messages.success(
                self.request,
                f"Time entry updated to {form.instance.hours} hours."
            )
            return response
        except Exception as e:
            logger.error(f"Error updating time entry: {str(e)}")
            messages.error(self.request, "Error updating time entry. Please try again.")
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('customer_projects:task-detail', kwargs={'pk': self.object.task.pk})

class DocumentListView(LoginRequiredMixin, ListView):
    """
    List all documents for a project
    """
    model = ProjectDocument
    template_name = 'customer_projects/document_list.html'
    context_object_name = 'documents'
    paginate_by = 20

    def get_queryset(self):
        self.project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        return ProjectDocument.objects.filter(project=self.project).order_by('-upload_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context

@login_required
def document_upload(request, project_id):
    """
    Handle document upload with progress tracking
    """
    project = get_object_or_404(Project, pk=project_id)

    if request.method == 'POST':
        form = ProjectDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                document = form.save(commit=False)
                document.project = project
                document.uploaded_by = request.user.employee_profile
                document.save()

                if request.is_ajax():
                    return JsonResponse({
                        'status': 'success',
                        'document': {
                            'id': document.id,
                            'title': document.title,
                            'url': document.file.url,
                            'uploaded_by': document.uploaded_by.get_full_name(),
                            'upload_date': document.upload_date.strftime('%Y-%m-%d %H:%M')
                        }
                    })

                messages.success(request, "Document uploaded successfully.")
                return redirect('customer_projects:project-detail', pk=project_id)

            except Exception as e:
                logger.error(f"Error uploading document: {str(e)}")
                if request.is_ajax():
                    return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
                messages.error(request, "Error uploading document. Please try again.")
    else:
        form = ProjectDocumentForm()

    return render(request, 'customer_projects/document_upload.html', {
        'form': form,
        'project': project
    })

@login_required
def document_download(request, document_id):
    """
    Handle secure document download
    """
    document = get_object_or_404(ProjectDocument, pk=document_id)
    project = document.project

    # Check permissions
    if not (project.project_manager == request.user.employee_profile or
            request.user.employee_profile in project.team_members.all()):
        raise PermissionDenied

    try:
        response = FileResponse(
            document.file,
            content_type='application/force-download'
        )
        response['Content-Disposition'] = f'attachment; filename="{document.file.name}"'
        return response
    except Exception as e:
        logger.error(f"Error downloading document: {str(e)}")
        messages.error(request, "Error downloading document. Please try again.")
        return redirect('customer_projects:project-detail', pk=project.pk)

class ProjectCommentCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new comment on a project item
    """
    model = ProjectComment
    form_class = ProjectCommentForm
    template_name = 'customer_projects/comment_form.html'

    def form_valid(self, form):
        try:
            form.instance.author = self.request.user.employee_profile

            # Set the content object based on comment type
            content_type = self.request.POST.get('content_type')
            object_id = self.request.POST.get('object_id')

            if content_type == 'project':
                form.instance.content_object = get_object_or_404(Project, pk=object_id)
            elif content_type == 'task':
                form.instance.content_object = get_object_or_404(ProjectTask, pk=object_id)
            elif content_type == 'risk':
                form.instance.content_object = get_object_or_404(ProjectRisk, pk=object_id)
            else:
                raise ValueError("Invalid content type")

            response = super().form_valid(form)

            if self.request.is_ajax():
                return JsonResponse({
                    'status': 'success',
                    'comment': {
                        'id': form.instance.id,
                        'text': form.instance.text,
                        'author': form.instance.author.get_full_name(),
                        'created_at': form.instance.created_at.strftime('%Y-%m-%d %H:%M')
                    }
                })

            messages.success(self.request, "Comment added successfully.")
            return response

        except Exception as e:
            logger.error(f"Error creating comment: {str(e)}")
            messages.error(self.request, "Error creating comment. Please try again.")
            return self.form_invalid(form)

    def get_success_url(self):
        content_type = self.request.POST.get('content_type')
        object_id = self.request.POST.get('object_id')

        if content_type == 'project':
            return reverse('customer_projects:project-detail', kwargs={'pk': object_id})
        elif content_type == 'task':
            return reverse('customer_projects:task-detail', kwargs={'pk': object_id})
        elif content_type == 'risk':
            return reverse('customer_projects:risk-detail', kwargs={'pk': object_id})

        return reverse('customer_projects:project-list')


class RiskUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update a project risk
    """
    model = ProjectRisk
    form_class = ProjectRiskForm
    template_name = 'customer_projects/risk_form.html'

    def get_success_url(self):
        return reverse('customer_projects:project-detail', kwargs={'pk': self.object.project.id})

# Project Reports Views
class ProjectReportView(LoginRequiredMixin, DetailView):
    """
    Generate detailed project report
    """
    model = Project
    template_name = 'customer_projects/project_report.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        # Task Statistics
        task_stats = ProjectTask.objects.filter(phase__project=project).aggregate(
            total_tasks=Count('id'),
            completed_tasks=Count('id', filter=Q(status='done')),
            total_hours=Sum('actual_hours'),
            overdue_tasks=Count('id', filter=Q(
                status__in=['todo', 'in_progress'],
                due_date__lt=timezone.now().date()
            ))
        )

        # Time Tracking
        time_entries = TimeEntry.objects.filter(
            task__phase__project=project
        ).select_related('employee', 'task')

        # Risk Analysis
        risk_analysis = ProjectRisk.objects.filter(project=project).aggregate(
            high_risks=Count('id', filter=Q(risk_level='high')),
            medium_risks=Count('id', filter=Q(risk_level='medium')),
            low_risks=Count('id', filter=Q(risk_level='low')),
            open_risks=Count('id', filter=Q(status__in=['identified', 'assessed']))
        )

        context.update({
            'task_stats': task_stats,
            'time_entries': time_entries,
            'risk_analysis': risk_analysis,
            'team_utilization': self.get_team_utilization(project),
            'phase_progress': self.get_phase_progress(project)
        })

        return context

    def get_team_utilization(self, project):
        """Calculate team member utilization"""
        team_utilization = []
        for member in project.team_members.all():
            time_logged = TimeEntry.objects.filter(
                task__phase__project=project,
                employee=member
            ).aggregate(total_hours=Sum('hours'))['total_hours'] or 0

            team_utilization.append({
                'member': member,
                'hours_logged': time_logged,
                'allocation_percentage': ProjectTeamMember.objects.get(
                    project=project,
                    employee=member
                ).allocation_percentage
            })
        return team_utilization

    def get_phase_progress(self, project):
        """Calculate progress for each project phase"""
        phases = []
        for phase in project.phases.all():
            task_stats = phase.tasks.aggregate(
                total=Count('id'),
                completed=Count('id', filter=Q(status='done'))
            )
            if task_stats['total'] > 0:
                progress = (task_stats['completed'] / task_stats['total']) * 100
            else:
                progress = 0

            phases.append({
                'phase': phase,
                'progress': progress,
                'task_stats': task_stats
            })
        return phases

# Comments and Discussion Views
@login_required
def add_comment(request, project_id):
    """
    Add a comment to a project or task
    """
    if request.method == 'POST':
        form = ProjectCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user.employee_profile

            # Set the content object based on comment type
            content_type = request.POST.get('content_type')
            object_id = request.POST.get('object_id')

            if content_type == 'project':
                comment.content_object = get_object_or_404(Project, pk=object_id)
            elif content_type == 'task':
                comment.content_object = get_object_or_404(ProjectTask, pk=object_id)

            comment.save()

            if request.is_ajax():
                return JsonResponse({
                    'status': 'success',
                    'comment': {
                        'id': comment.id,
                        'text': comment.text,
                        'author': comment.author.get_full_name(),
                        'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
                    }
                })

            messages.success(request, "Comment added successfully.")
            return redirect(request.POST.get('next', 'customer_projects:project-list'))

    return JsonResponse({'error': 'Invalid request'}, status=400)

# Project Analytics Views
class ProjectAnalyticsView(LoginRequiredMixin, TemplateView):
    """
    Project analytics and metrics dashboard
    """
    template_name = 'customer_projects/project_analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_profile

        # Get projects where user is manager or team member
        projects = Project.objects.filter(
            Q(project_manager=employee) | Q(team_members=employee)
        ).distinct()

        # Project Status Distribution
        status_distribution = projects.values('status').annotate(
            count=Count('id')
        ).order_by('status')

        # Task Status Distribution
        task_distribution = ProjectTask.objects.filter(
            phase__project__in=projects
        ).values('status').annotate(
            count=Count('id')
        ).order_by('status')

        # Time Tracking Analysis
        time_analysis = TimeEntry.objects.filter(
            task__phase__project__in=projects
        ).aggregate(
            total_hours=Sum('hours'),
            billable_hours=Sum('hours', filter=Q(is_billable=True)),
            non_billable_hours=Sum('hours', filter=Q(is_billable=False))
        )

        # Risk Analysis
        risk_analysis = ProjectRisk.objects.filter(
            project__in=projects
        ).values('risk_level').annotate(
            count=Count('id')
        ).order_by('risk_level')

        context.update({
            'status_distribution': status_distribution,
            'task_distribution': task_distribution,
            'time_analysis': time_analysis,
            'risk_analysis': risk_analysis,
            'project_progress': self.get_project_progress(projects),
            'team_performance': self.get_team_performance(projects)
        })

        return context

    def get_project_progress(self, projects):
        """Calculate progress metrics for projects"""
        return projects.annotate(
            total_tasks=Count('phases__tasks'),
            completed_tasks=Count(
                'phases__tasks',
                filter=Q(phases__tasks__status='done')
            )
        ).annotate(
            progress_percentage=F('completed_tasks') * 100.0 / F('total_tasks')
        )

    def get_team_performance(self, projects):
        """Calculate team performance metrics"""
        return Employee.objects.filter(
            Q(managed_projects__in=projects) |
            Q(project_assignments__project__in=projects)
        ).distinct().annotate(
            tasks_assigned=Count('project_tasks'),
            tasks_completed=Count(
                'project_tasks',
                filter=Q(project_tasks__status='done')
            ),
            hours_logged=Sum('time_entries__hours')
        )

# Export Views
@login_required
def export_project_data(request, project_id):
    """
    Export project data to CSV
    """
    project = get_object_or_404(Project, pk=project_id)

    # Verify permissions
    if not (project.project_manager == request.user.employee_profile or
            request.user.employee_profile in project.team_members.all()):
        raise PermissionDenied

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{project.project_code}_export.csv"'

    writer = csv.writer(response)

    # Write project details
    writer.writerow(['Project Details'])
    writer.writerow(['Code', 'Name', 'Status', 'Progress', 'Start Date', 'Target End Date'])
    writer.writerow([
        project.project_code,
        project.name,
        project.get_status_display(),
        f"{project.progress}%",
        project.start_date,
        project.target_end_date
    ])

    # Write task details
    writer.writerow([])
    writer.writerow(['Tasks'])
    writer.writerow(['Phase', 'Task', 'Status', 'Assigned To', 'Due Date', 'Hours'])

    for phase in project.phases.all():
        for task in phase.tasks.all():
            writer.writerow([
                phase.name,
                task.title,
                task.get_status_display(),
                task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned',
                task.due_date,
                task.actual_hours or 0
            ])

    return response

def form_valid(self, form):
        try:
            with transaction.atomic():
                form.instance.created_by = self.request.user.employee_profile

                # Save the project
                response = super().form_valid(form)

                # Create initial project phase
                ProjectPhase.objects.create(
                    project=self.object,
                    name="Planning",
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data['target_end_date']
                )

                # Add project manager to team members
                if form.instance.project_manager:
                    ProjectTeamMember.objects.create(
                        project=self.object,
                        employee=form.instance.project_manager,
                        role='lead'
                    )

                messages.success(self.request, "Project created successfully.")
                return response

        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            messages.error(self.request, "Error creating project. Please try again.")
            return super().form_invalid(form)

class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing project
    """
    model = Project
    form_class = ProjectForm
    template_name = 'customer_projects/project_form.html'
    success_url = reverse_lazy('customer_projects:project-list')

    def get_queryset(self):
        # Only allow project managers to update projects
        return Project.objects.filter(project_manager=self.request.user.employee_profile)

    def form_valid(self, form):
        messages.success(self.request, "Project updated successfully.")
        return super().form_valid(form)

class ProjectDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Delete a project
    """
    model = Project
    template_name = 'customer_projects/project_confirm_delete.html'
    success_url = reverse_lazy('customer_projects:project-list')

    def test_func(self):
        project = self.get_object()
        return self.request.user.employee_profile == project.project_manager

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Project deleted successfully.")
        return super().delete(request, *args, **kwargs)

# Project Team Views
class TeamMemberCreateView(LoginRequiredMixin, CreateView):
    """
    View to add a team member to a project.
    """
    model = ProjectTeamMember
    form_class = ProjectTeamMemberForm
    template_name = "customer_projects/team_member_form.html"

    def get_form_kwargs(self):
        """
        Pass the current project instance to the form.
        """
        kwargs = super().get_form_kwargs()
        kwargs['project'] = get_object_or_404(Project, id=self.kwargs['project_id'])
        return kwargs

    def form_valid(self, form):
        """
        Set the project before saving the team member.
        """
        form.instance.project = get_object_or_404(Project, id=self.kwargs['project_id'])
        messages.success(self.request, "Team member added successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """
        Include project details in context.
        """
        context = super().get_context_data(**kwargs)
        context["project"] = get_object_or_404(Project, id=self.kwargs["project_id"])
        return context

    def get_success_url(self):
        """
        Redirect to the correct team list with project_id.
        """
        return reverse("customer_projects:team-list", kwargs={"project_id": self.kwargs["project_id"]})
# Project Phase Views
class PhaseListView(LoginRequiredMixin, ListView):

    """
    List all phases for a project
    """
    model = ProjectPhase
    template_name = 'customer_projects/phase_list.html'
    context_object_name = 'phases'

    def get_queryset(self):
        self.project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        return ProjectPhase.objects.filter(project=self.project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context

# Task Views
class TaskListView(LoginRequiredMixin, ListView):
    """
    List all tasks for a project phase
    """
    model = ProjectTask
    template_name = 'customer_projects/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        self.phase = get_object_or_404(ProjectPhase, pk=self.kwargs['phase_id'])
        return ProjectTask.objects.filter(phase=self.phase)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phase'] = self.phase
        context['project'] = self.phase.project
        return context

# class TaskCreateView(LoginRequiredMixin, CreateView):
#     """
#     Create a new task
#     """
#     model = ProjectTask
#     form_class = ProjectTaskForm
#     template_name = 'customer_projects/task_form.html'

#     def get_phase(self):
#         return get_object_or_404(ProjectPhase, pk=self.kwargs['phase_id'])

#     def form_valid(self, form):
#         form.instance.phase = self.get_phase()
#         messages.success(self.request, "Task created successfully.")
#         return super().form_valid(form)

#     def get_success_url(self):
#         return reverse('customer_projects:phase-detail', kwargs={'pk': self.kwargs['phase_id']})

# Document Views
class DocumentUploadView(LoginRequiredMixin, CreateView):
    """
    Upload a project document
    """
    model = ProjectDocument
    form_class = ProjectDocumentForm
    template_name = 'customer_projects/document_form.html'

    def form_valid(self, form):
        form.instance.project_id = self.kwargs['project_id']
        form.instance.uploaded_by = self.request.user.employee_profile
        messages.success(self.request, "Document uploaded successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect to the project documents list after a successful upload"""
        return reverse("customer_projects:document-list", kwargs={"project_id": self.kwargs["project_id"]})

# Time Entry Views
@login_required
def time_entry_create(request, task_id):
    """
    Create a time entry for a task
    """
    task = get_object_or_404(ProjectTask, pk=task_id)

    if request.method == 'POST':
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            time_entry = form.save(commit=False)
            time_entry.task = task
            time_entry.employee = request.user.employee_profile
            time_entry.save()

            messages.success(request, "Time entry recorded successfully.")
            return redirect('customer_projects:task-detail', pk=task_id)
    else:
        form = TimeEntryForm()

    return render(request, 'customer_projects/time_entry_form.html', {
        'form': form,
        'task': task
    })

# API Endpoints
@login_required
def update_task_status(request):
    """Update task status via AJAX"""
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        new_status = request.POST.get('status')

        task = get_object_or_404(ProjectTask, pk=task_id)

        # Verify permissions
        if task.assigned_to != request.user.employee_profile:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        try:
            old_status = task.status
            task.status = new_status
            task.save()

            # Calculate new progress
            progress = task.phase.calculate_progress()

            return JsonResponse({
                'status': 'success',
                'new_status': task.get_status_display(),
                'phase_progress': progress,
                'project_progress': task.phase.project.progress
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)
@login_required
def project_progress_update(request, project_id):
    """
    Update project progress via AJAX
    """
    if request.method == 'POST':
        project = get_object_or_404(Project, pk=project_id)

        # Verify permissions
        if project.project_manager != request.user.employee_profile:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        try:
            progress = int(request.POST.get('progress', 0))
            if 0 <= progress <= 100:
                project.progress = progress
                project.save()
                return JsonResponse({
                    'status': 'success',
                    'progress': progress
                })
            else:
                return JsonResponse({
                    'error': 'Progress must be between 0 and 100'
                }, status=400)
        except ValueError:
            return JsonResponse({
                'error': 'Invalid progress value'
            }, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)

class ProjectTimelineView(LoginRequiredMixin, DetailView):
    """
    Project timeline and Gantt chart view
    """
    model = Project
    template_name = 'customer_projects/project_timeline.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        # Get all phases and tasks for the timeline
        phases = ProjectPhase.objects.filter(project=project).prefetch_related(
            'tasks',
            'tasks__assigned_to'
        )

        # Prepare timeline data
        timeline_data = []
        for phase in phases:
            timeline_data.append({
                'id': f'phase_{phase.id}',
                'type': 'phase',
                'name': phase.name,
                'start': phase.start_date.isoformat(),
                'end': phase.end_date.isoformat(),
                'progress': phase.progress if hasattr(phase, 'progress') else 0,
                'dependencies': []
            })

            for task in phase.tasks.all():
                timeline_data.append({
                    'id': f'task_{task.id}',
                    'type': 'task',
                    'name': task.title,
                    'start': task.start_date.isoformat(),
                    'end': task.due_date.isoformat(),
                    'progress': task.progress if hasattr(task, 'progress') else 0,
                    'dependencies': [dep.id for dep in task.dependencies.all()],
                    'assigned_to': task.assigned_to.get_full_name() if task.assigned_to else None
                })

        context.update({
            'timeline_data': timeline_data,
            'project_start': project.start_date.isoformat(),
            'project_end': project.target_end_date.isoformat(),
            'total_duration': (project.target_end_date - project.start_date).days
        })
        return context

@login_required
def project_timeline_data(request, project_id):
    """
    API endpoint for timeline data
    """
    try:
        project = get_object_or_404(Project, pk=project_id)
        if not (project.project_manager == request.user.employee_profile or
                request.user.employee_profile in project.team_members.all()):
            raise PermissionDenied

        phases = ProjectPhase.objects.filter(project=project).prefetch_related(
            'tasks',
            'tasks__assigned_to',
            'tasks__dependencies'
        )

        timeline_data = []
        for phase in phases:
            phase_data = {
                'id': f'phase_{phase.id}',
                'type': 'phase',
                'name': phase.name,
                'start': phase.start_date.isoformat(),
                'end': phase.end_date.isoformat(),
                'progress': phase.calculate_progress(),
                'tasks': []
            }

            for task in phase.tasks.all():
                task_data = {
                    'id': f'task_{task.id}',
                    'name': task.title,
                    'start': task.start_date.isoformat(),
                    'end': task.due_date.isoformat(),
                    'progress': task.calculate_progress(),
                    'dependencies': [f'task_{dep.id}' for dep in task.dependencies.all()],
                    'assigned_to': task.assigned_to.get_full_name() if task.assigned_to else None,
                    'status': task.status
                }
                phase_data['tasks'].append(task_data)

            timeline_data.append(phase_data)

        return JsonResponse({
            'status': 'success',
            'data': timeline_data
        })

    except Exception as e:
        logger.error(f"Error fetching timeline data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def update_task_dates(request, task_id):
    """
    Update task start and end dates
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        task = get_object_or_404(ProjectTask, pk=task_id)
        project = task.phase.project

        # Verify permissions
        if not (project.project_manager == request.user.employee_profile or
                task.assigned_to == request.user.employee_profile):
            raise PermissionDenied

        data = json.loads(request.body)
        new_start = datetime.fromisoformat(data.get('start_date'))
        new_end = datetime.fromisoformat(data.get('end_date'))

        # Validate dates
        if new_end <= new_start:
            return JsonResponse({
                'error': 'End date must be after start date'
            }, status=400)

        # Check for dependency conflicts
        for dep in task.dependencies.all():
            if dep.due_date > new_start:
                return JsonResponse({
                    'error': f'Dependency conflict with task: {dep.title}'
                }, status=400)

        task.start_date = new_start
        task.due_date = new_end
        task.save()

        return JsonResponse({
            'status': 'success',
            'task': {
                'id': task.id,
                'start_date': task.start_date.isoformat(),
                'due_date': task.due_date.isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Error updating task dates: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

class ProjectFinanceView(LoginRequiredMixin, DetailView):
    """
    Project financial overview and tracking
    """
    model = Project
    template_name = 'customer_projects/project_finance.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        # Calculate time-based costs
        time_entries = TimeEntry.objects.filter(
            task__phase__project=project
        ).select_related('employee', 'task')

        billable_time = time_entries.filter(is_billable=True).aggregate(
            total_hours=Sum('hours')
        )['total_hours'] or 0

        non_billable_time = time_entries.filter(is_billable=False).aggregate(
            total_hours=Sum('hours')
        )['total_hours'] or 0

        # Calculate costs by phase
        phase_costs = []
        for phase in project.phases.all():
            phase_time = time_entries.filter(task__phase=phase).aggregate(
                billable=Sum('hours', filter=Q(is_billable=True)),
                non_billable=Sum('hours', filter=Q(is_billable=False))
            )

            phase_costs.append({
                'phase': phase,
                'billable_hours': phase_time['billable'] or 0,
                'non_billable_hours': phase_time['non_billable'] or 0,
                'total_cost': (phase_time['billable'] or 0) * project.hourly_rate
            })

        context.update({
            'billable_time': billable_time,
            'non_billable_time': non_billable_time,
            'total_cost': billable_time * project.hourly_rate,
            'phase_costs': phase_costs,
            'budget_remaining': project.budget - (billable_time * project.hourly_rate),
            'budget_utilization': (billable_time * project.hourly_rate / project.budget * 100)
                if project.budget else 0
        })
        return context

@method_decorator(login_required, name='dispatch')
class RiskCreateView(LoginRequiredMixin, CreateView):
    """View to create a new project risk."""
    model = ProjectRisk
    form_class = ProjectRiskForm
    template_name = "customer_projects/risk_form.html"

    def dispatch(self, request, *args, **kwargs):
        """Ensure project exists before proceeding"""
        self.project = get_object_or_404(Project, pk=self.kwargs.get('project_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Add project to template context"""
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context

    def form_valid(self, form):
        """Set project and identified_by before saving"""
        form.instance.project = self.project
        form.instance.identified_by = self.request.user.employee_profile
        messages.success(self.request, "Risk created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect to the project detail page after success"""
        return reverse("customer_projects:project-detail", kwargs={"pk": self.project.id})


class TeamListView(ListView):
    model = ProjectTeamMember
    template_name = "customer_projects/team_list.html"
    context_object_name = "team_members"

    def get_queryset(self):
        """Retrieve team members for the specific project."""
        project = get_object_or_404(Project, id=self.kwargs['project_id'])
        return ProjectTeamMember.objects.filter(project=project)

    def get_context_data(self, **kwargs):
        """Pass project details to the template."""
        context = super().get_context_data(**kwargs)
        context['project'] = get_object_or_404(Project, id=self.kwargs['project_id'])
        return context


class RiskListView(ListView):
    """List all risks associated with a project"""
    model = ProjectRisk
    template_name = "customer_projects/risk_list.html"
    context_object_name = "risks"

    def get_queryset(self):
        project = get_object_or_404(Project, id=self.kwargs['project_id'])
        return ProjectRisk.objects.filter(project=project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = get_object_or_404(Project, id=self.kwargs['project_id'])
        return context


class ReportListView(ListView):
    """List all reports associated with a project"""
    model = ProjectReport
    template_name = "customer_projects/report_list.html"
    context_object_name = "reports"

    def get_queryset(self):
        project = get_object_or_404(Project, id=self.kwargs['project_id'])
        return ProjectReport.objects.filter(project=project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = get_object_or_404(Project, id=self.kwargs['project_id'])
        return context


class ReportCreateView(LoginRequiredMixin, CreateView):
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'customer_projects/report_form.html'

    def form_valid(self, form):
        form.instance.project_id = self.kwargs['project_id']
        form.instance.created_by = self.request.user.employee_profile
        messages.success(self.request, "Report created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('customer_projects:project-detail',
                      kwargs={'pk': self.kwargs['project_id']})

class ReportUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectReport
    form_class = ProjectReportForm
    template_name = 'customer_projects/report_form.html'

    def get_success_url(self):
        return reverse('customer_projects:project-detail',
                      kwargs={'pk': self.object.project.id})


class TeamMemberUpdateView(LoginRequiredMixin, UpdateView):
    model = ProjectTeamMember
    form_class = ProjectTeamMemberForm
    template_name = 'customer_projects/team_member_form.html'

    def get_success_url(self):
        return reverse('customer_projects:project-detail',
                      kwargs={'pk': self.object.project.id})


@login_required
def bulk_document_upload(request, project_id):
    project = get_object_or_404(Project, pk=project_id)

    if request.method == 'POST':
        form = BulkDocumentUploadForm(request.POST)
        files = request.FILES.getlist('files')

        if form.is_valid() and files:
            document_type = form.cleaned_data['document_type']
            description = form.cleaned_data['description']
            uploaded_count = 0
            error_files = []

            for file in files:
                try:
                    # Validate file size
                    if file.size > 52428800:  # 50MB
                        error_files.append(f"{file.name} (exceeds 50MB limit)")
                        continue

                    # Validate file extension
                    ext = file.name.lower()[-4:]
                    allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
                    if ext not in allowed_extensions:
                        error_files.append(f"{file.name} (unsupported file type)")
                        continue

                    # Create document
                    ProjectDocument.objects.create(
                        project=project,
                        title=file.name,
                        document_type=document_type,
                        file=file,
                        description=description,
                        version='1.0',
                        uploaded_by=request.user.employee_profile
                    )
                    uploaded_count += 1
                except Exception as e:
                    error_files.append(f"{file.name} ({str(e)})")
                    logger.error(f"Error uploading file {file.name}: {str(e)}")

            if uploaded_count > 0:
                messages.success(request, f"{uploaded_count} documents uploaded successfully.")

            if error_files:
                messages.error(request, f"Failed to upload: {', '.join(error_files)}")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'uploaded': uploaded_count,
                    'errors': error_files,
                    'redirect_url': reverse('customer_projects:project-detail', kwargs={'pk': project_id})
                })
            return redirect('customer_projects:project-detail', pk=project_id)

        else:
            messages.error(request, "Please select files to upload and ensure the form is valid.")
    else:
        form = BulkDocumentUploadForm()

    return render(request, 'customer_projects/bulk_document_upload.html', {
        'form': form,
        'project': project
    })


class DocumentFormView(LoginRequiredMixin, CreateView):
    """View for uploading project documents"""
    model = ProjectDocument
    form_class = ProjectDocumentForm
    template_name = "customer_projects/document_form.html"

    def form_valid(self, form):
        """Set the project ID before saving"""
        project_id = self.kwargs.get("project_id")
        project = get_object_or_404(Project, id=project_id)
        form.instance.project = project
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect to the document list after successful upload"""
        return reverse("customer_projects:document-list", kwargs={"project_id": self.kwargs.get("project_id")})


# ✅ **List Phases for a Project**
class PhaseListView(LoginRequiredMixin, ListView):
    """View all phases within a project"""
    model = ProjectPhase
    template_name = "customer_projects/phase_list.html"
    context_object_name = "phases"

    def get_queryset(self):
        project = get_object_or_404(Project, id=self.kwargs['project_id'])
        return project.phases.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = get_object_or_404(Project, id=self.kwargs["project_id"])
        return context

class PhaseCreateView(LoginRequiredMixin, CreateView):
    """Creates a new project phase"""
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'customer_projects/phase_form.html'

    def dispatch(self, request, *args, **kwargs):
        """Ensure project exists before proceeding"""
        self.project = get_object_or_404(Project, pk=self.kwargs.get('project_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Pass project to context"""
        context = super().get_context_data(**kwargs)
        context['project'] = self.project  # Ensure project is available in template
        return context

    def form_valid(self, form):
        """Ensures phase is linked to the correct project before saving"""
        form.instance.project = self.project
        form.save()
        messages.success(self.request, "Phase added successfully.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        """Redirect back to project update page after adding a phase"""
        return reverse('customer_projects:project-update', kwargs={'pk': self.project.pk})


class PhaseUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an existing phase"""
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = "customer_projects/phase_form.html"

    def dispatch(self, request, *args, **kwargs):
        """Get phase and project before proceeding"""
        self.object = self.get_object()
        self.project = self.object.project
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Add project to template context"""
        context = super().get_context_data(**kwargs)
        context['project'] = self.project
        return context

    def form_valid(self, form):
        try:
            # Save old status for comparison
            old_status = self.object.status
            response = super().form_valid(form)

            # If status changed, recalculate progress
            if old_status != form.instance.status:
                # Calculate and update phase progress
                self.calculate_phase_progress()
                # Update project progress after phase update
                self.calculate_project_progress()

            messages.success(self.request, "Phase updated successfully.")
            return response
        except Exception as e:
            logger.error(f"Error updating phase: {str(e)}")
            messages.error(self.request, f"Error updating phase: {str(e)}")
            return self.form_invalid(form)

    def calculate_phase_progress(self):
        """Calculate and update phase progress based on tasks with weighted status"""
        try:
            phase_tasks = self.object.tasks.all()
            total_tasks = phase_tasks.count()

            if total_tasks > 0:
                # Count tasks in different states
                completed_tasks = phase_tasks.filter(status='done').count()
                in_progress_tasks = phase_tasks.filter(status='in_progress').count()
                in_review_tasks = phase_tasks.filter(status='in_review').count()

                # Calculate weighted progress
                progress = (
                    (completed_tasks * 100) +  # Done tasks count as 100%
                    (in_review_tasks * 75) +   # In Review tasks count as 75%
                    (in_progress_tasks * 50)    # In Progress tasks count as 50%
                ) / total_tasks
            else:
                # If no tasks, base progress on phase status
                status_progress = {
                    'planning': 0,
                    'in_progress': 50,
                    'completed': 100,
                    'on_hold': 25
                }
                progress = status_progress.get(self.object.status, 0)

            self.object.progress = round(progress)
            self.object.save(update_fields=['progress'])
            return self.object.progress

        except Exception as e:
            logger.error(f"Error calculating phase progress: {str(e)}")
            return 0

    def calculate_project_progress(self):
        """Calculate and update project progress based on phases"""
        try:
            phases = self.project.phases.all()
            if not phases.exists():
                return 0

            # Get sum of weighted phase progress
            phase_count = phases.count()
            total_progress = sum(phase.progress for phase in phases)
            project_progress = round(total_progress / phase_count)

            # Update project progress
            self.project.progress = project_progress
            self.project.save(update_fields=['progress'])

            return project_progress

        except Exception as e:
            logger.error(f"Error calculating project progress: {str(e)}")
            return 0

    def get_success_url(self):
        """Return to phase list with correct project_id"""
        return reverse("customer_projects:phase-list", kwargs={"project_id": self.project.id})

# ✅ **Delete Phase**
class PhaseDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a phase"""
    model = ProjectPhase
    template_name = "customer_projects/phase_confirm_delete.html"

    def get_success_url(self):
        return reverse("customer_projects:phase-list", kwargs={"project_id": self.object.project.id})

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Phase deleted successfully.")
        return super().delete(request, *args, **kwargs)


class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = ProjectTask
    template_name = 'customer_projects/task_confirm_delete.html'

    def get_success_url(self):
        return reverse('customer_projects:task-list', kwargs={'phase_id': self.object.phase.id})

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Task deleted successfully.")
        return super().delete(request, *args, **kwargs)


@login_required
@require_http_methods(["POST"])
def update_phase_status(request, pk):
    try:
        phase = get_object_or_404(ProjectPhase, pk=pk)

        new_status = request.POST.get('status')

        if not new_status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        if new_status not in dict(ProjectPhase.STATUS_CHOICES):
            return JsonResponse({
                'success': False,
                'error': f'Invalid status. Choices are: {", ".join(dict(ProjectPhase.STATUS_CHOICES).keys())}'
            }, status=400)

        old_status = phase.status
        phase.status = new_status
        phase.save()

        progress = phase.calculate_progress()

        return JsonResponse({
            'success': True,
            'status': phase.get_status_display(),
            'progress': progress
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class ProjectTaskDetailView(LoginRequiredMixin, DetailView):
    model = ProjectTask
    template_name = 'customer_projects/project_task_detail.html'
    context_object_name = 'task'

    def get_object(self, queryset=None):
        project_id = self.kwargs.get('project_id')
        phase_id = self.kwargs.get('phase_id')
        task_id = self.kwargs.get('pk')

        return get_object_or_404(
            ProjectTask.objects.select_related(
                'phase',
                'phase__project',
                'assigned_to',
                'assigned_to__user'
            ),
            id=task_id,
            phase_id=phase_id,
            phase__project_id=project_id
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()

        context.update({
            'project': task.phase.project,
            'phase': task.phase,
            'time_entries': TimeEntry.objects.filter(task=task).select_related('employee'),
            'comments': ProjectComment.objects.filter(
                content_type__model='projecttask',
                object_id=task.id
            ).select_related('author', 'author__user').order_by('-created_at')
        })
        return context

class ProjectTaskListView(LoginRequiredMixin, ListView):
    model = ProjectTask
    template_name = 'customer_projects/project_task_list.html'
    context_object_name = 'tasks'
    paginate_by = 10

    def get_queryset(self):
        """
        Filter tasks based on the specific project phase
        """
        project_id = self.kwargs.get('project_id')
        phase_id = self.kwargs.get('phase_id')

        # Create the base queryset
        queryset = ProjectTask.objects.select_related(
            'phase',
            'phase__project',
            'assigned_to',
            'assigned_to__user'
        ).filter(
            phase_id=phase_id,
            phase__project_id=project_id
        )

        # Filter based on user permissions
        employee = self.request.user.employee_profile
        queryset = queryset.filter(
            Q(phase__project__project_manager=employee) |
            Q(phase__project__team_members=employee) |
            Q(assigned_to=employee)
        ).distinct()

        # Apply search and filters
        search_query = self.request.GET.get('search')
        status = self.request.GET.get('status')
        priority = self.request.GET.get('priority')

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if status:
            queryset = queryset.filter(status=status)

        if priority:
            queryset = queryset.filter(priority=priority)

        return queryset.order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_id = self.kwargs.get('project_id')
        phase_id = self.kwargs.get('phase_id')

        context['project'] = get_object_or_404(Project, id=project_id)
        context['phase'] = get_object_or_404(ProjectPhase, id=phase_id)

        # Calculate summary statistics using the unsliced queryset
        queryset = self.get_queryset()
        context['summary'] = {
            'total_tasks': queryset.count(),
            'completed_tasks': queryset.filter(status='completed').count(),
            'in_progress_tasks': queryset.filter(status='in_progress').count(),
            'pending_tasks': queryset.filter(status='pending').count(),
        }

        # Add filter choices
        context['status_choices'] = ProjectTask.STATUS_CHOICES
        context['priority_choices'] = ProjectTask.PRIORITY_CHOICES

        # Check permissions
        employee = self.request.user.employee_profile
        context['can_create_task'] = (
            context['project'].project_manager == employee or
            employee in context['project'].team_members.all()
        )

        return context


class IntegratedProjectCreateView(LoginRequiredMixin, View):
    """View for creating a project with phases and tasks in a single form"""
    template_name = 'customer_projects/integrated_project_form.html'

    def get(self, request, *args, **kwargs):
        """Handle GET request - display the empty form"""
        # Get customer ID if provided in query parameters
        customer_id = request.GET.get('customer')

        # Create initial form data with customer pre-selected if provided
        initial_data = {}
        if customer_id:
            initial_data['customer'] = customer_id

        project_form = ProjectForm(user=request.user, initial=initial_data)
        phase_forms = [ProjectPhaseForm(prefix=f'phase-0')]
        task_forms = [[ProjectTaskForm(prefix=f'phase-0-task-0')]]

        context = {
            'project_form': project_form,
            'phase_forms': phase_forms,
            'task_forms': task_forms,
            'num_phases': 1,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle POST request - process the form data"""
        print("POST data keys:", list(request.POST.keys()))  # Debug what keys are coming in

        project_form = ProjectForm(request.POST, user=request.user)

        if not project_form.is_valid():
            # If project form is invalid, re-render with errors
            messages.error(request, "Please correct the errors in the project form.")
            return render(request, self.template_name, {'project_form': project_form})

        # Save the project directly
        try:
            with transaction.atomic():
                # Save the project
                project = project_form.save(commit=False)
                project.created_by = request.user.employee_profile
                project.save()

                # Add project manager to team members
                if project.project_manager:
                    ProjectTeamMember.objects.create(
                        project=project,
                        employee=project.project_manager,
                        role='lead'
                    )

                # Process phases and tasks directly from POST data
                # Get the number of phases from the form
                num_phases = int(request.POST.get('num_phases', 1))

                # Save phases and tasks - direct approach
                for i in range(num_phases):
                    prefix = f'phase-{i}'

                    # Check if we have phase data
                    phase_name = request.POST.get(f'{prefix}-name')
                    if phase_name:
                        # Create the phase
                        phase = ProjectPhase(
                            project=project,
                            name=phase_name,
                            status=request.POST.get(f'{prefix}-status', 'planning'),
                            description=request.POST.get(f'{prefix}-description', '')
                        )

                        # Handle date fields
                        start_date = request.POST.get(f'{prefix}-start_date')
                        end_date = request.POST.get(f'{prefix}-end_date')

                        if start_date:
                            phase.start_date = start_date
                        if end_date:
                            phase.end_date = end_date

                        phase.save()

                        # Save tasks for this phase
                        num_tasks = int(request.POST.get(f'{prefix}-num_tasks', 0))
                        for j in range(num_tasks):
                            task_prefix = f'{prefix}-task-{j}'

                            # Check if any keys exist for this task
                            task_keys = [k for k in request.POST.keys() if k.startswith(task_prefix)]

                            if task_keys:
                                task_title = request.POST.get(f'{task_prefix}-title')

                                if task_title:
                                    # Create the task
                                    task = ProjectTask(
                                        phase=phase,
                                        title=task_title,
                                        status=request.POST.get(f'{task_prefix}-status', 'todo'),
                                        priority=request.POST.get(f'{task_prefix}-priority', 'medium'),
                                        description=request.POST.get(f'{task_prefix}-description', '')
                                    )

                                    # Handle date fields
                                    task_start_date = request.POST.get(f'{task_prefix}-start_date')
                                    task_due_date = request.POST.get(f'{task_prefix}-due_date')

                                    if task_start_date:
                                        task.start_date = task_start_date
                                    if task_due_date:
                                        task.due_date = task_due_date

                                    # Handle estimated hours (if present)
                                    estimated_hours = request.POST.get(f'{task_prefix}-estimated_hours')
                                    if estimated_hours:
                                        try:
                                            task.estimated_hours = float(estimated_hours)
                                        except (ValueError, TypeError):
                                            pass

                                    # Handle assigned_to field (it's a foreign key)
                                    assigned_to_id = request.POST.get(f'{task_prefix}-assigned_to')
                                    if assigned_to_id:
                                        try:
                                            employee = Employee.objects.get(id=assigned_to_id)
                                            task.assigned_to = employee
                                        except Employee.DoesNotExist:
                                            pass

                                    task.save()

                messages.success(request, "Project created successfully with phases and tasks.")
                return redirect('customer_projects:project-detail', pk=project.pk)

        except Exception as e:
            import traceback
            print(f"Error creating project: {str(e)}")
            print(traceback.format_exc())
            messages.error(request, f"Error creating project: {str(e)}")

            # Recreate the forms for display
            phase_forms = []
            task_forms = []

            for i in range(num_phases):
                prefix = f'phase-{i}'
                phase_form = ProjectPhaseForm(request.POST, prefix=prefix)
                phase_forms.append(phase_form)

                # Get number of tasks for this phase
                num_tasks = int(request.POST.get(f'{prefix}-num_tasks', 0))
                phase_task_forms = []

                for j in range(num_tasks):
                    task_prefix = f'{prefix}-task-{j}'
                    task_form = ProjectTaskForm(request.POST, prefix=task_prefix)
                    phase_task_forms.append(task_form)

                task_forms.append(phase_task_forms)

            context = {
                'project_form': project_form,
                'phase_forms': phase_forms,
                'task_forms': task_forms,
                'num_phases': num_phases
            }
            return render(request, self.template_name, context)
