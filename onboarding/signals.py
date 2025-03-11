from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import (
    CustomerOnboarding, OnboardingStepCompletion,
    DataImportJob, OnboardingFeedback
)


@receiver(post_save, sender=CustomerOnboarding)
def onboarding_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for Customer Onboarding.
    Sets up initial onboarding steps when a new onboarding is created.
    """
    if created and instance.plan:
        # Setup onboarding steps
        from .services import OnboardingService
        OnboardingService.setup_step_completions(instance)


@receiver(post_save, sender=OnboardingStepCompletion)
def step_completion_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for Step Completion.
    Updates onboarding progress when a step is completed.
    """
    if not created and instance.is_completed:
        # Update onboarding progress
        instance.customer_onboarding.calculate_progress()
        instance.customer_onboarding.last_activity_date = instance.completed_date
        instance.customer_onboarding.save(update_fields=['progress_percentage', 'last_activity_date'])

        # Check if this was the last step
        next_step = instance.customer_onboarding.get_next_step()
        if not next_step and instance.customer_onboarding.status != 'completed':
            # Mark onboarding as completed if all steps are done
            if instance.customer_onboarding.progress_percentage >= 100:
                instance.customer_onboarding.status = 'completed'
                instance.customer_onboarding.completed_date = instance.completed_date
                instance.customer_onboarding.save(update_fields=['status', 'completed_date'])


@receiver(post_save, sender=DataImportJob)
def data_import_post_save(sender, instance, created, **kwargs):
    if created:
        instance.customer_onboarding.last_activity_date = instance.created_at
        instance.customer_onboarding.save(update_fields=['last_activity_date'])

        # Run in a background thread
        import threading
        thread = threading.Thread(target=lambda: DataImportService.process_import_job(instance))
        thread.daemon = True
        thread.start()

@receiver(post_save, sender=OnboardingFeedback)
def feedback_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for Feedback.
    Creates notification for assigned rep when feedback is submitted.
    """
    if created:
        # Create notification for the assigned rep
        onboarding = instance.customer_onboarding

        if onboarding.assigned_to and onboarding.assigned_to.user:
            from .models import OnboardingNotification

            # Determine feedback type text
            feedback_type = "overall"
            if instance.feedback_type != 'overall' and instance.step:
                feedback_type = f"step '{instance.step.name}'"

            OnboardingNotification.objects.create(
                customer_onboarding=onboarding,
                notification_type='milestone',
                title=f"New Feedback Received: {onboarding.customer.company_name}",
                message=f"Customer has submitted {feedback_type} feedback with a rating of {instance.overall_rating}/5.",
                related_step=instance.step,
                recipient=onboarding.assigned_to.user
            )
