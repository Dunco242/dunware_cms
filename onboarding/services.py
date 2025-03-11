import os
import csv
import json
import logging
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Avg, Sum, F, Q, Case, When, Value, IntegerField
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from core.models import Customer, Employee
from .models import (
    OnboardingPlan, OnboardingStep, CustomerOnboarding,
    OnboardingStepCompletion, DataImportJob, OnboardingFeedback,
    OnboardingChecklistItem, ChecklistItemCompletion, OnboardingNotification
)

# Configure logging
logger = logging.getLogger(__name__)


class OnboardingService:
    """
    Service class for onboarding-related operations
    """

    @staticmethod
    def setup_step_completions(onboarding):
        """
        Set up OnboardingStepCompletion records for all steps in the plan
        """
        steps = onboarding.plan.steps.all()

        # Create completion records for all steps if they don't exist
        for step in steps:
            OnboardingStepCompletion.objects.get_or_create(
                customer_onboarding=onboarding,
                step=step,
                defaults={'is_completed': False}
            )

        # Set current step if not already set
        if not onboarding.current_step:
            first_step = steps.order_by('order').first()
            if first_step:
                onboarding.current_step = first_step
                onboarding.save(update_fields=['current_step'])

        return True

    @staticmethod
    def get_next_step(step_completion):
        """
        Get the next step after the given completion
        """
        current_step = step_completion.step

        # Get all steps in this plan ordered by order
        next_step = OnboardingStep.objects.filter(
            plan=current_step.plan,
            order__gt=current_step.order
        ).order_by('order').first()

        if next_step:
            next_completion, created = OnboardingStepCompletion.objects.get_or_create(
                customer_onboarding=step_completion.customer_onboarding,
                step=next_step,
                defaults={'is_completed': False}
            )
            return next_completion

        return None

    @staticmethod
    def get_previous_step(step_completion):
        """
        Get the previous step before the given completion
        """
        current_step = step_completion.step

        # Get previous step in this plan
        prev_step = OnboardingStep.objects.filter(
            plan=current_step.plan,
            order__lt=current_step.order
        ).order_by('-order').first()

        if prev_step:
            prev_completion, created = OnboardingStepCompletion.objects.get_or_create(
                customer_onboarding=step_completion.customer_onboarding,
                step=prev_step,
                defaults={'is_completed': False}
            )
            return prev_completion

        return None

    @staticmethod
    def are_all_required_items_completed(step_completion):
        """
        Check if all required checklist items are completed for a step
        """
        required_items = OnboardingChecklistItem.objects.filter(
            step=step_completion.step,
            is_required=True
        )

        if not required_items.exists():
            return True

        # Check each required item
        for item in required_items:
            try:
                item_completion = ChecklistItemCompletion.objects.get(
                    onboarding_step_completion=step_completion,
                    checklist_item=item
                )

                if not item_completion.is_completed:
                    return False
            except ChecklistItemCompletion.DoesNotExist:
                return False

        return True

    @staticmethod
    def get_onboardings_needing_attention():
        """
        Get onboardings that need attention (stuck, inactive, etc.)
        """
        # Get onboardings with no activity in the last 5 days
        inactive_deadline = timezone.now() - timedelta(days=5)

        # Get onboardings that are in progress but haven't had activity
        stuck_onboardings = CustomerOnboarding.objects.filter(
            status='in_progress',
            last_activity_date__lt=inactive_deadline
        ).select_related('customer', 'assigned_to')

        # Get onboardings that have been in "not started" state for too long
        not_started_deadline = timezone.now() - timedelta(days=7)

        delayed_onboardings = CustomerOnboarding.objects.filter(
            status='not_started',
            created_at__lt=not_started_deadline
        ).select_related('customer', 'assigned_to')

        # Combine both lists
        result = {
            'stuck': stuck_onboardings,
            'delayed': delayed_onboardings
        }

        return result

    @staticmethod
    def get_satisfaction_metrics():
        """
        Calculate satisfaction metrics from feedback
        """
        # Get all feedback with ratings
        feedback = OnboardingFeedback.objects.all()

        # Get average ratings
        metrics = {}

        if feedback.exists():
            metrics['overall_avg'] = feedback.aggregate(avg=Avg('overall_rating'))['avg']
            metrics['ease_of_use_avg'] = feedback.aggregate(avg=Avg('ease_of_use_rating'))['avg']

            # Filter out null support ratings
            support_feedback = feedback.exclude(support_rating__isnull=True)
            metrics['support_avg'] = support_feedback.aggregate(avg=Avg('support_rating'))['avg'] if support_feedback.exists() else None

            # Get rating distribution
            metrics['distribution'] = {
                1: feedback.filter(overall_rating=1).count(),
                2: feedback.filter(overall_rating=2).count(),
                3: feedback.filter(overall_rating=3).count(),
                4: feedback.filter(overall_rating=4).count(),
                5: feedback.filter(overall_rating=5).count()
            }
        else:
            metrics['overall_avg'] = None
            metrics['ease_of_use_avg'] = None
            metrics['support_avg'] = None
            metrics['distribution'] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        return metrics


class DataImportService:
    """
    Service class for data import operations
    """

    # Define template configurations for each import type
    IMPORT_TEMPLATES = {
        'customers': {
            'columns': ['Company Name', 'Contact Name', 'Email', 'Phone', 'Address', 'Industry', 'Notes'],
            'example_data': [
                ['Acme Inc.', 'John Smith', 'john@acme.com', '555-123-4567', '123 Main St, City', 'Technology', 'New customer'],
                ['XYZ Corp', 'Jane Doe', 'jane@xyz.com', '555-987-6543', '456 Oak Ave, Town', 'Healthcare', '']
            ]
        },
        'leads': {
            'columns': ['Company', 'Contact Name', 'Email', 'Phone', 'Source', 'Status', 'Notes'],
            'example_data': [
                ['New Prospect', 'Alice Brown', 'alice@example.com', '555-111-2222', 'Website', 'New', 'Interested in Product A'],
                ['Potential Client', 'Bob Green', 'bob@example.com', '555-333-4444', 'Referral', 'Contacted', 'Follow up next week']
            ]
        },
        'contacts': {
            'columns': ['First Name', 'Last Name', 'Email', 'Phone', 'Company', 'Job Title', 'Notes'],
            'example_data': [
                ['Michael', 'Johnson', 'michael@company.com', '555-555-5555', 'Company LLC', 'Marketing Director', ''],
                ['Sarah', 'Williams', 'sarah@business.com', '555-666-7777', 'Business Inc', 'CEO', 'Key decision maker']
            ]
        },
        'products': {
            'columns': ['Name', 'SKU', 'Description', 'Price', 'Category', 'Active'],
            'example_data': [
                ['Basic Plan', 'BP-001', 'Basic subscription plan', '9.99', 'Subscription', 'Yes'],
                ['Premium Service', 'PS-002', 'Premium service package', '99.99', 'Service', 'Yes']
            ]
        }
    }

    @staticmethod
    def get_import_template(import_type):
        """
        Generate a template file for data import
        """
        if import_type not in DataImportService.IMPORT_TEMPLATES:
            raise ValueError(f"Unknown import type: {import_type}")

        template_config = DataImportService.IMPORT_TEMPLATES[import_type]

        # Create Excel file in memory
        output = BytesIO()

        # Create DataFrame from template configuration
        df = pd.DataFrame(template_config['example_data'], columns=template_config['columns'])

        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Template', index=False)

            # Get the worksheet to make formatting adjustments
            worksheet = writer.sheets['Template']

            # Make columns wider for better readability
            for i, column in enumerate(template_config['columns']):
                worksheet.column_dimensions[chr(65 + i)].width = 20

        # Get the bytes content and create a Django ContentFile
        output.seek(0)
        return ContentFile(output.getvalue(), name=f"{import_type}_template.xlsx")

    @staticmethod
    def process_import_job(import_job):
        """
        Process a data import job
        """
        try:
            # Update job status
            import_job.status = 'processing'
            import_job.started_at = timezone.now()
            import_job.save(update_fields=['status', 'started_at'])

            # Read the file into a DataFrame
            file_ext = os.path.splitext(import_job.source_file.name)[1].lower()

            if file_ext == '.csv':
                df = pd.read_csv(import_job.source_file)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(import_job.source_file)
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")

            # Update record count
            import_job.records_total = len(df)
            import_job.save(update_fields=['records_total'])

            # Process based on import type
            if import_job.import_type == 'customers':
                records_processed, records_succeeded, records_failed = DataImportService._import_customers(
                    df, import_job.customer_onboarding.customer
                )
            elif import_job.import_type == 'leads':
                records_processed, records_succeeded, records_failed = DataImportService._import_leads(
                    df, import_job.customer_onboarding.customer
                )
            elif import_job.import_type == 'contacts':
                records_processed, records_succeeded, records_failed = DataImportService._import_contacts(
                    df, import_job.customer_onboarding.customer
                )
            elif import_job.import_type == 'products':
                records_processed, records_succeeded, records_failed = DataImportService._import_products(
                    df, import_job.customer_onboarding.customer
                )
            else:
                raise ValueError(f"Unsupported import type: {import_job.import_type}")

            # Update job stats
            import_job.records_processed = records_processed
            import_job.records_succeeded = records_succeeded
            import_job.records_failed = records_failed
            import_job.status = 'completed'
            import_job.completed_at = timezone.now()
            import_job.save(update_fields=[
                'records_processed', 'records_succeeded', 'records_failed',
                'status', 'completed_at'
            ])

            # Create a notification about the completed import
            from .models import OnboardingNotification
            OnboardingNotification.objects.create(
                customer_onboarding=import_job.customer_onboarding,
                notification_type='completion',
                title=f"{import_job.get_import_type_display()} Import Completed",
                message=f"Import from {import_job.source_name} completed with {records_succeeded} records imported successfully.",
                related_step=import_job.related_step,
                recipient=import_job.customer_onboarding.assigned_to.user if import_job.customer_onboarding.assigned_to else None
            )

            return True

        except Exception as e:
            logger.error(f"Error processing import job {import_job.id}: {str(e)}")
            import_job.status = 'failed'
            import_job.error_details = str(e)
            import_job.completed_at = timezone.now()
            import_job.save(update_fields=['status', 'error_details', 'completed_at'])
            return False

    @staticmethod
    def _import_customers(df, customer):
        """
        Import customers from DataFrame
        """
        # This would integrate with your actual customer model
        # For demonstration, we'll just count
        records_processed = 0
        records_succeeded = 0
        records_failed = 0

        # Example implementation
        for index, row in df.iterrows():
            try:
                records_processed += 1

                # In a real implementation, you would create Customer objects
                # For example:
                # Customer.objects.create(
                #     name=row['Company Name'],
                #     contact_name=row['Contact Name'],
                #     email=row['Email'],
                #     phone=row['Phone'],
                #     address=row['Address'],
                #     industry=row['Industry'],
                #     notes=row['Notes'],
                #     owner=customer  # The customer who owns this record
                # )

                records_succeeded += 1
            except Exception as e:
                logger.error(f"Error importing customer at row {index}: {str(e)}")
                records_failed += 1
            return records_processed, records_succeeded, records_failed

    @staticmethod
    def _import_leads(df, customer):
        """
        Import leads from DataFrame
        """
        # Similar structure to _import_customers
        records_processed = 0
        records_succeeded = 0
        records_failed = 0

        for index, row in df.iterrows():
            try:
                records_processed += 1

                # In a real implementation, you would create Lead objects
                # For example:
                # Lead.objects.create(
                #     company=row['Company'],
                #     contact_name=row['Contact Name'],
                #     email=row['Email'],
                #     phone=row['Phone'],
                #     source=row['Source'],
                #     status=row['Status'],
                #     notes=row['Notes'],
                #     owner=customer
                # )

                records_succeeded += 1
            except Exception as e:
                logger.error(f"Error importing lead at row {index}: {str(e)}")
                records_failed += 1

        return records_processed, records_succeeded, records_failed

    @staticmethod
    def _import_contacts(df, customer):
        """
        Import contacts from DataFrame
        """
        records_processed = 0
        records_succeeded = 0
        records_failed = 0

        for index, row in df.iterrows():
            try:
                records_processed += 1

                # In a real implementation, you would create Contact objects
                # For example:
                # Contact.objects.create(
                #     first_name=row['First Name'],
                #     last_name=row['Last Name'],
                #     email=row['Email'],
                #     phone=row['Phone'],
                #     company=row['Company'],
                #     job_title=row['Job Title'],
                #     notes=row['Notes'],
                #     customer=customer
                # )

                records_succeeded += 1
            except Exception as e:
                logger.error(f"Error importing contact at row {index}: {str(e)}")
                records_failed += 1

        return records_processed, records_succeeded, records_failed

    @staticmethod
    def _import_products(df, customer):
        """
        Import products from DataFrame
        """
        records_processed = 0
        records_succeeded = 0
        records_failed = 0

        for index, row in df.iterrows():
            try:
                records_processed += 1

                # In a real implementation, you would create Product objects
                # For example:
                # Product.objects.create(
                #     name=row['Name'],
                #     sku=row['SKU'],
                #     description=row['Description'],
                #     price=Decimal(row['Price']),
                #     category=row['Category'],
                #     is_active=row['Active'].lower() in ['yes', 'true', '1', 'y'],
                #     customer=customer
                # )

                records_succeeded += 1
            except Exception as e:
                logger.error(f"Error importing product at row {index}: {str(e)}")
                records_failed += 1

        return records_processed, records_succeeded, records_failed


class NotificationService:
    """
    Service class for onboarding-related notifications
    """

    @staticmethod
    def send_onboarding_created_notifications(onboarding):
        """
        Send notifications when a new onboarding is created
        """
        # Create notification for the assigned employee
        if onboarding.assigned_to:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='welcome',
                title=f"New Onboarding Assigned: {onboarding.customer.company_name}",
                message=f"You have been assigned to handle the onboarding process for {onboarding.customer.company_name}.",
                recipient=onboarding.assigned_to.user
            )

            # Send email notification
            notification.send_email()

        # Create notification for the customer if they have a user account
        if hasattr(onboarding.customer, 'user') and onboarding.customer.user:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='welcome',
                title="Welcome to DunWare CRM!",
                message="Your onboarding process has been set up. Let's get started with your new CRM!",
                recipient=onboarding.customer.user
            )

            # Send email notification
            notification.send_email()

    @staticmethod
    def send_step_completion_notification(step_completion):
        """
        Send notifications when a step is completed by an employee
        """
        onboarding = step_completion.customer_onboarding
        step = step_completion.step

        # Notify the customer if they have a user account
        if hasattr(onboarding.customer, 'user') and onboarding.customer.user:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='completion',
                title=f"Onboarding Step Completed: {step.name}",
                message=f"The '{step.name}' step of your onboarding has been completed.",
                related_step=step,
                recipient=onboarding.customer.user
            )

            # Send email notification if enabled
            if onboarding.send_reminders:
                notification.send_email()

        # If this was the last step, send completion notification
        if not onboarding.get_next_step():
            # Check if all steps are completed
            all_completed = True
            for step_check in onboarding.step_completions.all():
                if not step_check.is_completed:
                    all_completed = False
                    break

            if all_completed:
                # Update onboarding status
                onboarding.status = 'completed'
                onboarding.completed_date = timezone.now()
                onboarding.progress_percentage = 100
                onboarding.save(update_fields=['status', 'completed_date', 'progress_percentage'])

                # Send completion notification
                NotificationService.send_onboarding_completion_notifications(onboarding)

    @staticmethod
    def send_customer_step_completion_notification(step_completion):
        """
        Send notifications when a step is completed by a customer
        """
        onboarding = step_completion.customer_onboarding
        step = step_completion.step

        # Notify the assigned employee
        if onboarding.assigned_to:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='completion',
                title=f"Customer Completed Step: {step.name}",
                message=f"{onboarding.customer.company_name} has completed the '{step.name}' step of their onboarding.",
                related_step=step,
                recipient=onboarding.assigned_to.user
            )

            # Send email notification
            notification.send_email()

    @staticmethod
    def send_onboarding_completion_notifications(onboarding):
        """
        Send notifications when an onboarding is completed
        """
        # Notify the assigned employee
        if onboarding.assigned_to:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='completion',
                title=f"Onboarding Completed: {onboarding.customer.company_name}",
                message=f"The onboarding process for {onboarding.customer.company_name} has been completed successfully.",
                recipient=onboarding.assigned_to.user
            )

            # Send email notification
            notification.send_email()

        # Notify the customer if they have a user account
        if hasattr(onboarding.customer, 'user') and onboarding.customer.user:
            notification = OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='completion',
                title="Onboarding Completed!",
                message="Congratulations! Your onboarding process has been completed successfully. Welcome to DunWare CRM!",
                recipient=onboarding.customer.user
            )

            # Send email notification if enabled
            if onboarding.send_reminders:
                notification.send_email()

        # Optionally notify managers or administrators
        # This could be expanded based on your organizational structure

    @staticmethod
    def send_reminder_notifications():
        """
        Send reminder notifications for in-progress onboardings that need attention
        This would typically be called by a scheduled task or cron job
        """
        # Find onboardings that haven't had activity in 3+ days but are still in progress
        reminder_threshold = timezone.now() - timedelta(days=3)

        onboardings_needing_reminders = CustomerOnboarding.objects.filter(
            status='in_progress',
            last_activity_date__lt=reminder_threshold,
            send_reminders=True
        ).select_related('customer', 'assigned_to', 'current_step')

        for onboarding in onboardings_needing_reminders:
            if onboarding.assigned_to:
                # Create a reminder notification
                notification = OnboardingNotification.objects.create(
                    customer_onboarding=onboarding,
                    notification_type='reminder',
                    title=f"Onboarding Reminder: {onboarding.customer.company_name}",
                    message=f"The onboarding process for {onboarding.customer.company_name} has been inactive for 3+ days.",
                    related_step=onboarding.current_step,
                    recipient=onboarding.assigned_to.user
                )

                # Send email notification
                notification.send_email()

            # Update next reminder date to avoid sending too many reminders
            onboarding.next_reminder_date = timezone.now().date() + timedelta(days=2)
            onboarding.save(update_fields=['next_reminder_date'])


class OnboardingAnalyticsService:
    """
    Service class for onboarding analytics and metrics
    """

    @staticmethod
    def get_analytics(employee=None):
        """
        Get onboarding analytics for dashboard
        """
        analytics = {}

        # Filter by employee if provided
        onboarding_filter = {}
        step_completion_filter = {}

        if employee:
            onboarding_filter['assigned_to'] = employee
            step_completion_filter['customer_onboarding__assigned_to'] = employee

        # Onboarding status counts
        status_counts = CustomerOnboarding.objects.filter(
            **onboarding_filter
        ).values('status').annotate(count=Count('id'))

        analytics['status_counts'] = {
            'not_started': 0,
            'in_progress': 0,
            'completed': 0,
            'paused': 0,
            'abandoned': 0
        }

        for status in status_counts:
            analytics['status_counts'][status['status']] = status['count']

        # Onboarding completion time (avg days to complete)
        completed_onboardings = CustomerOnboarding.objects.filter(
            status='completed',
            start_date__isnull=False,
            completed_date__isnull=False,
            **onboarding_filter
        )

        if completed_onboardings.exists():
            total_days = 0
            count = 0

            for onboarding in completed_onboardings:
                days = (onboarding.completed_date.date() - onboarding.start_date.date()).days
                if days >= 0:  # Sanity check
                    total_days += days
                    count += 1

            analytics['avg_completion_days'] = round(total_days / count, 1) if count > 0 else 0
        else:
            analytics['avg_completion_days'] = 0

        # Step completion analytics
        step_completions = OnboardingStepCompletion.objects.filter(
            is_completed=True,
            **step_completion_filter
        )

        if step_completions.exists():
            # Most time-consuming steps
            step_time_data = {}

            for completion in step_completions:
                if completion.completed_date and completion.created_at:
                    step_name = completion.step.name
                    days = (completion.completed_date - completion.created_at).days

                    if step_name not in step_time_data:
                        step_time_data[step_name] = {'total_days': 0, 'count': 0}

                    step_time_data[step_name]['total_days'] += max(0, days)  # Avoid negative days
                    step_time_data[step_name]['count'] += 1

            # Calculate averages
            step_avg_times = []
            for step_name, data in step_time_data.items():
                if data['count'] > 0:
                    avg_days = round(data['total_days'] / data['count'], 1)
                    step_avg_times.append({
                        'step_name': step_name,
                        'avg_days': avg_days
                    })

            # Sort by average time (descending)
            analytics['step_avg_times'] = sorted(
                step_avg_times,
                key=lambda x: x['avg_days'],
                reverse=True
            )[:5]  # Top 5 most time-consuming steps
        else:
            analytics['step_avg_times'] = []

        # Satisfaction metrics from feedback
        analytics['satisfaction'] = OnboardingService.get_satisfaction_metrics()

        # Recent completions
        analytics['recent_completions'] = CustomerOnboarding.objects.filter(
            status='completed',
            **onboarding_filter
        ).order_by('-completed_date')[:5]

        return analytics

    @staticmethod
    def get_detailed_analytics(start_date=None, end_date=None):
        """
        Get detailed analytics for the analytics page
        """
        analytics = {}

        # Apply date filters if provided
        filters = {}

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                filters['created_at__gte'] = start_date
            except (ValueError, TypeError):
                pass

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                filters['created_at__lte'] = datetime.combine(end_date, datetime.max.time())
            except (ValueError, TypeError):
                pass

        # Onboarding volume over time
        onboardings = CustomerOnboarding.objects.filter(**filters)

        # Group by day
        onboarding_by_day = onboardings.annotate(
            day=TruncDay('created_at')
        ).values('day').annotate(count=Count('id')).order_by('day')

        analytics['onboarding_volume'] = {
            'labels': [entry['day'].strftime('%Y-%m-%d') for entry in onboarding_by_day],
            'data': [entry['count'] for entry in onboarding_by_day]
        }

        # Completion rate
        total_count = onboardings.count()
        completed_count = onboardings.filter(status='completed').count()

        analytics['completion_rate'] = round((completed_count / total_count * 100) if total_count > 0 else 0, 1)

        # Average time to complete each step
        step_completion_filters = {}

        if start_date:
            step_completion_filters['completed_date__gte'] = start_date

        if end_date:
            step_completion_filters['completed_date__lte'] = datetime.combine(end_date, datetime.max.time())

        step_completions = OnboardingStepCompletion.objects.filter(
            is_completed=True,
            **step_completion_filters
        ).select_related('step')

        step_data = {}
        for completion in step_completions:
            if completion.completed_date and completion.created_at:
                step_type = completion.step.step_type

                if step_type not in step_data:
                    step_data[step_type] = {
                        'total_hours': 0,
                        'count': 0,
                        'display_name': dict(OnboardingStep.STEP_TYPE_CHOICES).get(step_type, step_type)
                    }

                # Calculate hours (not just days for more precision)
                hours = (completion.completed_date - completion.created_at).total_seconds() / 3600
                step_data[step_type]['total_hours'] += hours
                step_data[step_type]['count'] += 1

        # Calculate averages
        for step_type, data in step_data.items():
            if data['count'] > 0:
                data['avg_hours'] = round(data['total_hours'] / data['count'], 1)
            else:
                data['avg_hours'] = 0

        analytics['step_completion_times'] = sorted(
            step_data.values(),
            key=lambda x: x['avg_hours'],
            reverse=True
        )

        # Satisfaction trends over time
        feedback_filters = {}

        if start_date:
            feedback_filters['submitted_at__gte'] = start_date

        if end_date:
            feedback_filters['submitted_at__lte'] = datetime.combine(end_date, datetime.max.time())

        feedback_by_month = OnboardingFeedback.objects.filter(
            **feedback_filters
        ).annotate(
            month=TruncMonth('submitted_at')
        ).values('month').annotate(
            avg_rating=Avg('overall_rating')
        ).order_by('month')

        analytics['satisfaction_trend'] = {
            'labels': [entry['month'].strftime('%Y-%m') for entry in feedback_by_month],
            'data': [float(entry['avg_rating']) for entry in feedback_by_month]
        }

        # Get the most common improvement suggestions
        feedback_with_improvements = OnboardingFeedback.objects.exclude(
            what_could_improve=''
        ).filter(**feedback_filters)

        improvement_text = " ".join([f.what_could_improve for f in feedback_with_improvements])

        # This is a very simplified text analysis - in a real app, you'd use NLP
        common_terms = OnboardingAnalyticsService._simple_text_analysis(improvement_text)
        analytics['common_improvement_terms'] = common_terms[:10]  # Top 10 terms

        return analytics

    @staticmethod
    def _simple_text_analysis(text):
        """
        Very simple text analysis to find common terms in feedback
        In a real application, you would use NLP libraries like NLTK or spaCy
        """
        import re
        from collections import Counter

        # Remove common stop words
        stop_words = {
            'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'by',
            'from', 'in', 'out', 'with', 'about', 'as', 'into', 'like', 'through',
            'after', 'before', 'between', 'under', 'over', 'of', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'my', 'your', 'his', 'her',
            'its', 'our', 'their', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
            'was', 'were', 'will', 'would', 'shall', 'should', 'may', 'might', 'must',
            'can', 'could'
        }

        # Tokenize text
        words = re.findall(r'\b\w+\b', text.lower())

        # Filter out stop words and short words
        filtered_words = [word for word in words if word not in stop_words and len(word) > 3]

        # Count word frequencies
        word_counts = Counter(filtered_words)

        # Return most common words
        return word_counts.most_common(20)
