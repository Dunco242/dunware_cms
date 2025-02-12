from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from .models import Employee
import logging

logger = logging.getLogger(__name__)

class EmployeeRequiredMixin:
    """Mixin to handle employee profile requirements"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            self.employee = request.user.employee_profile
            if not self.employee.is_active:
                messages.warning(request, 'Your employee profile is inactive. Please contact an administrator.')
                return redirect('logout')
        except Employee.DoesNotExist:
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
