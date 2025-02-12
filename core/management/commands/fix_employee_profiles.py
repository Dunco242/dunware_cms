from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.timezone import now
from core.models import Employee

class Command(BaseCommand):
    help = 'Fix employee profiles and user associations'

    def handle(self, *args, **options):
        self.stdout.write("Starting employee profile fix...")

        # Get all users
        users = User.objects.all()
        self.stdout.write(f"Found {users.count()} total users")

        # Fix existing profiles and create missing ones
        for user in users:
            try:
                # Check if user has an employee profile
                try:
                    employee = Employee.objects.get(user=user)
                    self.stdout.write(
                        self.style.SUCCESS(f"User {user.username} already has correct profile")
                    )
                except Employee.DoesNotExist:
                    # Try to find an unassigned employee profile that might match
                    unassigned_employees = Employee.objects.filter(
                        user__isnull=True,
                        employee_id__contains=f"{user.id:04d}"
                    )

                    if unassigned_employees.exists():
                        # Found a matching unassigned profile
                        employee = unassigned_employees.first()
                        employee.user = user
                        employee.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Associated existing employee profile with user {user.username}"
                            )
                        )
                    else:
                        # Create new profile
                        Employee.objects.create(
                            user=user,
                            hire_date=now().date(),
                            employee_id=f"EMP{user.id:04d}",
                            department="General",
                            position="Unassigned",
                            phone="000-000-0000",
                            is_active=True
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Created new employee profile for user {user.username}"
                            )
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error processing user {user.username}: {str(e)}"
                    )
                )

        # Check for orphaned employee profiles
        orphaned_employees = Employee.objects.filter(user__isnull=True)
        if orphaned_employees.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Found {orphaned_employees.count()} orphaned employee profiles"
                )
            )
            for emp in orphaned_employees:
                self.stdout.write(
                    f"Orphaned profile: ID {emp.employee_id}"
                )

        self.stdout.write(self.style.SUCCESS("Employee profile fix completed"))
