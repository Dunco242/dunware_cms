# core/customer_lifecycle.py
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, F, Sum, Count, Max
from django.db import transaction
from django.contrib.auth.models import User

from .models import (
    Customer, Lead, Meeting, Task, Note, Event,
    Employee, ServiceSubscription, Invoice, Payment
)
from .notification_service import SmartNotificationService

logger = logging.getLogger(__name__)

class CustomerLifecycleManager:
    """
    Manages the entire customer lifecycle from acquisition to retention
    with automated workflows and engagement optimization
    """

    def __init__(self):
        self.notification_service = SmartNotificationService()

    def process_new_customer(self, customer):
        """
        Set up initial onboarding process for a new customer

        Args:
            customer: The newly created Customer object
        """
        try:
            with transaction.atomic():
                # Set up welcome email task
                self._create_welcome_email_task(customer)

                # Set up initial meeting task
                self._create_initial_meeting_task(customer)

                # Set up follow-up task
                self._create_followup_task(customer, days=7)

                # Notify account manager
                if customer.assigned_to:
                    self.notification_service.create_notification(
                        user=customer.assigned_to.user,
                        title="New Customer Added",
                        message=f"New customer {customer.company_name} has been added to your accounts.",
                        notification_type="other",
                        event_datetime=timezone.now(),
                        priority="medium",
                        content_object=customer,
                        action_url=f"/customers/{customer.id}/"
                    )

                logger.info(f"Customer lifecycle initiated for {customer.company_name}")
                return True

        except Exception as e:
            logger.error(f"Error setting up customer lifecycle: {str(e)}")
            return False

    def _create_welcome_email_task(self, customer):
        """Create task for sending welcome email"""
        if not customer.assigned_to:
            logger.warning(f"Cannot create welcome email task - no assigned employee for {customer.company_name}")
            return None

        task = Task.objects.create(
            title=f"Send welcome email to {customer.company_name}",
            description=f"Send a personalized welcome email to {customer.contact_person} at {customer.email}. Include company brochure and schedule a welcome call.",
            due_date=timezone.now() + timedelta(days=1),
            priority="high",
            status="pending",
            assigned_to=customer.assigned_to,
            created_by=customer.assigned_to,
            customer=customer
        )

        return task

    def _create_initial_meeting_task(self, customer):
        """Create task for scheduling initial meeting"""
        if not customer.assigned_to:
            return None

        task = Task.objects.create(
            title=f"Schedule kickoff meeting with {customer.company_name}",
            description=f"Schedule a kickoff meeting with {customer.contact_person} to discuss their specific needs and how we can best serve them.",
            due_date=timezone.now() + timedelta(days=3),
            priority="high",
            status="pending",
            assigned_to=customer.assigned_to,
            created_by=customer.assigned_to,
            customer=customer
        )

        return task

    def _create_followup_task(self, customer, days=7):
        """Create a follow-up task after specified days"""
        if not customer.assigned_to:
            return None

        task = Task.objects.create(
            title=f"Follow up with {customer.company_name}",
            description=f"Check in with {customer.contact_person} to ensure they're having a good experience and address any questions or concerns.",
            due_date=timezone.now() + timedelta(days=days),
            priority="medium",
            status="pending",
            assigned_to=customer.assigned_to,
            created_by=customer.assigned_to,
            customer=customer
        )

        return task

    def evaluate_customer_health(self, customer=None):
        """
        Evaluate customer health and trigger appropriate actions

        Args:
            customer: Specific customer to evaluate, or all active customers if None
        """
        customers_to_check = []

        if customer:
            customers_to_check = [customer]
        else:
            # Get all active customers
            customers_to_check = Customer.objects.filter(status='active')

        for customer in customers_to_check:
            health_score, factors = self._calculate_health_score(customer)

            # Log health score for tracking
            logger.info(f"Customer {customer.company_name} health score: {health_score}")

            # Take actions based on health score
            if health_score < 50:
                self._handle_at_risk_customer(customer, health_score, factors)
            elif health_score < 70:
                self._handle_needs_attention_customer(customer, health_score, factors)
            else:
                self._handle_healthy_customer(customer, health_score, factors)

    def _calculate_health_score(self, customer):
        """
        Calculate customer health score based on various factors

        Returns:
            tuple: (score, factors_dict)
        """
        now = timezone.now()
        factors = {}

        # Base score
        score = 70

        # 1. Recency of interactions
        last_meeting = Meeting.objects.filter(customers=customer).aggregate(Max('start_time'))['start_time__max']
        last_note = Note.objects.filter(customer=customer).aggregate(Max('created_at'))['created_at__max']
        last_task = Task.objects.filter(customer=customer).aggregate(Max('updated_at'))['updated_at__max']

        # Get most recent interaction
        latest_dates = [d for d in [last_meeting, last_note, last_task] if d is not None]

        if latest_dates:
            most_recent = max(latest_dates)
            days_since_interaction = (now - most_recent).days

            # Adjust score based on recency
            if days_since_interaction < 7:
                score += 10
                factors['recent_interaction'] = 'Recent interaction (+10)'
            elif days_since_interaction < 30:
                score += 0  # Neutral
                factors['recent_interaction'] = 'Interaction within last month (0)'
            elif days_since_interaction < 60:
                score -= 10
                factors['recent_interaction'] = 'No interaction for >30 days (-10)'
            else:
                score -= 25
                factors['recent_interaction'] = 'No interaction for >60 days (-25)'
        else:
            # No interactions at all
            score -= 30
            factors['recent_interaction'] = 'No recorded interactions (-30)'

        # 2. Payment history
        recent_payments = Payment.objects.filter(
            customer=customer,
            transaction_date__gte=now - timedelta(days=90)
        )

        paid_on_time_count = recent_payments.filter(status='completed').count()
        late_payment_count = Invoice.objects.filter(
            customer=customer,
            status='overdue',
            due_date__gte=now - timedelta(days=90)
        ).count()

        if late_payment_count == 0 and paid_on_time_count > 0:
            score += 15
            factors['payment'] = 'Excellent payment history (+15)'
        elif late_payment_count == 0 and paid_on_time_count == 0:
            # No payments due, neutral
            factors['payment'] = 'No recent payments due (0)'
        elif late_payment_count > 0 and late_payment_count < paid_on_time_count:
            score -= 10
            factors['payment'] = 'Some late payments (-10)'
        else:
            score -= 25
            factors['payment'] = 'Poor payment history (-25)'

        # 3. Active subscriptions
        active_subscriptions = ServiceSubscription.objects.filter(
            customer=customer,
            is_active=True
        ).count()

        if active_subscriptions > 2:
            score += 15
            factors['subscriptions'] = 'Multiple active subscriptions (+15)'
        elif active_subscriptions > 0:
            score += 5
            factors['subscriptions'] = 'Has active subscription (+5)'
        else:
            score -= 10
            factors['subscriptions'] = 'No active subscriptions (-10)'

        # 4. Project engagement (if using customer_projects app)
        # This is a placeholder - you'll need to implement this if you connect to your customer_projects app
        # For example:
        # active_projects = Project.objects.filter(customer=customer, status__in=['in_progress', 'active']).count()
        # if active_projects > 0:
        #     score += 10

        # Ensure score is between 0-100
        score = max(0, min(100, score))

        return score, factors

    def _handle_at_risk_customer(self, customer, health_score, factors):
        """Handle customers with low health scores (at risk)"""
        if not customer.assigned_to:
            logger.warning(f"Cannot handle at-risk customer {customer.company_name} - no assigned employee")
            return

        # Create high priority task for account manager
        task = Task.objects.create(
            title=f"URGENT: At-risk customer {customer.company_name}",
            description=f"This customer has a health score of {health_score}. Key issues: {', '.join(factors.values())}. Please contact them immediately to address concerns.",
            due_date=timezone.now() + timedelta(days=1),
            priority="high",
            status="pending",
            assigned_to=customer.assigned_to,
            created_by=customer.assigned_to,
            customer=customer
        )

        # Send notification
        self.notification_service.create_notification(
            user=customer.assigned_to.user,
            title="At-Risk Customer Alert",
            message=f"{customer.company_name} is at risk (Health Score: {health_score}). Immediate attention required.",
            notification_type="other",
            event_datetime=timezone.now(),
            priority="high",
            content_object=customer,
            action_url=f"/customers/{customer.id}/"
        )

    def _handle_needs_attention_customer(self, customer, health_score, factors):
        """Handle customers with moderate health scores (needs attention)"""
        if not customer.assigned_to:
            return

        # Create medium priority task
        task = Task.objects.create(
            title=f"Customer needs attention: {customer.company_name}",
            description=f"This customer has a health score of {health_score}. Areas for improvement: {', '.join(factors.values())}. Please schedule a check-in.",
            due_date=timezone.now() + timedelta(days=3),
            priority="medium",
            status="pending",
            assigned_to=customer.assigned_to,
            created_by=customer.assigned_to,
            customer=customer
        )

        # Send notification
        self.notification_service.create_notification(
            user=customer.assigned_to.user,
            title="Customer Needs Attention",
            message=f"{customer.company_name}'s engagement is declining (Health Score: {health_score}).",
            notification_type="other",
            event_datetime=timezone.now(),
            priority="medium",
            content_object=customer,
            action_url=f"/customers/{customer.id}/"
        )

    def _handle_healthy_customer(self, customer, health_score, factors):
        """Handle customers with high health scores (healthy)"""
        # For healthy customers, we might check if they're candidates for upselling
        active_subscriptions = ServiceSubscription.objects.filter(
            customer=customer,
            is_active=True
        )

        all_services_ids = set(ServiceSubscription.objects.values_list('service_id', flat=True))
        customer_service_ids = set(active_subscriptions.values_list('service_id', flat=True))

        potential_services = all_services_ids - customer_service_ids

        if potential_services and customer.assigned_to:
            # Create upsell opportunity task
            task = Task.objects.create(
                title=f"Upsell opportunity: {customer.company_name}",
                description=f"This customer has a strong health score of {health_score}. Consider recommending additional services to complement their current subscriptions.",
                due_date=timezone.now() + timedelta(days=14),
                priority="medium",
                status="pending",
                assigned_to=customer.assigned_to,
                created_by=customer.assigned_to,
                customer=customer
            )

    def process_service_subscription(self, subscription):
        """
        Process a new service subscription

        Args:
            subscription: The ServiceSubscription object
        """
        if not subscription.customer.assigned_to:
            return

        # Create onboarding task for the new service
        task = Task.objects.create(
            title=f"Service onboarding: {subscription.service.name} for {subscription.customer.company_name}",
            description=f"Complete the onboarding process for the new {subscription.service.name} service. Ensure the customer understands how to use it and who to contact for support.",
            due_date=timezone.now() + timedelta(days=2),
            priority="high",
            status="pending",
            assigned_to=subscription.customer.assigned_to,
            created_by=subscription.customer.assigned_to,
            customer=subscription.customer
        )

        # Send notification
        self.notification_service.create_notification(
            user=subscription.customer.assigned_to.user,
            title="New Service Subscription",
            message=f"{subscription.customer.company_name} has subscribed to {subscription.service.name}. Please complete onboarding.",
            notification_type="other",
            event_datetime=timezone.now(),
            priority="medium",
            content_object=subscription,
            action_url="#"  # Replace with proper URL
        )

    def handle_subscription_expiry(self, subscription, days_before_expiry=7):
        """
        Handle expiring subscriptions by creating renewal tasks

        Args:
            subscription: The ServiceSubscription object
            days_before_expiry: Days before expiry to start renewal process
        """
        if not subscription.end_date or not subscription.customer.assigned_to:
            return

        today = timezone.now().date()
        days_until_expiry = (subscription.end_date - today).days

        if days_until_expiry <= days_before_expiry:
            # Create renewal task
            task = Task.objects.create(
                title=f"Subscription renewal: {subscription.service.name} for {subscription.customer.company_name}",
                description=f"This {subscription.service.name} subscription expires on {subscription.end_date}. Contact the customer to discuss renewal options.",
                due_date=timezone.now() + timedelta(days=max(1, days_until_expiry - 5)),
                priority="high",
                status="pending",
                assigned_to=subscription.customer.assigned_to,
                created_by=subscription.customer.assigned_to,
                customer=subscription.customer
            )

            # Send notification
            self.notification_service.create_notification(
                user=subscription.customer.assigned_to.user,
                title="Subscription Expiring Soon",
                message=f"{subscription.customer.company_name}'s {subscription.service.name} subscription expires in {days_until_expiry} days.",
                notification_type="deadline",
                event_datetime=datetime.combine(subscription.end_date, datetime.min.time()),
                priority="medium" if days_until_expiry > 3 else "high",
                content_object=subscription,
                action_url="#"  # Replace with proper URL
            )

    def schedule_customer_checkup(self, days_interval=90):
        """
        Schedule regular check-ups for customers who haven't had recent interactions

        Args:
            days_interval: Minimum days between check-ups
        """
        today = timezone.now().date()
        threshold_date = timezone.now() - timedelta(days=days_interval)

        # Get active customers
        active_customers = Customer.objects.filter(status='active')

        for customer in active_customers:
            if not customer.assigned_to:
                continue

            # Check for recent substantial interaction (meeting or note)
            recent_meeting = Meeting.objects.filter(
                customers=customer,
                start_time__gt=threshold_date
            ).exists()

            recent_note = Note.objects.filter(
                customer=customer,
                created_at__gt=threshold_date
            ).exists()

            # Skip if recent substantial interaction
            if recent_meeting or recent_note:
                continue

            # Check if already has a pending check-up task
            existing_task = Task.objects.filter(
                customer=customer,
                title__icontains="Regular check-up",
                status__in=['pending', 'in_progress'],
                due_date__gte=today
            ).exists()

            if existing_task:
                continue

            # Create check-up task
            task = Task.objects.create(
                title=f"Regular check-up: {customer.company_name}",
                description=f"It's been {days_interval} days since the last substantial interaction with this customer. Schedule a call to check in, gather feedback, and ensure they're satisfied.",
                due_date=timezone.now() + timedelta(days=7),
                priority="medium",
                status="pending",
                assigned_to=customer.assigned_to,
                created_by=customer.assigned_to,
                customer=customer
            )

    def convert_lead_to_customer(self, lead, customer):
        """
        Handle the lead to customer conversion process

        Args:
            lead: The Lead object being converted
            customer: The newly created Customer object
        """
        # Start the customer lifecycle
        self.process_new_customer(customer)

        # Update the lead record
        lead.status = 'converted'
        lead.converted_to_customer = customer
        lead.conversion_date = timezone.now()
        lead.save()

        # Transfer any notes from lead to customer
        notes = Note.objects.filter(lead=lead)
        for note in notes:
            new_note = Note.objects.create(
                title=note.title,
                content=note.content,
                note_type=note.note_type,
                created_by=note.created_by,
                customer=customer,
                created_at=note.created_at
            )

        # Log the conversion
        logger.info(f"Lead {lead.company_name} converted to customer {customer.company_name}")
