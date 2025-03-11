from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, TemplateView, FormView, View
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from io import BytesIO
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt  # Only use if needed
from django.db import transaction
from django.http import JsonResponse, HttpResponseRedirect, Http404, HttpResponse
from weasyprint import HTML
from core.models import Customer, Employee
from core.mixins import EmployeeRequiredMixin
from .models import (
    OnboardingPlan, OnboardingStep, CustomerOnboarding,
    OnboardingStepCompletion, DataImportJob, OnboardingFeedback,
    OnboardingChecklistItem, ChecklistItemCompletion
)
from .forms import (
    CustomerOnboardingForm, OnboardingStepCompletionForm, DataImportForm,
    OnboardingFeedbackForm, ChecklistItemCompletionForm
)
from .services import (
    OnboardingService, DataImportService, NotificationService,
    OnboardingAnalyticsService
)
import io
import logging
logger = logging.getLogger(__name__)


class OnboardingDashboardView(LoginRequiredMixin, EmployeeRequiredMixin, TemplateView):
    """
    Dashboard view for onboarding progress and management
    """
    template_name = 'onboarding/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_profile

        # Get onboarding data based on role
        if employee.position in ['manager', 'account_manager', 'admin']:
            # Managers see all active onboarding processes
            active_onboardings = CustomerOnboarding.objects.filter(
                status__in=['not_started', 'in_progress', 'paused']
            ).select_related('customer', 'plan', 'assigned_to', 'current_step')

            # Filter by assigned if requested
            if self.request.GET.get('assigned') == 'me':
                active_onboardings = active_onboardings.filter(assigned_to=employee)
        else:
            # Regular employees only see onboardings assigned to them
            active_onboardings = CustomerOnboarding.objects.filter(
                assigned_to=employee,
                status__in=['not_started', 'in_progress', 'paused']
            ).select_related('customer', 'plan', 'current_step')

        # Get onboarding analytics
        analytics = OnboardingAnalyticsService.get_analytics(employee)

        context.update({
            'active_onboardings': active_onboardings,
            'analytics': analytics,
            'recent_completions': OnboardingStepCompletion.objects.filter(
                is_completed=True
            ).select_related(
                'customer_onboarding__customer',
                'step'
            ).order_by('-completed_date')[:5],
            'needs_attention': OnboardingService.get_onboardings_needing_attention()
        })

        return context


class OnboardingPlanListView(LoginRequiredMixin, EmployeeRequiredMixin, ListView):
    """
    List all available onboarding plans
    """
    model = OnboardingPlan
    template_name = 'onboarding/plan_list.html'
    context_object_name = 'plans'

    def get_queryset(self):
        # Only show active plans unless user is admin
        queryset = OnboardingPlan.objects.all()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(is_active=True)
        return queryset


class OnboardingPlanDetailView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    """
    Detailed view of an onboarding plan with all its steps
    """
    model = OnboardingPlan
    template_name = 'onboarding/plan_detail.html'
    context_object_name = 'plan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plan = self.get_object()

        context.update({
            'steps': plan.steps.all().order_by('order'),
            'total_estimated_time': sum(step.estimated_minutes for step in plan.steps.all())
        })

        return context


class CustomerOnboardingDetailView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    """
    Detailed view of a customer's onboarding progress
    """
    model = CustomerOnboarding
    template_name = 'onboarding/customer_onboarding_detail.html'
    context_object_name = 'onboarding'

    def get_queryset(self):
        # Include related objects for better performance
        return CustomerOnboarding.objects.select_related(
            'customer', 'plan', 'assigned_to', 'current_step'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        onboarding = self.get_object()

        # Get all steps with completion status
        steps_with_status = []
        for step in onboarding.plan.steps.all().order_by('order'):
            try:
                completion = OnboardingStepCompletion.objects.get(
                    customer_onboarding=onboarding,
                    step=step
                )
            except OnboardingStepCompletion.DoesNotExist:
                completion = None

            steps_with_status.append({
                'step': step,
                'completion': completion
            })

        context.update({
            'steps_with_status': steps_with_status,
            'current_step_index': next(
                (i for i, s in enumerate(steps_with_status)
                 if s['step'] == onboarding.current_step),
                0
            ),
            'import_jobs': onboarding.import_jobs.all().order_by('-created_at')[:5],
            'feedback': onboarding.feedback.all().order_by('-submitted_at'),
            'total_steps': len(steps_with_status),
            'completed_steps': len([s for s in steps_with_status if s['completion'] and s['completion'].is_completed])
        })

        return context

    def post(self, request, *args, **kwargs):
        """Handle action buttons"""
        onboarding = self.get_object()
        action = request.POST.get('action')

        if action == 'start_onboarding':
            onboarding.status = 'in_progress'
            onboarding.start_date = timezone.now()
            onboarding.save()

            # Set up step completions if not already created
            OnboardingService.setup_step_completions(onboarding)

            messages.success(request, f"Onboarding process for {onboarding.customer.company_name} has been started.")
            return redirect('onboarding:customer_onboarding_detail', pk=onboarding.pk)

        elif action == 'pause_onboarding':
            onboarding.status = 'paused'
            onboarding.save()
            messages.info(request, f"Onboarding process for {onboarding.customer.company_name} has been paused.")
            return redirect('onboarding:customer_onboarding_detail', pk=onboarding.pk)

        elif action == 'resume_onboarding':
            onboarding.status = 'in_progress'
            onboarding.save()
            messages.success(request, f"Onboarding process for {onboarding.customer.company_name} has been resumed.")
            return redirect('onboarding:customer_onboarding_detail', pk=onboarding.pk)

        elif action == 'complete_onboarding':
            onboarding.status = 'completed'
            onboarding.completed_date = timezone.now()
            onboarding.progress_percentage = 100
            onboarding.save()

            # Send completion notification
            NotificationService.send_onboarding_completion_notifications(onboarding)

            messages.success(request, f"Onboarding process for {onboarding.customer.company_name} has been marked as completed.")
            return redirect('onboarding:customer_onboarding_detail', pk=onboarding.pk)

        elif action == 'assign_to_me':
            onboarding.assigned_to = request.user.employee_profile
            onboarding.save()
            messages.success(request, f"You are now assigned to {onboarding.customer.company_name}'s onboarding.")
            return redirect('onboarding:customer_onboarding_detail', pk=onboarding.pk)

        # If no valid action, just reload the page
        return self.get(request, *args, **kwargs)


class CreateCustomerOnboardingView(LoginRequiredMixin, EmployeeRequiredMixin, CreateView):
    """
    Create a new onboarding process for a customer
    """
    model = CustomerOnboarding
    form_class = CustomerOnboardingForm
    template_name = 'onboarding/customer_onboarding_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Get the customer if available
        customer_id = self.kwargs.get('customer_id')
        if customer_id:
            kwargs['initial'] = {'customer': customer_id}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # If customer_id is in URL, get customer details
        customer_id = self.kwargs.get('customer_id')
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
                context['customer'] = customer
            except Customer.DoesNotExist:
                pass

        context['plans'] = OnboardingPlan.objects.filter(is_active=True)
        return context

    def form_valid(self, form):
        with transaction.atomic():
            # Set current user as assigned_to if not specified
            if not form.cleaned_data.get('assigned_to'):
                form.instance.assigned_to = self.request.user.employee_profile

            # Save the onboarding
            response = super().form_valid(form)

            # Set up related records
            OnboardingService.setup_step_completions(self.object)

            # Send notifications
            NotificationService.send_onboarding_created_notifications(self.object)

            messages.success(
                self.request,
                f"Onboarding process created for {self.object.customer.company_name}"
            )

            return response

    def get_success_url(self):
        return reverse('onboarding:customer_onboarding_detail', kwargs={'pk': self.object.pk})


class StepDetailView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    """
    Detailed view of an onboarding step with customer progress
    """
    template_name = 'onboarding/step_detail.html'
    context_object_name = 'step_completion'

    def get_object(self):
        onboarding_id = self.kwargs.get('onboarding_id')
        step_id = self.kwargs.get('step_id')

        # Get the customer onboarding
        onboarding = get_object_or_404(CustomerOnboarding, pk=onboarding_id)
        step = get_object_or_404(OnboardingStep, pk=step_id, plan=onboarding.plan)

        # Get or create the step completion record
        step_completion, created = OnboardingStepCompletion.objects.get_or_create(
            customer_onboarding=onboarding,
            step=step,
            defaults={'is_completed': False}
        )

        return step_completion

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        step_completion = self.get_object()

        # Get checklist items with completion status
        checklist_items = []
        for item in step_completion.step.checklist_items.all().order_by('order'):
            try:
                completion = ChecklistItemCompletion.objects.get(
                    onboarding_step_completion=step_completion,
                    checklist_item=item
                )
            except ChecklistItemCompletion.DoesNotExist:
                # Create it if it doesn't exist
                completion = ChecklistItemCompletion.objects.create(
                    onboarding_step_completion=step_completion,
                    checklist_item=item,
                    is_completed=False
                )

            checklist_items.append({
                'item': item,
                'completion': completion
            })

        # Get import jobs related to this step
        import_jobs = DataImportJob.objects.filter(
            customer_onboarding=step_completion.customer_onboarding,
            related_step=step_completion.step
        ).order_by('-created_at')

        context.update({
            'onboarding': step_completion.customer_onboarding,
            'step': step_completion.step,
            'checklist_items': checklist_items,
            'import_jobs': import_jobs,
            'completion_form': OnboardingStepCompletionForm(instance=step_completion),
            'import_form': DataImportForm(initial={
                'customer_onboarding': step_completion.customer_onboarding.id,
                'related_step': step_completion.step.id
            }),
            'next_step': OnboardingService.get_next_step(step_completion),
            'prev_step': OnboardingService.get_previous_step(step_completion)
        })

        return context

    def post(self, request, *args, **kwargs):
        """Handle step completion form submission"""
        step_completion = self.get_object()
        action = request.POST.get('action')

        if action == 'complete_step':
            form = OnboardingStepCompletionForm(request.POST, instance=step_completion)
            if form.is_valid():
                # Mark the step as completed
                step_completion = form.save(commit=False)
                step_completion.is_completed = True
                step_completion.completed_date = timezone.now()
                step_completion.completed_by = request.user
                step_completion.save()

                # Update the customer onboarding progress
                onboarding = step_completion.customer_onboarding
                onboarding.calculate_progress()
                onboarding.update_current_step()

                # Send notification
                NotificationService.send_step_completion_notification(step_completion)

                messages.success(request, f"{step_completion.step.name} marked as completed.")

                # Redirect to the next step if available, otherwise back to onboarding detail
                next_step = OnboardingService.get_next_step(step_completion)
                if next_step:
                    return redirect('onboarding:step_detail',
                                   onboarding_id=onboarding.id,
                                   step_id=next_step.step.id)
                else:
                    return redirect('onboarding:customer_onboarding_detail',
                                   pk=onboarding.id)
            else:
                messages.error(request, "There was an error completing this step.")
                return self.get(request, *args, **kwargs)

        elif action == 'update_checklist':
            # Update checklist item completions
            checklist_item_id = request.POST.get('checklist_item_id')
            is_completed = request.POST.get('is_completed') == 'true'

            try:
                checklist_item = OnboardingChecklistItem.objects.get(id=checklist_item_id)
                item_completion, created = ChecklistItemCompletion.objects.get_or_create(
                    onboarding_step_completion=step_completion,
                    checklist_item=checklist_item,
                    defaults={'is_completed': is_completed}
                )

                if not created:
                    item_completion.is_completed = is_completed
                    item_completion.completed_date = timezone.now() if is_completed else None
                    item_completion.completed_by = request.user if is_completed else None
                    item_completion.save()

                # Check if all required items are completed
                all_completed = OnboardingService.are_all_required_items_completed(step_completion)

                return JsonResponse({
                    'success': True,
                    'is_completed': is_completed,
                    'all_completed': all_completed
                })
            except Exception as e:
                logger.error(f"Error updating checklist item: {str(e)}")
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        # If no valid action, just reload the page
        return self.get(request, *args, **kwargs)


@login_required
def submit_import_job(request, onboarding_id, step_id):
    """
    Handle data import job submission
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # Verify the onboarding and step exist and are related
    onboarding = get_object_or_404(CustomerOnboarding, pk=onboarding_id)
    step = get_object_or_404(OnboardingStep, pk=step_id, plan=onboarding.plan)

    form = DataImportForm(request.POST, request.FILES)
    if form.is_valid():
        import_job = form.save(commit=False)
        import_job.customer_onboarding = onboarding
        import_job.related_step = step
        import_job.created_by = request.user
        import_job.save()

        # Start the import process asynchronously (this would typically use Celery or similar)
        try:
            DataImportService.process_import_job(import_job)
            messages.success(request, "Data import job submitted successfully.")
        except Exception as e:
            import_job.status = 'failed'
            import_job.error_details = str(e)
            import_job.save()
            messages.error(request, f"Error processing import: {str(e)}")

        return redirect('onboarding:step_detail', onboarding_id=onboarding_id, step_id=step_id)
    else:
        messages.error(request, "There was an error with your import file.")
        return redirect('onboarding:step_detail', onboarding_id=onboarding_id, step_id=step_id)


class WelcomeView(LoginRequiredMixin, TemplateView):
    """
    Welcome view for customers starting their onboarding
    """
    template_name = 'onboarding/welcome.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the customer associated with current user
        if hasattr(self.request.user, 'customer'):
            customer = self.request.user.customer

            try:
                # Get or create onboarding for this customer
                onboarding, created = CustomerOnboarding.objects.get_or_create(
                    customer=customer,
                    defaults={
                        'plan': OnboardingPlan.objects.filter(tier='starter').first(),
                        'status': 'not_started'
                    }
                )

                context['onboarding'] = onboarding
                context['next_step'] = onboarding.current_step or onboarding.plan.steps.order_by('order').first()

            except Exception as e:
                logger.error(f"Error getting customer onboarding: {str(e)}")

        return context


class CustomerOnboardingStepView(LoginRequiredMixin, DetailView):
    """
    Customer-facing view for completing onboarding steps
    """
    template_name = 'onboarding/customer_step.html'
    context_object_name = 'step_completion'

    def get_object(self):
        step_id = self.kwargs.get('step_id')

        # Get the customer associated with current user
        if not hasattr(self.request.user, 'customer'):
            raise Http404("No customer profile found for this user")

        customer = self.request.user.customer

        # Get the onboarding for this customer
        try:
            onboarding = CustomerOnboarding.objects.get(customer=customer)
        except CustomerOnboarding.DoesNotExist:
            raise Http404("No onboarding process found for this customer")

        # Get the step
        step = get_object_or_404(OnboardingStep, pk=step_id, plan=onboarding.plan)

        # Get or create the step completion record
        step_completion, created = OnboardingStepCompletion.objects.get_or_create(
            customer_onboarding=onboarding,
            step=step,
            defaults={'is_completed': False}
        )

        return step_completion

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        step_completion = self.get_object()

        # Similar to StepDetailView but with customer-specific UI adjustments
        # Get checklist items with completion status
        checklist_items = []
        for item in step_completion.step.checklist_items.all().order_by('order'):
            try:
                completion = ChecklistItemCompletion.objects.get(
                    onboarding_step_completion=step_completion,
                    checklist_item=item
                )
            except ChecklistItemCompletion.DoesNotExist:
                completion = ChecklistItemCompletion.objects.create(
                    onboarding_step_completion=step_completion,
                    checklist_item=item,
                    is_completed=False
                )

            checklist_items.append({
                'item': item,
                'completion': completion
            })

        context.update({
            'onboarding': step_completion.customer_onboarding,
            'step': step_completion.step,
            'checklist_items': checklist_items,
            'feedback_form': OnboardingFeedbackForm(initial={
                'customer_onboarding': step_completion.customer_onboarding.id,
                'step': step_completion.step.id
            }),
            'next_step': OnboardingService.get_next_step(step_completion),
            'prev_step': OnboardingService.get_previous_step(step_completion),
            'progress_percentage': step_completion.customer_onboarding.progress_percentage
        })

        return context

    def post(self, request, *args, **kwargs):
        """Handle step actions for customer"""
        step_completion = self.get_object()
        action = request.POST.get('action')

        if action == 'complete_step':
            # Mark step as completed by customer
            if not step_completion.is_completed:
                step_completion.is_completed = True
                step_completion.completed_date = timezone.now()
                step_completion.completed_by = request.user
                step_completion.save()

                # Update the customer onboarding progress
                onboarding = step_completion.customer_onboarding
                onboarding.calculate_progress()
                onboarding.update_current_step()

                # Send notification to assigned representative
                NotificationService.send_customer_step_completion_notification(step_completion)

                messages.success(request, f"Great job! You've completed the {step_completion.step.name} step.")

            # Redirect to the next step if available, otherwise to the dashboard
            next_step = OnboardingService.get_next_step(step_completion)
            if next_step:
                return redirect('onboarding:customer_step', step_id=next_step.step.id)
            else:
                return redirect('onboarding:customer_dashboard')

        elif action == 'update_checklist':
            # Identical to the employee version but with different notification
            checklist_item_id = request.POST.get('checklist_item_id')
            is_completed = request.POST.get('is_completed') == 'true'

            try:
                checklist_item = OnboardingChecklistItem.objects.get(id=checklist_item_id)
                item_completion, created = ChecklistItemCompletion.objects.get_or_create(
                    onboarding_step_completion=step_completion,
                    checklist_item=checklist_item,
                    defaults={'is_completed': is_completed}
                )

                if not created:
                    item_completion.is_completed = is_completed
                    item_completion.completed_date = timezone.now() if is_completed else None
                    item_completion.completed_by = request.user if is_completed else None
                    item_completion.save()

                # Check if all required items are completed
                all_completed = OnboardingService.are_all_required_items_completed(step_completion)

                return JsonResponse({
                    'success': True,
                    'is_completed': is_completed,
                    'all_completed': all_completed
                })
            except Exception as e:
                logger.error(f"Error updating checklist item: {str(e)}")
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        elif action == 'submit_feedback':
            form = OnboardingFeedbackForm(request.POST)
            if form.is_valid():
                feedback = form.save(commit=False)
                feedback.customer_onboarding = step_completion.customer_onboarding
                feedback.step = step_completion.step
                feedback.submitted_by = request.user
                feedback.save()

                messages.success(request, "Thank you for your feedback!")

                # Redirect to the current step
                return redirect('onboarding:customer_step', step_id=step_completion.step.id)
            else:
                messages.error(request, "There was an error submitting your feedback.")
                return self.get(request, *args, **kwargs)

        # If no valid action, just reload the page
        return self.get(request, *args, **kwargs)


class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    """
    Dashboard view for customers to track their onboarding progress
    """
    template_name = 'onboarding/customer_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the customer associated with current user
        if not hasattr(self.request.user, 'customer'):
            context['no_customer_profile'] = True
            return context

        customer = self.request.user.customer

        try:
            # Get onboarding for this customer
            onboarding = CustomerOnboarding.objects.get(customer=customer)

            # Get steps with completion status
            steps_with_status = []
            for step in onboarding.plan.steps.all().order_by('order'):
                try:
                    completion = OnboardingStepCompletion.objects.get(
                        customer_onboarding=onboarding,
                        step=step
                    )
                except OnboardingStepCompletion.DoesNotExist:
                    completion = None

                steps_with_status.append({
                    'step': step,
                    'completion': completion
                })

            context.update({
                'onboarding': onboarding,
                'steps_with_status': steps_with_status,
                'import_jobs': onboarding.import_jobs.all().order_by('-created_at')[:3],
                'current_step': onboarding.current_step,
                'next_step': onboarding.get_next_step(),
                'days_since_start': (timezone.now().date() - onboarding.start_date.date()).days if onboarding.start_date else 0,
                'estimated_completion_date': (onboarding.start_date + timezone.timedelta(days=onboarding.plan.estimated_days)).date() if onboarding.start_date else None
            })
        except CustomerOnboarding.DoesNotExist:
            context['no_onboarding'] = True

        return context


@login_required
def generate_import_template(request, import_type):
    """
    Generate a template file for data import
    """
    try:
        # Get template based on import type
        template_file = DataImportService.get_import_template(import_type)

        # Serve the file
        response = HttpResponse(template_file.read(), content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = f'attachment; filename="{import_type}_import_template.xlsx"'
        return response
    except Exception as e:
        logger.error(f"Error generating import template: {str(e)}")
        messages.error(request, f"Error generating template: {str(e)}")
        return redirect(request.META.get('HTTP_REFERER', 'onboarding:dashboard'))


class SubmitFeedbackView(LoginRequiredMixin, CreateView):
    """
    View for submitting feedback about the onboarding process
    """
    model = OnboardingFeedback
    form_class = OnboardingFeedbackForm
    template_name = 'onboarding/feedback_form.html'

    def get_initial(self):
        initial = super().get_initial()

        # Pre-fill form based on URL parameters
        onboarding_id = self.kwargs.get('onboarding_id')
        step_id = self.kwargs.get('step_id')

        if onboarding_id:
            initial['customer_onboarding'] = onboarding_id

        if step_id:
            initial['step'] = step_id
            initial['feedback_type'] = 'step'
        else:
            initial['feedback_type'] = 'overall'

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        onboarding_id = self.kwargs.get('onboarding_id')
        if onboarding_id:
            context['onboarding'] = get_object_or_404(CustomerOnboarding, pk=onboarding_id)

        step_id = self.kwargs.get('step_id')
        if step_id:
            context['step'] = get_object_or_404(OnboardingStep, pk=step_id)

        return context

    def form_valid(self, form):
        form.instance.submitted_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Thank you for your feedback!")
        return response

    def get_success_url(self):
        if hasattr(self.request.user, 'employee_profile'):
            # Employee redirects to onboarding detail
            return reverse('onboarding:customer_onboarding_detail',
                          kwargs={'pk': self.object.customer_onboarding.pk})
        else:
            # Customer redirects to their dashboard
            return reverse('onboarding:customer_dashboard')


class OnboardingAnalyticsView(LoginRequiredMixin, EmployeeRequiredMixin, TemplateView):
    """
    View for onboarding analytics and metrics
    """
    template_name = 'onboarding/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get date range from request
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        # Get analytics data
        analytics = OnboardingAnalyticsService.get_detailed_analytics(start_date, end_date)

        context.update({
            'analytics': analytics,
            'start_date': start_date or (timezone.now() - timezone.timedelta(days=30)).strftime('%Y-%m-%d'),
            'end_date': end_date or timezone.now().strftime('%Y-%m-%d')
        })

        return context

@login_required
def generate_onboarding_report(request, pk):
    """Generate a stylish PDF report for a customer onboarding with progress chart"""
    onboarding = get_object_or_404(CustomerOnboarding, pk=pk)

    # Create response object
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="onboarding_report_{pk}.pdf"'

    # Create the PDF document
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )

    # Container for elements to be added to the PDF
    elements = []

    # Define styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1  # Center alignment
    title_style.textColor = colors.darkblue

    subtitle_style = styles['Heading2']
    subtitle_style.textColor = colors.darkblue

    section_title_style = styles['Heading3']
    section_title_style.textColor = colors.darkblue

    normal_style = styles['Normal']

    # Title
    elements.append(Paragraph(f"Onboarding Report", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"{onboarding.customer.company_name}", subtitle_style))
    elements.append(Spacer(1, 20))

    # Customer Information
    elements.append(Paragraph("Customer Information", section_title_style))

    customer_data = [
        ["Company Name:", onboarding.customer.company_name],
        ["Contact Person:", onboarding.customer.contact_person],
        ["Email:", onboarding.customer.email],
        ["Phone:", onboarding.customer.phone]
    ]

    customer_table = Table(customer_data, colWidths=[150, 300])
    customer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.darkblue),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(customer_table)
    elements.append(Spacer(1, 20))

    # Onboarding Overview
    elements.append(Paragraph("Onboarding Overview", section_title_style))

    overview_data = [
        ["Plan:", onboarding.plan.name],
        ["Status:", onboarding.get_status_display()],
        ["Progress:", f"{onboarding.progress_percentage}%"],
        ["Start Date:", onboarding.start_date.strftime("%Y-%m-%d") if onboarding.start_date else "Not Started"],
        ["Completed Date:", onboarding.completed_date.strftime("%Y-%m-%d") if onboarding.completed_date else "Not Completed"],
    ]

    if onboarding.assigned_to:
        overview_data.append(["Assigned To:", onboarding.assigned_to.get_full_name()])

    overview_table = Table(overview_data, colWidths=[150, 300])
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.darkblue),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(overview_table)
    elements.append(Spacer(1, 20))

    # Progress Chart
    elements.append(Paragraph("Onboarding Progress", section_title_style))

    # Create drawing for pie chart
    drawing = Drawing(400, 200)
    progress_pie = Pie()
    progress_pie.x = 150
    progress_pie.y = 50
    progress_pie.width = 100
    progress_pie.height = 100
    progress_pie.data = [onboarding.progress_percentage, 100-onboarding.progress_percentage]
    progress_pie.labels = [f"{onboarding.progress_percentage}% Complete", f"{100-onboarding.progress_percentage}% Remaining"]

    # Colors for the pie chart
    progress_pie.slices[0].fillColor = HexColor('#007bff')  # Blue for completed (Bootstrap primary)
    progress_pie.slices[1].fillColor = HexColor('#e9ecef')  # Light gray for remaining

    drawing.add(progress_pie)
    elements.append(drawing)
    elements.append(Spacer(1, 20))

    # Completed Steps
    elements.append(Paragraph("Completed Steps", section_title_style))

    # Header row for steps table
    steps_data = [["Step", "Type", "Completion Date", "Completed By"]]

    for completion in onboarding.step_completions.filter(is_completed=True):
        completed_by = completion.completed_by.get_full_name() if completion.completed_by else "N/A"
        completed_date = completion.completed_date.strftime("%Y-%m-%d") if completion.completed_date else "N/A"

        steps_data.append([
            completion.step.name,
            completion.step.get_step_type_display(),
            completed_date,
            completed_by
        ])

    if len(steps_data) == 1:  # Only header row, no data
        elements.append(Paragraph("No steps have been completed yet.", normal_style))
    else:
        steps_table = Table(steps_data, colWidths=[200, 100, 100, 100])
        steps_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        elements.append(steps_table)

    elements.append(Spacer(1, 30))

    # Pending Steps (if any)
    pending_steps = onboarding.step_completions.filter(is_completed=False)
    if pending_steps.exists():
        elements.append(Paragraph("Pending Steps", section_title_style))

        pending_data = [["Step", "Type", "Required", "Est. Time (min)"]]

        for completion in pending_steps:
            step = completion.step
            pending_data.append([
                step.name,
                step.get_step_type_display(),
                "Yes" if step.is_required else "No",
                str(step.estimated_minutes)
            ])

        pending_table = Table(pending_data, colWidths=[200, 100, 100, 100])
        pending_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        elements.append(pending_table)
        elements.append(Spacer(1, 30))

    # Footer with date
    report_date = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Report generated on: {report_date}", normal_style))

    # Build the PDF
    doc.build(elements)

    # Get the value of the BytesIO buffer and write it to the response
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)

    return response

@login_required
def generate_html_report(request, pk):
    """Generate a PDF report from HTML template"""
    onboarding = get_object_or_404(CustomerOnboarding, pk=pk)

    # Render HTML template with context
    html_string = render_to_string('onboarding/report_template.html', {
        'onboarding': onboarding,
        'report_date': timezone.now()
    })

    # Create PDF from HTML
    html = HTML(string=html_string)
    pdf = html.write_pdf()

    # Create response
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="onboarding_report_{pk}.pdf"'

    return response
