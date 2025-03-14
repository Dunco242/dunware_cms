from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.apps import apps
import logging

logger = logging.getLogger(__name__)

class EmployeeRequiredMixin:
    """Mixin to handle employee profile requirements"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Use apps.get_model to avoid circular import
            Employee = apps.get_model('core', 'Employee')

            try:
                # Get the employee via the related name
                self.employee = request.user.employee_profile

                if not self.employee.is_active:
                    messages.warning(request, 'Your employee profile is inactive. Please contact an administrator.')
                    return redirect('logout')
            except AttributeError: #Catch the attribute error first
                try:
                    # Attempt to create employee profile
                    self.employee = Employee.objects.create(
                        user=request.user,
                        hire_date=timezone.now().date(),
                        employee_id=f"EMP{request.user.id:04d}",
                        department="General",
                        position="Unassigned",
                        phone="000-000-0000",
                        is_active=True
                    )
                    logger.info(f"Created missing employee profile for user {request.user.username}")
                    messages.success(request, 'Employee profile has been created.')
                except Exception as e:
                    logger.error(f"Failed to create employee profile for user {request.user.username}: {str(e)}")
                    messages.error(request, 'Unable to create employee profile. Please contact an administrator.')
                    return redirect('logout')

        except Exception as e:
            logger.error(f"Error checking employee profile for user {request.user.username}: {str(e)}")
            messages.error(request, 'Error accessing employee profile. Please contact an administrator.')
            return redirect('logout')

        return super().dispatch(request, *args, **kwargs)


class ProjectDatesMixin:
    """Mixin to handle project-related dates"""

    def get_all_project_dates(self):
        """Get all project-related dates for this object"""
        try:
            # Lazy load models to avoid circular imports
            ProjectPhase = apps.get_model('customer_projects', 'ProjectPhase')
            ProjectTask = apps.get_model('customer_projects', 'ProjectTask')
            Project = apps.get_model('customer_projects', 'Project')

            return {
                'projects': self.projects.all() if hasattr(self, 'projects') else Project.objects.none(),
                'phases': ProjectPhase.objects.filter(project__customer=self),
                'tasks': ProjectTask.objects.filter(phase__project__customer=self)
            }
        except Exception as e:
            logger.error(f"Error getting project dates: {str(e)}")
            return {
                'projects': [],
                'phases': [],
                'tasks': []
            }
