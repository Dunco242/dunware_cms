from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Employee
from django.utils.timezone import now

@receiver(post_save, sender=User)
def create_employee_profile(sender, instance, created, **kwargs):
    if created:
        Employee.objects.create(
            user=instance,
            hire_date=now().date(),  # ✅ Automatically set hire date
            employee_id=f"EMP{instance.id:04d}",  # ✅ Generate a unique Employee ID
            department="General",  # ✅ Set a default department
            position="Unassigned",  # ✅ Set a default position
            phone="000-000-0000",  # ✅ Set a default phone number
            is_active=True
        )

@receiver(post_save, sender=User)
def save_employee_profile(sender, instance, **kwargs):
    instance.employee.save()
