# core/views.py
from .imports import *



class DashboardView(LoginRequiredMixin, EmployeeRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        try:
            # Basic dashboard data
            context.update({
                'total_customers': Customer.objects.filter(
                    assigned_to=self.employee
                ).count(),
                'total_leads': Lead.objects.filter(
                    assigned_to=self.employee
                ).count(),
                'upcoming_tasks': Task.objects.filter(
                    assigned_to=self.employee,
                    status__in=['pending', 'in_progress'],
                    due_date__gte=timezone.now()
                ).order_by('due_date')[:5],
                'upcoming_meetings': Meeting.objects.filter(
                    Q(organizer=self.employee) | Q(attendees=self.employee),
                    start_time__gte=timezone.now()
                ).order_by('start_time')[:5],
                'recent_notes': Note.objects.filter(
                    created_by=self.employee
                ).order_by('-created_at')[:5],
                'overdue_tasks': Task.objects.filter(
                    assigned_to=self.employee,
                    status__in=['pending', 'in_progress'],
                    due_date__lt=timezone.now()
                ).count(),
            })

            # Add smart notification data
            from .notification_service import SmartNotificationService
            notification_service = SmartNotificationService()

            # Get active and upcoming notifications
            active_notifications = notification_service.get_user_active_notifications(
                self.request.user, limit=10
            )

            upcoming_notifications = notification_service.get_user_upcoming_notifications(
                self.request.user, limit=10
            )

            context.update({
                'active_notifications': active_notifications,
                'upcoming_notifications': upcoming_notifications,
            })

            # Add smart scheduling suggestions
            try:
                from .scheduling_service import SchedulingService
                scheduling_service = SchedulingService(self.request.user)

                # Get today's availability
                availability = scheduling_service.get_availability(timezone.now().date())

                # Find next available slots
                available_slots = []
                for duration in [30, 60]:
                    next_start, next_end = scheduling_service.get_next_available_slot(
                        from_datetime=timezone.now(),
                        duration_minutes=duration
                    )

                    if next_start and next_end:
                        available_slots.append({
                            'duration': duration,
                            'start': next_start,
                            'end': next_end
                        })

                context['available_slots'] = available_slots
                context['availability'] = availability
            except Exception as e:
                logger.error(f"Error getting scheduling data: {str(e)}")

            # Add customer lifecycle data
            try:
                from .customer_lifecycle import CustomerLifecycleManager
                lifecycle_manager = CustomerLifecycleManager()

                # Get customers assigned to this employee
                assigned_customers = Customer.objects.filter(assigned_to=self.employee)

                # Get at-risk customers (health score < 50)
                at_risk_customers = []
                needs_attention_customers = []

                for customer in assigned_customers:
                    health_score, factors = lifecycle_manager._calculate_health_score(customer)

                    if health_score < 50:
                        at_risk_customers.append({
                            'customer': customer,
                            'health_score': health_score,
                            'factors': factors
                        })
                    elif health_score < 70:
                        needs_attention_customers.append({
                            'customer': customer,
                            'health_score': health_score,
                            'factors': factors
                        })

                context['at_risk_customers'] = at_risk_customers
                context['needs_attention_customers'] = needs_attention_customers
            except Exception as e:
                logger.error(f"Error getting customer lifecycle data: {str(e)}")

            # Add invoice data
            try:
                # Get pending invoices for assigned customers
                pending_invoices = Invoice.objects.filter(
                    customer__assigned_to=self.employee,
                    status__in=['pending', 'partial']
                ).order_by('due_date')

                context['pending_invoices'] = pending_invoices

                # Get overdue invoices
                overdue_invoices = Invoice.objects.filter(
                    customer__assigned_to=self.employee,
                    status='overdue'
                ).order_by('due_date')

                context['overdue_invoices'] = overdue_invoices

                # Get pending payments
                pending_payments = Payment.objects.filter(
                    customer__assigned_to=self.employee,
                    status='pending'
                ).order_by('-transaction_date')

                context['pending_payments'] = pending_payments
            except Exception as e:
                logger.error(f"Error getting invoice data: {str(e)}")

        except Exception as e:
            logger.error(f"Error getting dashboard data: {str(e)}")
            messages.error(self.request, 'Error loading dashboard data.')
            context.update({
                'total_customers': 0,
                'total_leads': 0,
                'upcoming_tasks': [],
                'upcoming_meetings': [],
                'recent_notes': [],
                'overdue_tasks': 0,
            })

        return context

# Employee Views
class EmployeeListView(LoginRequiredMixin, ListView):
    model = Employee
    template_name = 'core/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(employee_id__icontains=search_query) |
                Q(department__icontains=search_query)
            )
        return queryset.order_by('-created_at')

class EmployeeDetailView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = 'core/employee_detail.html'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object()
        context.update({
            'assigned_customers': Customer.objects.filter(assigned_to=employee),
            'assigned_leads': Lead.objects.filter(assigned_to=employee),
            'upcoming_meetings': Meeting.objects.filter(
                Q(organizer=employee) | Q(attendees=employee),
                start_time__gte=timezone.now()
            ).order_by('start_time'),
            'active_tasks': Task.objects.filter(
                assigned_to=employee,
                status__in=['pending', 'in_progress']
            ).order_by('due_date'),
        })
        return context

class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'core/employee_form.html'
    success_url = reverse_lazy('employee-list')

    def test_func(self):
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Employee created successfully.')
        return super().form_valid(form)

class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'core/employee_form.html'
    success_url = reverse_lazy('employee-list')

    def test_func(self):
        return self.request.user.is_superuser or self.get_object().user == self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Employee updated successfully.')
        return super().form_valid(form)

class EmployeeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Employee
    template_name = 'core/employee_confirm_delete.html'
    success_url = reverse_lazy('employee-list')

    def test_func(self):
        return self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Employee deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Authentication Views
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful. Please log in.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'core/register.html', {'form': form})

@login_required
def profile(request):
    employee = get_object_or_404(Employee, user=request.user)

    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = EmployeeForm(instance=employee)

    # Calculate Quick Stats
    total_customers = Customer.objects.filter(assigned_to=employee).count()
    active_tasks = Task.objects.filter(assigned_to=employee, status='in_progress').count()
    upcoming_meetings = Meeting.objects.filter(
        Q(organizer=employee) | Q(attendees=employee),
        start_time__gte=now()
    ).count()

    context = {
        'form': form,
        'employee': employee,
        'total_customers': total_customers,
        'active_tasks': active_tasks,
        'upcoming_meetings': upcoming_meetings
    }

    return render(request, 'core/profile.html', context)
@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'core/change_password.html', {'form': form})

# Continuing in core/views.py

# Customer Views
class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'core/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10

    def get_queryset(self):
        queryset = Customer.objects.all()
        search_query = self.request.GET.get('search')
        status_filter = self.request.GET.get('status')

        if search_query:
            queryset = queryset.filter(
                Q(company_name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(email__icontains=search_query)
            )

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Customer.CUSTOMER_STATUS
        return context

logger = logging.getLogger(__name__)
class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'core/customer_detail.html'
    context_object_name = 'customer'
    # Debug query for uninvoiced entries
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.get_object()

        # Get customer-specific events, tasks, and meetings
        context.update({
            'events': Event.objects.filter(customer=customer).order_by('-start_time')[:5],
            'tasks': Task.objects.filter(customer=customer).order_by('-created_at')[:5],
            'meetings': Meeting.objects.filter(customers=customer).order_by('-start_time')[:5],
            'projects': customer.projects.all().order_by('-created_at'),
            'invoices': Invoice.objects.filter(customer=customer),
            'payments': Payment.objects.filter(invoice__customer=customer),
            'total_paid': Payment.objects.filter(invoice__customer=customer).aggregate(total=models.Sum('amount'))['total'] or 0
        })

        # Add customer health score
        try:
            from .customer_lifecycle import CustomerLifecycleManager
            lifecycle_manager = CustomerLifecycleManager()

            # Calculate health score
            health_score, health_factors = lifecycle_manager._calculate_health_score(customer)
            context['health_score'] = health_score
            context['health_factors'] = health_factors

            # Add health status based on score
            if health_score >= 80:
                context['health_status'] = 'excellent'
                context['health_color'] = 'success'
            elif health_score >= 70:
                context['health_status'] = 'good'
                context['health_color'] = 'info'
            elif health_score >= 50:
                context['health_status'] = 'needs attention'
                context['health_color'] = 'warning'
            else:
                context['health_status'] = 'at risk'
                context['health_color'] = 'danger'

            # Get recent interactions
            from django.db.models import Max

            last_meeting = Meeting.objects.filter(customers=customer).aggregate(Max('start_time'))['start_time__max']
            last_note = Note.objects.filter(customer=customer).aggregate(Max('created_at'))['created_at__max']
            last_task = Task.objects.filter(customer=customer).aggregate(Max('updated_at'))['updated_at__max']

            latest_dates = [d for d in [last_meeting, last_note, last_task] if d is not None]
            if latest_dates:
                context['last_interaction'] = max(latest_dates)
                days_since = (timezone.now() - context['last_interaction']).days
                context['days_since_interaction'] = days_since

        except Exception as e:
            logger.error(f"Error calculating customer health: {str(e)}")

        # Get uninvoiced time entries data for API
        try:
            from customer_projects.models import TimeEntry
            from django.db.models import Sum, Count

            # Get details about uninvoiced entries for this customer's projects
            uninvoiced_data = TimeEntry.objects.filter(
                is_billable=True,
                is_invoiced=False,
                task__phase__project__customer=customer
            ).aggregate(
                count=Count('id'),
                total_hours=Sum('hours')
            )

            context['uninvoiced_entries_count'] = uninvoiced_data['count'] or 0
            context['uninvoiced_hours'] = uninvoiced_data['total_hours'] or 0
            context['has_uninvoiced_entries'] = uninvoiced_data['count'] > 0 if uninvoiced_data['count'] is not None else False

        except Exception as e:
            logger.error(f"Error getting uninvoiced time entries: {str(e)}")
            context['uninvoiced_entries_count'] = 0
            context['uninvoiced_hours'] = 0
            context['has_uninvoiced_entries'] = False

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests for customer actions"""
        customer = self.get_object()
        action = request.POST.get('action')

        if action == 'run_health_check':
            # Run health check on demand
            try:
                from .customer_lifecycle import CustomerLifecycleManager
                lifecycle_manager = CustomerLifecycleManager()

                lifecycle_manager.evaluate_customer_health(customer)
                messages.success(request, "Customer health evaluation completed successfully")
            except Exception as e:
                messages.error(request, f"Error running health check: {str(e)}")

        elif action == 'schedule_follow_up':
            # Schedule follow-up task
            try:
                from .customer_lifecycle import CustomerLifecycleManager
                lifecycle_manager = CustomerLifecycleManager()

                follow_up_days = int(request.POST.get('follow_up_days', 7))
                task = lifecycle_manager._create_followup_task(customer, days=follow_up_days)

                if task:
                    messages.success(request, f"Follow-up task scheduled for {task.due_date.strftime('%Y-%m-%d')}")
                else:
                    messages.warning(request, "Could not schedule follow-up task - customer may not have an assigned employee")

            except Exception as e:
                messages.error(request, f"Error scheduling follow-up: {str(e)}")

        elif action == 'generate_invoice':
            # Generate invoice for customer
            try:
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                # Find active subscriptions
                subscriptions = ServiceSubscription.objects.filter(
                    customer=customer,
                    is_active=True
                )

                if not subscriptions.exists():
                    messages.warning(request, "Customer has no active subscriptions to invoice")
                else:
                    # Create invoice for each subscription
                    invoices_created = 0
                    for subscription in subscriptions:
                        invoice = invoice_generator._generate_subscription_invoice(
                            subscription, timezone.now().date()
                        )
                        if invoice:
                            invoices_created += 1

                    if invoices_created > 0:
                        messages.success(request, f"Successfully generated {invoices_created} invoice(s)")
                    else:
                        messages.warning(request, "No invoices were generated - subscriptions may already be invoiced")

            except Exception as e:
                messages.error(request, f"Error generating invoice: {str(e)}")

        elif action == 'generate_project_invoices':
            # Generate invoices for uninvoiced time entries
            try:
                from .automation import automation_system

                # Add more logging for debugging
                logger.info(f"Starting invoice generation for customer {customer.pk}")

                # Call the invoice generation directly instead of using automation_system
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                # Direct call to generate project invoices
                invoices_created = invoice_generator.generate_project_invoices(timezone.now().date())

                if invoices_created > 0:
                    messages.success(request, f"Successfully generated {invoices_created} invoice(s) for pending time entries")
                else:
                    messages.warning(request, "No invoices were generated. This could be because there are no uninvoiced billable time entries, or they've already been processed.")

                logger.info(f"Invoice generation completed for customer {customer.pk}. Invoices created: {invoices_created}")

            except Exception as e:
                logger.exception(f"Error generating project invoices for customer {customer.pk}")
                messages.error(request, f"Error generating project invoices: {str(e)}")


        # Redirect back to customer detail page
        return redirect('customer-detail', pk=customer.pk)



class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'core/customer_form.html'
    success_url = reverse_lazy('customer-list')

    def form_valid(self, form):
        messages.success(self.request, 'Customer created successfully.')
        return super().form_valid(form)

class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'core/customer_form.html'
    success_url = reverse_lazy('customer-list')

    def form_valid(self, form):
        messages.success(self.request, 'Customer updated successfully.')
        return super().form_valid(form)

class CustomerDeleteView(LoginRequiredMixin, DeleteView):
    model = Customer
    template_name = 'core/customer_confirm_delete.html'
    success_url = reverse_lazy('customer-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Customer deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Lead Views
class LeadListView(LoginRequiredMixin, ListView):
    model = Lead
    template_name = 'core/lead_list.html'
    context_object_name = 'leads'
    paginate_by = 10

    def get_queryset(self):
        queryset = Lead.objects.all()
        search_query = self.request.GET.get('search')
        status_filter = self.request.GET.get('status')
        source_filter = self.request.GET.get('source')

        if search_query:
            queryset = queryset.filter(
                Q(company_name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(email__icontains=search_query)
            )

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if source_filter:
            queryset = queryset.filter(source=source_filter)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'status_choices': Lead.LEAD_STATUS,
            'source_choices': Lead.LEAD_SOURCE
        })
        return context

class LeadDetailView(LoginRequiredMixin, DetailView):
    model = Lead
    template_name = 'core/lead_detail.html'
    context_object_name = 'lead'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lead = self.get_object()
        context.update({
            'notes': Note.objects.filter(lead=lead).order_by('-created_at'),
            'tasks': Task.objects.filter(lead=lead).order_by('-created_at'),
            'meetings': Meeting.objects.filter(leads=lead).order_by('-start_time'),
        })
        return context

class LeadCreateView(LoginRequiredMixin, CreateView):
    model = Lead
    form_class = LeadForm
    template_name = 'core/lead_form.html'
    success_url = reverse_lazy('lead-list')

    def form_valid(self, form):
        messages.success(self.request, 'Lead created successfully.')
        return super().form_valid(form)

class LeadUpdateView(LoginRequiredMixin, UpdateView):
    model = Lead
    form_class = LeadForm
    template_name = 'core/lead_form.html'
    success_url = reverse_lazy('lead-list')

    def form_valid(self, form):
        messages.success(self.request, 'Lead updated successfully.')
        return super().form_valid(form)

class LeadDeleteView(LoginRequiredMixin, DeleteView):
    model = Lead
    template_name = 'core/lead_confirm_delete.html'
    success_url = reverse_lazy('lead-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Lead deleted successfully.')
        return super().delete(request, *args, **kwargs)

@login_required
def convert_lead_to_customer(request, pk):
    lead = get_object_or_404(Lead, pk=pk)

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Create customer record
                customer = form.save(commit=False)
                customer.company_name = lead.company_name
                customer.contact_person = lead.contact_person
                customer.email = lead.email
                customer.phone = lead.phone
                customer.assigned_to = lead.assigned_to
                customer.save()

                # Copy notes from lead to customer
                for note in Note.objects.filter(lead=lead):
                    note.pk = None  # Create a new note
                    note.lead = None
                    note.customer = customer
                    note.save()

                # Update lead status
                lead.status = 'converted'
                lead.converted_to_customer = customer
                lead.conversion_date = timezone.now()
                lead.save()

                # Use customer lifecycle automation
                try:
                    # Import the customer lifecycle manager
                    from .customer_lifecycle import CustomerLifecycleManager
                    lifecycle_manager = CustomerLifecycleManager()

                    # Process the new customer with automation
                    lifecycle_manager.convert_lead_to_customer(lead, customer)

                    # Log the conversion
                    logger.info(f"Lead {lead.id} converted to customer {customer.id} with lifecycle automation")

                except Exception as e:
                    # If lifecycle automation fails, still proceed but log the error
                    logger.error(f"Error in customer lifecycle automation: {str(e)}")

                    # Create basic onboarding tasks manually as fallback
                    if customer.assigned_to:
                        # Create welcome email task
                        Task.objects.create(
                            title=f"Send welcome email to {customer.company_name}",
                            description=f"Send a personalized welcome email to {customer.contact_person} at {customer.email}.",
                            due_date=timezone.now() + timedelta(days=1),
                            priority="high",
                            status="pending",
                            assigned_to=customer.assigned_to,
                            created_by=customer.assigned_to,
                            customer=customer
                        )

                        # Create initial meeting task
                        Task.objects.create(
                            title=f"Schedule kickoff meeting with {customer.company_name}",
                            description=f"Schedule an initial meeting to discuss their specific needs.",
                            due_date=timezone.now() + timedelta(days=3),
                            priority="medium",
                            status="pending",
                            assigned_to=customer.assigned_to,
                            created_by=customer.assigned_to,
                            customer=customer
                        )

                messages.success(request, 'Lead successfully converted to customer.')
                return redirect('customer-detail', pk=customer.pk)
    else:
        # Populate form with lead data
        form = CustomerForm(initial={
            'company_name': lead.company_name,
            'contact_person': lead.contact_person,
            'email': lead.email,
            'phone': lead.phone,
            'assigned_to': lead.assigned_to
        })

    return render(request, 'core/lead_to_customer.html', {
        'form': form,
        'lead': lead
    })

# Service Views
class ServiceListView(LoginRequiredMixin, ListView):
    model = Service
    template_name = 'core/service_list.html'
    context_object_name = 'services'
    paginate_by = 10

    def get_queryset(self):
        queryset = Service.objects.all()
        search_query = self.request.GET.get('search')

        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset.order_by('-created_at')

class ServiceDetailView(LoginRequiredMixin, DetailView):
    model = Service
    template_name = 'core/service_detail.html'
    context_object_name = 'service'

class ServiceCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Service
    form_class = ServiceForm
    template_name = 'core/service_form.html'
    success_url = reverse_lazy('service-list')

    def test_func(self):
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Service created successfully.')
        return super().form_valid(form)

class ServiceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Service
    form_class = ServiceForm
    template_name = 'core/service_form.html'
    success_url = reverse_lazy('service-list')

    def test_func(self):
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Service updated successfully.')
        return super().form_valid(form)

class ServiceDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Service
    template_name = 'core/service_confirm_delete.html'
    success_url = reverse_lazy('service-list')

    def test_func(self):
        return self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Service deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Continuing in core/views.py

# Note Views
class NoteListView(LoginRequiredMixin, ListView):
    model = Note
    template_name = 'core/note_list.html'
    context_object_name = 'notes'
    paginate_by = 10

    def get_queryset(self):
        queryset = Note.objects.all()
        search_query = self.request.GET.get('search')
        note_type = self.request.GET.get('note_type')

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(content__icontains=search_query)
            )

        if note_type:
            queryset = queryset.filter(note_type=note_type)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['note_types'] = Note.NOTE_TYPES
        return context

class NoteDetailView(LoginRequiredMixin, DetailView):
    model = Note
    template_name = 'core/note_detail.html'
    context_object_name = 'note'

class NoteCreateView(LoginRequiredMixin, CreateView):
    model = Note
    form_class = NoteForm
    template_name = 'core/note_form.html'
    success_url = reverse_lazy('note-list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user.employee_profile
        messages.success(self.request, 'Note created successfully.')
        return super().form_valid(form)

class NoteUpdateView(LoginRequiredMixin, UpdateView):
    model = Note
    form_class = NoteForm
    template_name = 'core/note_form.html'
    success_url = reverse_lazy('note-list')

    def form_valid(self, form):
        messages.success(self.request, 'Note updated successfully.')
        return super().form_valid(form)

class NoteDeleteView(LoginRequiredMixin, DeleteView):
    model = Note
    template_name = 'core/note_confirm_delete.html'
    success_url = reverse_lazy('note-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Note deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Task Views
class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 10

    def get_queryset(self):
        """Return all tasks with option to filter by current user"""
        # Check if user wants to see only their tasks
        show_my_tasks = self.request.GET.get('my_tasks') == 'true'

        if show_my_tasks and hasattr(self.request.user, 'employee_profile'):
            # Show only user's tasks
            employee = self.request.user.employee_profile
            queryset = Task.objects.filter(
                Q(assigned_to=employee) | Q(created_by=employee)
            )
        else:
            # Show all tasks
            queryset = Task.objects.all()

        # Apply other filters
        search_query = self.request.GET.get('search')
        status = self.request.GET.get('status')
        priority = self.request.GET.get('priority')
        due_date = self.request.GET.get('due_date')

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if status:
            queryset = queryset.filter(status=status)

        if priority:
            queryset = queryset.filter(priority=priority)

        if due_date:
            queryset = queryset.filter(due_date__date=due_date)

        return queryset.order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add show_my_tasks parameter to context to maintain state in the template
        context['show_my_tasks'] = self.request.GET.get('my_tasks') == 'true'

        context.update({
            'status_choices': Task.STATUS_CHOICES,
            'priority_choices': Task.PRIORITY_CHOICES,
            'search_form': TaskSearchForm(self.request.GET)
        })
        return context

class TaskDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view that handles both regular Tasks and ProjectTasks
    """
    template_name = 'core/task_detail.html'
    context_object_name = 'task'

    def get_object(self, queryset=None):
        """
        Retrieve either a Task or ProjectTask based on the provided ID
        """
        pk = self.kwargs.get('pk')
        employee = self.request.user.employee_profile

        # First try to get it as a ProjectTask
        try:
            project_task = ProjectTask.objects.filter(
                Q(phase__project__project_manager=employee) |
                Q(phase__project__team_members=employee) |
                Q(assigned_to=employee)
            ).get(pk=pk)
            return project_task
        except ProjectTask.DoesNotExist:
            # If not found, try as a regular Task
            try:
                regular_task = Task.objects.filter(
                    Q(assigned_to=employee) | Q(created_by=employee)
                ).get(pk=pk)
                return regular_task
            except Task.DoesNotExist:
                # If neither exists, raise 404
                raise Http404("No task found matching the query")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.get_object()

        # Add task-type specific context
        if isinstance(task, ProjectTask):
            # For project tasks, add project and phase information
            context.update({
                'is_project_task': True,
                'project': task.phase.project,
                'phase': task.phase,
                'time_entries': TimeEntry.objects.filter(task=task),
                'comments': ProjectComment.objects.filter(
                    content_type__model='projecttask',
                    object_id=task.id
                ).select_related('author', 'author__user')
            })
        else:
            # For regular tasks, add related data
            context.update({
                'is_project_task': False,
                'customer': task.customer,  # If your Task model has a customer field
                'related_notes': Note.objects.filter(task=task).order_by('-created_at') if hasattr(task, 'notes') else []
            })

        # Add common context used for both task types
        context['can_edit'] = (
            (isinstance(task, ProjectTask) and
             (task.phase.project.project_manager == self.request.user.employee_profile or
              self.request.user.employee_profile in task.phase.project.team_members.all())) or
            (isinstance(task, Task) and
             (task.assigned_to == self.request.user.employee_profile or
              task.created_by == self.request.user.employee_profile))
        )

        return context

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('task-list')

    def get_initial(self):
        """Set initial values for the form"""
        initial = super().get_initial()

        # Set due date based on scheduling availability
        try:
            from .scheduling_service import SchedulingService
            scheduling_service = SchedulingService(self.request.user)

            # Find next available slot for a task (30 minutes)
            next_start, next_end = scheduling_service.get_next_available_slot(
                from_datetime=timezone.now(),
                duration_minutes=30
            )

            if next_start:
                initial['due_date'] = next_start
        except Exception as e:
            logger.error(f"Error getting scheduling data: {str(e)}")
            # Default to tomorrow at 9 AM if scheduling fails
            tomorrow = timezone.now() + timedelta(days=1)
            initial['due_date'] = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        # Set assigned to as current user's employee profile
        try:
            initial['assigned_to'] = self.request.user.employee_profile
        except Exception:
            pass

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add scheduling availability data
        try:
            from .scheduling_service import SchedulingService
            scheduling_service = SchedulingService(self.request.user)

            # Get availability for next 7 days
            availability_data = {}
            today = timezone.now().date()
            for i in range(7):
                day = today + timedelta(days=i)
                availability_data[day.strftime('%Y-%m-%d')] = scheduling_service.get_availability(day)

            context['availability_data'] = availability_data
        except Exception as e:
            logger.error(f"Error getting scheduling data: {str(e)}")

        return context

    def form_valid(self, form):
        try:
            employee = self.request.user.employee_profile
        except AttributeError:
            messages.error(self.request, "You must have an employee profile to create tasks.")
            return self.form_invalid(form)

        # Get task details
        due_date = form.cleaned_data.get('due_date')

        try:
            # Validate scheduling with scheduling service
            from .scheduling_service import SchedulingService
            scheduling_service = SchedulingService(self.request.user)

            # Check a small duration (30 minutes) for task slot
            if due_date:
                end_time = due_date + timedelta(minutes=30)
                duration = 30

                # Check availability based on scheduling rules
                is_available = scheduling_service.check_availability(
                    due_date,
                    end_time,
                    duration
                )

                if not is_available:
                    # Try to find next available slot
                    next_start, next_end = scheduling_service.get_next_available_slot(
                        due_date,
                        duration
                    )

                    if next_start and next_end:
                        messages.error(self.request,
                            f"The selected time is not available according to your scheduling rules. "
                            f"Next available slot is {next_start.strftime('%Y-%m-%d %H:%M')} "
                            f"to {next_end.strftime('%Y-%m-%d %H:%M')}"
                        )
                    else:
                        messages.error(self.request, "No available time slots found based on your scheduling rules.")

                    return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error checking scheduling availability: {str(e)}")
            # Continue even if scheduling validation fails

        # Set the created_by and assigned_to
        form.instance.created_by = employee
        if not form.instance.assigned_to:
            form.instance.assigned_to = employee

        try:
            # Save the task
            response = super().form_valid(form)

            # Create notification
            from .notification_service import SmartNotificationService
            notification_service = SmartNotificationService()
            notification_service.create_task_notification(self.object)

            messages.success(self.request, 'Task created successfully.')
            return response
        except Exception as e:
            logger.error(f"Unexpected error in task creation: {str(e)}")
            messages.error(self.request, f'An unexpected error occurred: {str(e)}')
            return self.form_invalid(form)

class TaskUpdateView(LoginRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('task-list')

    def form_valid(self, form):
        messages.success(self.request, 'Task updated successfully.')
        return super().form_valid(form)

class TaskDeleteView(LoginRequiredMixin, DeleteView):
    model = Task
    template_name = 'core/task_confirm_delete.html'
    success_url = reverse_lazy('task-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Task deleted successfully.')
        return super().delete(request, *args, **kwargs)

@login_required
def task_status_update(request, pk):
    if request.method == 'POST' and request.is_ajax():
        task = get_object_or_404(Task, pk=pk)
        new_status = request.POST.get('status')

        if new_status in dict(Task.STATUS_CHOICES):
            task.status = new_status
            task.save()
            return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

# Meeting Views
class MeetingListView(LoginRequiredMixin, ListView):
    model = Meeting
    template_name = 'core/meeting_list.html'
    context_object_name = 'meetings'
    paginate_by = 10

    def get_queryset(self):
        employee = self.request.user.employee_profile
        queryset = Meeting.objects.filter(
            Q(organizer=employee) |
            Q(attendees=employee)
        ).distinct()

        search_query = self.request.GET.get('search')
        meeting_type = self.request.GET.get('meeting_type')
        date = self.request.GET.get('date')

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        if meeting_type:
            queryset = queryset.filter(meeting_type=meeting_type)

        if date:
            queryset = queryset.filter(start_time__date=date)

        return queryset.order_by('start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'meeting_types': Meeting.MEETING_TYPES,
            'search_form': MeetingSearchForm(self.request.GET)
        })
        return context

class MeetingDetailView(LoginRequiredMixin, DetailView):
    model = Meeting
    template_name = 'core/meeting_detail.html'
    context_object_name = 'meeting'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meeting = self.get_object()
        context['notes'] = Note.objects.filter(
            note_type='meeting',
            created_at__range=(meeting.start_time, meeting.end_time)
        )
        return context


logger = logging.getLogger(__name__)

class MeetingCreateView(LoginRequiredMixin, CreateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'core/meeting_form.html'
    success_url = reverse_lazy('meeting-list')

    def get_initial(self):
        """Set initial values for the form"""
        initial = super().get_initial()
        try:
            employee = Employee.objects.get(user=self.request.user)
            initial['organizer'] = employee

            # Ensure we're using timezone-aware datetime
            current_time = timezone.now()

            # Round minutes to nearest 15
            initial['start_time'] = current_time.replace(
                minute=(current_time.minute // 15) * 15,
                second=0,
                microsecond=0
            )
            initial['end_time'] = initial['start_time'] + timezone.timedelta(hours=1)

            # Log initial times for debugging
            logger.debug(f"Initial start time: {initial['start_time']}, Initial end time: {initial['end_time']}")

            # Check for suggested attendees in request
            attendee_ids = self.request.GET.getlist('attendees')
            if attendee_ids:
                # Use scheduling service to suggest optimal meeting time
                from .scheduling_service import SchedulingService
                scheduling_service = SchedulingService(self.request.user)

                # Get attendees as Employee objects
                attendees = Employee.objects.filter(id__in=attendee_ids)

                # Get suggestion for next 7 days
                suggestion = scheduling_service.suggest_meeting_time(
                    participants=list(attendees) + [employee],
                    duration_minutes=60,
                    within_days=7
                )

                # Use suggested time if available
                if suggestion.get('success'):
                    initial['start_time'] = suggestion['start_datetime']
                    initial['end_time'] = suggestion['end_datetime']
                    # Store attendees for the form
                    initial['attendees'] = attendees

        except Employee.DoesNotExist:
            logger.error(f"Employee profile not found for user {self.request.user.id}")
        except Exception as e:
            logger.error(f"Error setting initial meeting values: {str(e)}")
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'initial' not in kwargs:
            kwargs['initial'] = {}
        try:
            kwargs['initial']['organizer'] = self.request.user.employee_profile
        except Employee.DoesNotExist:
            logger.error(f"Employee profile not found for user {self.request.user.id}")
        return kwargs

    def get_context_data(self, **kwargs):
        """Add availability data to context"""
        context = super().get_context_data(**kwargs)

        try:
            # Add scheduling availability data
            from .scheduling_service import SchedulingService
            scheduling_service = SchedulingService(self.request.user)

            # Get availability for next 7 days
            availability_data = {}
            today = timezone.now().date()
            for i in range(7):
                day = today + timezone.timedelta(days=i)
                availability_data[day.strftime('%Y-%m-%d')] = scheduling_service.get_availability(day)

            context['availability_data'] = availability_data
            context['suggested_times'] = self._get_suggested_meeting_times(scheduling_service)

        except Exception as e:
            logger.error(f"Error getting scheduling data: {str(e)}")

        return context

    def _get_suggested_meeting_times(self, scheduling_service):
        """Get a list of suggested meeting times"""
        suggested_times = []

        try:
            for duration in [30, 60]:
                # Get next available slot
                start, end = scheduling_service.get_next_available_slot(
                    from_datetime=timezone.now(),
                    duration_minutes=duration
                )

                if start and end:
                    suggested_times.append({
                        'duration': duration,
                        'start': start,
                        'end': end,
                        'label': f"{duration} min meeting at {start.strftime('%I:%M %p')} on {start.strftime('%b %d')}"
                    })
        except Exception as e:
            logger.error(f"Error generating suggested times: {str(e)}")

        return suggested_times

    def form_valid(self, form):
        try:
            employee = Employee.objects.get(user=self.request.user)

            with transaction.atomic():
                form.instance.organizer = employee

                # Ensure datetime objects are timezone-aware
                start_time = form.cleaned_data['start_time']
                end_time = form.cleaned_data['end_time']

                if not timezone.is_aware(start_time):
                    start_time = timezone.make_aware(start_time)
                    form.instance.start_time = start_time

                if not timezone.is_aware(end_time):
                    end_time = timezone.make_aware(end_time)
                    form.instance.end_time = end_time

                # Log actual times being saved
                logger.debug(f"Saving meeting with start time: {start_time}, end time: {end_time}")

                # Use the scheduling service to check availability
                from .scheduling_service import SchedulingService
                scheduling_service = SchedulingService(self.request.user)

                duration = (end_time - start_time).total_seconds() / 60

                is_available = scheduling_service.check_availability(
                    start_time,
                    end_time,
                    duration
                )

                if not is_available:
                    # Try to find an alternative time slot
                    next_start, next_end = scheduling_service.get_next_available_slot(
                        from_datetime=start_time,
                        duration_minutes=int(duration)
                    )

                    if next_start and next_end:
                        form.add_error(None,
                            f"Selected time slot is not available. Suggested alternative: "
                            f"{next_start.strftime('%Y-%m-%d %H:%M')} to {next_end.strftime('%H:%M')}"
                        )
                    else:
                        form.add_error(None, "Selected time slot is not available")
                    return self.form_invalid(form)

                # Set status based on meeting time relative to now
                now = timezone.now()
                if start_time > now:
                    form.instance.status = 'scheduled'
                else:
                    form.instance.status = 'in_progress'

                response = super().form_valid(form)

                if form.instance.meeting_type == 'zoom':
                    try:
                        form.instance.create_zoom_meeting()
                    except Exception as e:
                        logger.error(f"Failed to create Zoom meeting: {str(e)}")
                        messages.warning(
                            self.request,
                            "Meeting scheduled, but Zoom meeting creation failed. "
                            "Please set up the Zoom meeting manually."
                        )

                messages.success(
                    self.request,
                    f"Meeting '{form.instance.title}' scheduled successfully"
                )

                # Create notifications for attendees
                from .notification_service import SmartNotificationService
                notification_service = SmartNotificationService()
                notification_service.create_meeting_notification(form.instance)

                return response

        except Employee.DoesNotExist:
            form.add_error(None, "Employee profile not found")
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error creating meeting: {str(e)}")
            form.add_error(None, "An error occurred while scheduling the meeting")
            return self.form_invalid(form)

    def get_success_url(self):
        if 'create_another' in self.request.POST:
            return reverse_lazy('meeting-create')
        return self.success_url


class MeetingUpdateView(LoginRequiredMixin, UpdateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'core/meeting_form.html'
    success_url = reverse_lazy('meeting-list')

    def form_valid(self, form):
        # Ensure user has an employee profile
        try:
            employee = self.request.user.employee_profile
        except AttributeError:
            messages.error(self.request, "You must have an employee profile to update meetings.")
            return self.form_invalid(form)

        # Get start and end times from the form and ensure they're timezone-aware
        start_time = form.cleaned_data.get('start_time')
        end_time = form.cleaned_data.get('end_time')

        if not timezone.is_aware(start_time):
            start_time = timezone.make_aware(start_time)
            form.instance.start_time = start_time

        if not timezone.is_aware(end_time):
            end_time = timezone.make_aware(end_time)
            form.instance.end_time = end_time

        # Log times for debugging
        logger.debug(f"Updating meeting with start: {start_time}, end: {end_time}")
        logger.debug(f"Current time: {timezone.now()}")

        # Create scheduling service for the current user
        scheduling_service = SchedulingService(self.request.user)

        # Calculate meeting duration in minutes
        duration = int((end_time - start_time).total_seconds() / 60)

        # Check availability based on scheduling rules
        # Exclude the current meeting from availability check
        if not scheduling_service.check_availability(start_time, end_time, duration, exclude_meeting_id=self.object.id):
            # If not available, find the next available slot
            next_start, next_end = scheduling_service.get_next_available_slot(
                start_time,
                duration
            )

            if next_start and next_end:
                messages.error(self.request,
                    f"The selected time is not available. "
                    f"Next available slot is {next_start.strftime('%Y-%m-%d %H:%M')} "
                    f"to {next_end.strftime('%Y-%m-%d %H:%M')}"
                )
                return self.form_invalid(form)
            else:
                messages.error(self.request, "No available time slots found.")
                return self.form_invalid(form)

        # Update status based on meeting time relative to now
        now = timezone.now()
        if start_time > now:
            form.instance.status = 'scheduled'
        elif start_time <= now and end_time > now:
            form.instance.status = 'in_progress'
        else:
            form.instance.status = 'completed'

        # Store the previous meeting type
        previous_type = self.get_object().meeting_type

        # Save the meeting
        response = super().form_valid(form)

        # Handle Zoom meeting creation/update
        if form.instance.meeting_type == 'zoom':
            try:
                if previous_type != 'zoom':
                    # Create new Zoom meeting
                    zoom_meeting = create_zoom_meeting(form.instance)
                    form.instance.zoom_meeting_id = zoom_meeting['id']
                    form.instance.zoom_join_url = zoom_meeting['join_url']
                else:
                    # Update existing Zoom meeting
                    update_zoom_meeting(form.instance)

                form.instance.save()
            except Exception as e:
                logger.error(f"Zoom meeting error: {str(e)}")
                messages.error(self.request, f'Error with Zoom meeting: {str(e)}')
                return self.form_invalid(form)

        messages.success(self.request, 'Meeting updated successfully.')
        return response

class MeetingDeleteView(LoginRequiredMixin, DeleteView):
    model = Meeting
    template_name = 'core/meeting_confirm_delete.html'
    success_url = reverse_lazy('meeting-list')

    def delete(self, request, *args, **kwargs):
        meeting = self.get_object()

        # Ensure the user has permission to delete
        if meeting.organizer.user != request.user:
            messages.error(request, 'You do not have permission to delete this meeting.')
            return redirect('meeting-detail', pk=meeting.pk)

        # Handle Zoom meeting deletion
        if meeting.meeting_type == 'zoom' and meeting.zoom_meeting_id:
            try:
                delete_zoom_meeting(meeting.zoom_meeting_id)
            except Exception as e:
                logger.error(f"Zoom meeting deletion error: {str(e)}")
                messages.error(request, f'Error deleting Zoom meeting: {str(e)}')
                return redirect('meeting-detail', pk=meeting.pk)

        messages.success(request, 'Meeting deleted successfully.')
        return super().delete(request, *args, **kwargs)


class MeetingUpdateView(LoginRequiredMixin, UpdateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'core/meeting_form.html'
    success_url = reverse_lazy('meeting-list')

    def form_valid(self, form):
        previous_type = self.get_object().meeting_type
        response = super().form_valid(form)

        if form.instance.meeting_type == 'zoom':
            if previous_type != 'zoom':
                # Create new Zoom meeting
                try:
                    zoom_meeting = create_zoom_meeting(form.instance)
                    form.instance.zoom_meeting_id = zoom_meeting['id']
                    form.instance.zoom_join_url = zoom_meeting['join_url']
                    form.instance.save()
                except Exception as e:
                    messages.error(self.request, f'Error creating Zoom meeting: {str(e)}')
                    return self.form_invalid(form)
            else:
                # Update existing Zoom meeting
                try:
                    update_zoom_meeting(form.instance)
                except Exception as e:
                    messages.error(self.request, f'Error updating Zoom meeting: {str(e)}')
                    return self.form_invalid(form)

        messages.success(self.request, 'Meeting updated successfully.')
        return response

class MeetingDeleteView(LoginRequiredMixin, DeleteView):
    model = Meeting
    template_name = 'core/meeting_confirm_delete.html'
    success_url = reverse_lazy('meeting-list')

    def delete(self, request, *args, **kwargs):
        meeting = self.get_object()
        if meeting.meeting_type == 'zoom' and meeting.zoom_meeting_id:
            try:
                delete_zoom_meeting(meeting.zoom_meeting_id)
            except Exception as e:
                messages.error(request, f'Error deleting Zoom meeting: {str(e)}')
                return redirect('meeting-detail', pk=meeting.pk)

        messages.success(request, 'Meeting deleted successfully.')
        return super().delete(request, *args, **kwargs)


logger = logging.getLogger(__name__)

class CalendarView(LoginRequiredMixin, EmployeeRequiredMixin, TemplateView):
    """
    Calendar view with employee selection capability
    """
    template_name = 'core/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get current employee from the mixin
            current_employee = self.employee

            # Get active employees excluding the current one
            available_employees = Employee.objects.exclude(
                id=current_employee.id
            ).filter(
                is_active=True
            ).select_related('user')  # Optimize query with select_related

            # Get schedule rule information
            schedule_rules = ScheduleRule.objects.filter(
                user=self.request.user,
                is_active=True
            )

            # Format rule information for display
            rule_info = []
            for rule in schedule_rules:
                rule_info.append({
                    'name': rule.name,
                    'recurrence': rule.get_recurrence_type_display(),
                    'time_range': f"{rule.start_time.strftime('%I:%M %p')} - {rule.end_time.strftime('%I:%M %p')}",
                    'day_info': self._get_rule_day_info(rule),
                    'buffer': f"{rule.buffer_before} min before, {rule.buffer_after} min after"
                })

            # Add scheduling service data if available
            try:
                from .scheduling_service import SchedulingService
                scheduling_service = SchedulingService(self.request.user)

                # Get availability for today
                today = timezone.now().date()
                availability_data = {
                    'today': scheduling_service.get_availability(today)
                }

                # Get suggested meeting slots
                available_slots = []
                for duration in [30, 60]:
                    next_start, next_end = scheduling_service.get_next_available_slot(
                        from_datetime=timezone.now(),
                        duration_minutes=duration
                    )

                    if next_start and next_end:
                        available_slots.append({
                            'duration': duration,
                            'start': next_start,
                            'end': next_end,
                            'label': f"{duration} min at {next_start.strftime('%I:%M %p')} on {next_start.strftime('%b %d')}"
                        })

                context['availability_data'] = availability_data
                context['available_slots'] = available_slots

            except Exception as e:
                logger.error(f"Error getting scheduling data: {str(e)}")

            # Add to context with other required data
            context.update({
                'current_employee': current_employee,
                'available_employees': available_employees,
                'employee_count': available_employees.count(),
                'schedule_rules': rule_info,
                'today': timezone.now().date(),
            })

        except Exception as e:
            logger.error(f"Error getting calendar data: {str(e)}")
            messages.error(self.request, 'Error loading calendar data.')
            context.update({
                'current_employee': None,
                'available_employees': [],
                'employee_count': 0,
                'schedule_rules': [],
                'today': timezone.now().date(),
                'error_message': str(e)
            })

        return context

    def _get_rule_day_info(self, rule):
        """Format day information for a schedule rule"""
        if rule.recurrence_type == 'daily':
            return "Every day"
        elif rule.recurrence_type == 'weekly':
            return f"Every {rule.get_day_of_week_display()}"
        elif rule.recurrence_type == 'monthly':
            return f"Day {rule.day_of_month} of each month"
        elif rule.recurrence_type == 'yearly':
            return f"{rule.get_month_display()} {rule.day_of_month}"
        return ""

# Function-based view alternative
def calendar_view(request):
    """Function-based alternative to the CalendarView class."""
    today = timezone.now().date()

    try:
        # Get all other active employees (not the current user)
        available_employees = Employee.objects.filter(
            is_active=True,
            user__is_active=True
        ).exclude(user=request.user).select_related('user')

        # Create the form with initial value
        form = EmployeeUsernameForm(initial={'employees': available_employees.first() if available_employees else None})

        # Get schedule rule information
        schedule_rules = ScheduleRule.objects.filter(
            user=request.user,
            is_active=True
        )

        # Format rule information for display
        rule_info = []
        for rule in schedule_rules:
            # Helper function to get day info
            def get_rule_day_info(rule):
                if rule.recurrence_type == 'daily':
                    return "Every day"
                elif rule.recurrence_type == 'weekly':
                    return f"Every {rule.get_day_of_week_display()}"
                elif rule.recurrence_type == 'monthly':
                    return f"Day {rule.day_of_month} of each month"
                elif rule.recurrence_type == 'yearly':
                    return f"{rule.get_month_display()} {rule.day_of_month}"
                return ""

            rule_info.append({
                'name': rule.name,
                'recurrence': rule.get_recurrence_type_display(),
                'time_range': f"{rule.start_time.strftime('%I:%M %p')} - {rule.end_time.strftime('%I:%M %p')}",
                'day_info': get_rule_day_info(rule),
                'duration_limits': f"{rule.min_booking_duration}-{rule.max_booking_duration} minutes",
                'buffer': f"{rule.buffer_before} min before, {rule.buffer_after} min after"
            })

        context = {
            'form': form,
            'available_employees': available_employees,
            'schedule_rules': rule_info,
            'events': [],  # These would be populated from your actual queries
            'tasks': [],
            'meetings': [],
            'today': today,
            'is_personal_calendar': True,
        }

    except Exception as e:
        logger.error(f"Error getting calendar data: {str(e)}")
        messages.error(request, 'Error loading calendar data.')
        context = {
            'form': EmployeeUsernameForm(),  # Empty form in case of error
            'available_employees': [],
            'events': [],
            'tasks': [],
            'meetings': [],
            'today': today,
            'is_personal_calendar': True,
        }

    return render(request, 'core/calendar.html', context)

@login_required
def user_calendar_events(request):
    """API endpoint to get calendar events for the current user"""
    try:
        employee = request.user.employee_profile
        events = []

        # 1. Fetch date range
        start_date = request.GET.get('start')
        end_date = request.GET.get('end')
        # Date range processing
        if start_date and end_date:
            start_date = datetime.fromisoformat(start_date.rstrip('Z'))
            end_date = datetime.fromisoformat(end_date.rstrip('Z'))
            start_date = timezone.make_aware(start_date)
            end_date = timezone.make_aware(end_date)
        else:
            today = timezone.now()
            start_date = today.replace(day=1, hour=0, minute=0, second=0)
            next_month = today.month + 1 if today.month < 12 else 1
            next_month_year = today.year if today.month < 12 else today.year + 1
            end_date = today.replace(year=next_month_year, month=next_month, day=1, hour=23, minute=59, second=59)

        # 2. Fetch application events (tasks, meetings, events)
        tasks = Task.objects.filter(
            Q(assigned_to=employee) | Q(created_by=employee),
            due_date__range=(start_date, end_date)
        ).select_related('assigned_to', 'assigned_to__user')

        for task in tasks:
            events.append({
                'id': f'task_{task.id}',
                'title': task.title,
                'start': task.due_date.isoformat(),
                'end': (task.due_date + timedelta(hours=1)).isoformat(),
                'backgroundColor': '#f6c23e',
                'borderColor': '#f6c23e',
                'textColor': '#000000',
                'url': f'/tasks/{task.id}/',
                'extendedProps': {
                    'type': 'task',
                    'status': task.get_status_display(),
                    'priority': task.get_priority_display(),
                    'assigned_to': task.assigned_to.user.get_full_name() if task.assigned_to else 'Unassigned'
                }
            })

        meetings = Meeting.objects.filter(
            Q(organizer=employee) | Q(attendees=employee),
            start_time__range=(start_date, end_date)
        ).distinct().select_related('organizer', 'organizer__user')

        for meeting in meetings:
            events.append({
                'id': f'meeting_{meeting.id}',
                'title': meeting.title,
                'start': meeting.start_time.isoformat(),
                'end': meeting.end_time.isoformat(),
                'backgroundColor': '#e74a3b',
                'borderColor': '#e74a3b',
                'textColor': '#ffffff',
                'url': f'/meetings/{meeting.id}/',
                'extendedProps': {
                    'type': 'meeting',
                    'meeting_type': meeting.get_meeting_type_display(),
                    'status': meeting.status,
                    'organizer': meeting.organizer.user.get_full_name() if meeting.organizer else 'Unknown'
                }
            })

        calendar_events = Event.objects.filter(
            Q(created_by=employee) | Q(attendees=employee),
            start_time__range=(start_date, end_date)
        ).distinct().select_related('created_by', 'created_by__user', 'customer')

        for event in calendar_events:
            events.append({
                'id': f'event_{event.id}',
                'title': event.title,
                'start': event.start_time.isoformat(),
                'end': event.end_time.isoformat(),
                'backgroundColor': event.color or '#858796',
                'borderColor': event.color or '#858796',
                'textColor': '#ffffff',
                'url': f'/events/{event.id}/',
                'extendedProps': {
                    'type': 'event',
                    'event_type': event.event_type,
                    'location': event.location or '',
                    'description': event.description or '',
                    'customer': event.customer.company_name if event.customer else None,
                    'created_by': event.created_by.user.get_full_name() if event.created_by else None
                }
            })

        # 3. Fetch Google Calendar events with improved error handling
        user_token_file = f'token_{request.user.id}.pickle'
        token_path = os.path.join(os.path.dirname(__file__), user_token_file)

        google_calendar_connected = False
        google_calendar_errors = None

        if os.path.exists(token_path):  # Check if token exists
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)

                # Check if token is expired and refresh if possible
                if creds.expired and creds.refresh_token:
                    try:
                        from google.auth.transport.requests import Request
                        creds.refresh(Request())
                        # Save the refreshed credentials
                        with open(token_path, 'wb') as token:
                            pickle.dump(creds, token)
                        logger.info(f"Google Calendar token refreshed for user {request.user.id}")
                    except Exception as refresh_error:
                        logger.error(f"Error refreshing Google credentials: {refresh_error}", exc_info=True)
                        messages.error(request, "Your Google Calendar connection has expired. Please reconnect.")
                        google_calendar_errors = f"Token refresh failed: {str(refresh_error)}"

                # Only proceed if we have valid credentials
                if not creds.expired:
                    google_calendar_connected = True
                    service = build('calendar', 'v3', credentials=creds)

                    events_result = service.events().list(
                        calendarId='primary',
                        timeMin=start_date.isoformat(),
                        timeMax=end_date.isoformat(),
                        maxResults=250,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()

                    google_events = events_result.get('items', [])

                    # Properly format Google Calendar events to match FullCalendar's expected format
                    for g_event in google_events:
                        start = g_event['start'].get('dateTime', g_event['start'].get('date'))
                        end = g_event['end'].get('dateTime', g_event['end'].get('date'))

                        events.append({
                            'id': f"google_{g_event['id']}",
                            'title': g_event['summary'],
                            'start': start,
                            'end': end,
                            'backgroundColor': '#4CAF50',  # Google Calendar color
                            'borderColor': '#4CAF50',
                            'textColor': '#ffffff',
                            'url': g_event.get('htmlLink', '#'),
                            'extendedProps': {
                                'type': 'event',
                                'event_type': 'google',
                                'description': g_event.get('description', ''),
                                'location': g_event.get('location', ''),
                                'organizer': g_event.get('organizer', {}).get('email', 'Unknown')
                            }
                        })

                    logger.info(f"Successfully loaded {len(google_events)} Google Calendar events for user {request.user.id}")
                else:
                    logger.warning(f"Google Calendar token expired for user {request.user.id} and couldn't be refreshed")
                    google_calendar_errors = "Token expired and couldn't be refreshed"

            except Exception as e:
                logger.error(f"Error fetching Google Calendar events: {e}", exc_info=True)
                messages.error(request, f"Error fetching Google Calendar events: {str(e)}")
                google_calendar_errors = str(e)
        else:
            # User hasn't connected Google Calendar yet - no error, just info
            logger.info(f"No Google Calendar token found for user {request.user.id}")

        # Add debug information to request for template rendering if needed
        request.google_calendar_connected = google_calendar_connected
        request.google_calendar_errors = google_calendar_errors

        # 4. Return combined events
        return JsonResponse(events, safe=False)

    except Exception as e:
        logger.error(f"Error getting calendar events: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def calendar_events(request):
    """
    Retrieve events for a specific customer or for the current user
    """
    customer_id = request.GET.get('customer_id')
    employee = request.user.employee_employee

    if customer_id:
        # Get events specific to this customer
        events = Event.objects.filter(customer_id=customer_id)
    else:
        # Get events where user is creator or attendee
        events = Event.objects.filter(
            Q(created_by=employee) |
            Q(attendees=employee)
        ).distinct()

    return JsonResponse([event.get_calendar_event_data() for event in events], safe=False)


@login_required
def available_slots(request):
    """Get available time slots for scheduling meetings"""
    date_str = request.GET.get('date')
    duration = int(request.GET.get('duration', 30))  # Default to 30 minutes

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Define working hours (9 AM to 5 PM)
    work_start = datetime.combine(date, datetime.strptime('09:00', '%H:%M').time())
    work_end = datetime.combine(date, datetime.strptime('17:00', '%H:%M').time())

    # Get all meetings for the day
    employee = request.user.employee_employee
    meetings = Meeting.objects.filter(
        Q(organizer=employee) | Q(attendees=employee),
        start_time__date=date
    ).order_by('start_time')

    # Create list of busy slots
    busy_slots = []
    for meeting in meetings:
        busy_slots.append({
            'start': meeting.start_time,
            'end': meeting.end_time
        })

    # Find available slots
    available_slots = []
    current_time = work_start
    slot_duration = timedelta(minutes=duration)

    while current_time + slot_duration <= work_end:
        slot_end = current_time + slot_duration
        is_available = True

        # Check if slot overlaps with any meeting
        for busy_slot in busy_slots:
            if (current_time < busy_slot['end'] and
                slot_end > busy_slot['start']):
                is_available = False
                current_time = busy_slot['end']
                break

        if is_available:
            available_slots.append({
                'start': current_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'end': slot_end.strftime('%Y-%m-%dT%H:%M:%S')
            })
            current_time += slot_duration
        else:
            continue

    return JsonResponse({
        'date': date_str,
        'duration': duration,
        'slots': available_slots
    })

@login_required
def update_task_status(request):
    """Update task status via API endpoint"""
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        new_status = request.POST.get('status')

        if not task_id or not new_status:
            return JsonResponse({
                'status': 'error',
                'message': 'Task ID and status are required'
            }, status=400)

        try:
            task = Task.objects.get(pk=task_id)

            # Check if user has permission to update this task
            if request.user.employee_employee != task.assigned_to and request.user.employee_profile != task.created_by:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Permission denied'
                }, status=403)

            # Validate status
            if new_status not in dict(Task.STATUS_CHOICES):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid status'
                }, status=400)

            task.status = new_status
            task.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Task status updated successfully',
                'task': {
                    'id': task.id,
                    'status': task.status,
                    'status_display': task.get_status_display()
                }
            })

        except Task.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Task not found'
            }, status=404)

    return JsonResponse({
        'status': 'error',
        'message': 'Method not allowed'
    }, status=405)


@login_required
def check_meeting_availability(request):
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')

    try:
        start_time = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')

        # Create scheduling service
        scheduling_service = SchedulingService(request.user)

        # Check against schedule rules
        duration = int((end_time - start_time).total_seconds() / 60)
        is_available = scheduling_service.check_availability(start_time, end_time, duration)

        if not is_available:
            next_start, next_end = scheduling_service.get_next_available_slot(start_time, duration)
            return JsonResponse({
                'available': False,
                'reason': f"Time slot conflicts with schedule rules. Next available: {next_start.strftime('%Y-%m-%d %H:%M')}"
            })

        return JsonResponse({'available': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def schedule_meeting(request):
    """Schedule a meeting via API endpoint"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data = json.loads(request.body)
    form = MeetingForm(data)

    if form.is_valid():
        meeting = form.save(commit=False)
        meeting.organizer = request.user.employee_profile

        if meeting.meeting_type == 'zoom':
            try:
                zoom_meeting = create_zoom_meeting(meeting)
                meeting.zoom_meeting_id = zoom_meeting['id']
                meeting.zoom_join_url = zoom_meeting['join_url']
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)

        meeting.save()
        form.save_m2m()  # Save many-to-many relationships

        return JsonResponse({
            'status': 'success',
            'meeting': {
                'id': meeting.id,
                'title': meeting.title,
                'start': meeting.start_time.isoformat(),
                'end': meeting.end_time.isoformat(),
                'url': meeting.get_absolute_url()
            }
        })

    return JsonResponse({'error': form.errors}, status=400)

@login_required
def export_customers(request):
    """Export customers to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customers.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Company Name', 'Contact Person', 'Email', 'Phone',
        'Address', 'City', 'State', 'ZIP', 'Status',
        'Assigned To', 'Created At'
    ])

    customers = Customer.objects.all()
    for customer in customers:
        writer.writerow([
            customer.company_name,
            customer.contact_person,
            customer.email,
            customer.phone,
            customer.address,
            customer.city,
            customer.state,
            customer.zip_code,
            customer.get_status_display(),
            customer.assigned_to.user.get_full_name() if customer.assigned_to else '',
            customer.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

@login_required
def export_leads(request):
    """Export leads to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leads.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Company Name', 'Contact Person', 'Email', 'Phone',
        'Source', 'Status', 'Assigned To', 'Created At'
    ])

    leads = Lead.objects.all()
    for lead in leads:
        writer.writerow([
            lead.company_name,
            lead.contact_person,
            lead.email,
            lead.phone,
            lead.get_source_display(),
            lead.get_status_display(),
            lead.assigned_to.user.get_full_name() if lead.assigned_to else '',
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

@login_required
def export_tasks(request):
    """Export tasks to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tasks.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Title', 'Description', 'Due Date', 'Priority',
        'Status', 'Assigned To', 'Created At'
    ])

    tasks = Task.objects.filter(
        Q(assigned_to=request.user.employee_profile) |
        Q(created_by=request.user.employee_profile)
    )

    for task in tasks:
        writer.writerow([
            task.title,
            task.description,
            task.due_date.strftime('%Y-%m-%d %H:%M:%S'),
            task.get_priority_display(),
            task.get_status_display(),
            task.assigned_to.user.get_full_name(),
            task.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

@login_required
def export_meetings(request):
    """Export meetings to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="meetings.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Title', 'Type', 'Start Time', 'End Time',
        'Description', 'Organizer', 'Attendees', 'Created At'
    ])

    meetings = Meeting.objects.filter(
        Q(organizer=request.user.employee_profile) |
        Q(attendees=request.user.employee_profile)
    ).distinct()

    for meeting in meetings:
        attendees = ', '.join([
            attendee.user.get_full_name()
            for attendee in meeting.attendees.all()
        ])

        writer.writerow([
            meeting.title,
            meeting.get_meeting_type_display(),
            meeting.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            meeting.end_time.strftime('%Y-%m-%d %H:%M:%S'),
            meeting.description,
            meeting.organizer.user.get_full_name(),
            attendees,
            meeting.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'core/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 10

    def get_queryset(self):
        """Retrieve invoices based on user role, excluding those marked as 'paid'."""
        if self.request.user.is_superuser:
            return Invoice.objects.exclude(status='paid').order_by('-issue_date')

        return Invoice.objects.filter(
            customer__assigned_to=self.request.user.employee_profile
        ).exclude(status='paid').order_by('-created_at')

class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'core/invoice_detail.html'
    context_object_name = 'invoice'


class InvoiceCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'core/invoice_form.html'
    success_url = reverse_lazy('invoice-list')

    def test_func(self):
        """Only superusers can create invoices"""
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Invoice created successfully.')
        return super().form_valid(form)


from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from .models import Invoice, Payment, ServiceSubscription
from .forms import InvoiceForm


class InvoiceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'core/invoice_form.html'
    success_url = reverse_lazy('invoice-list')

    def test_func(self):
        """Only superusers can edit invoices."""
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        """Add related data to context"""
        context = super().get_context_data(**kwargs)
        invoice = self.get_object()

        # Add customer's payment history
        context['customer_payments'] = Payment.objects.filter(
            customer=invoice.customer
        ).order_by('-transaction_date')

        # Add customer's subscription info
        context['customer_subscriptions'] = ServiceSubscription.objects.filter(
            customer=invoice.customer,
            is_active=True
        )

        # Add invoice line items if available
        if hasattr(invoice, 'notes') and invoice.notes:
            try:
                import json
                invoice_details = json.loads(invoice.notes)
                context['line_items'] = invoice_details.get('line_items', [])
            except (json.JSONDecodeError, ValueError):
                # No valid JSON in notes field
                pass

        return context

    def form_valid(self, form):
        invoice = form.save(commit=False)
        previous_status = self.get_object().status  # Get previous status before update

        # ✅ Ensure services are assigned correctly as IDs, not objects
        invoice.services.set([s.id for s in form.cleaned_data['services']])

        # ✅ Status Mapping for Payments
        status_mapping = {
            'paid': 'completed',
            'failed': 'pending',
            'pending': 'pending',
            'overdue': 'pending',
        }

        # Import the invoice generator
        from .invoice_automation import InvoiceGenerator
        invoice_generator = InvoiceGenerator()

        # ✅ Handle status change with automation
        if invoice.status != previous_status:
            if invoice.status == 'paid' and previous_status != 'paid':
                # Create a payment record if invoice is marked as paid
                with transaction.atomic():
                    # Check for existing payment
                    existing_payment = Payment.objects.filter(invoice=invoice).exists()

                    if not existing_payment:
                        # Create payment using the invoice generator
                        try:
                            payment = Payment.objects.create(
                                customer=invoice.customer,
                                invoice=invoice,
                                amount=invoice.total_amount,
                                status='completed',
                                transaction_date=timezone.now()
                            )

                            # Create transaction record
                            Transaction.objects.create(
                                customer=invoice.customer,
                                invoice=invoice,
                                payment=payment,
                                transaction_type='invoice_payment',
                                amount=payment.amount,
                                reference=payment.reference or f"INV-{invoice.invoice_number}",
                                status='completed'
                            )

                            messages.success(self.request, f'Invoice marked as {invoice.status}, payment recorded.')
                        except Exception as e:
                            logger.error(f"Error creating payment record: {str(e)}")
                            messages.error(self.request, f"Error recording payment: {str(e)}")

            elif invoice.status == 'overdue' and previous_status != 'overdue':
                # Create overdue notification
                from .notification_service import SmartNotificationService
                notification_service = SmartNotificationService()

                try:
                    notification_service.create_notification(
                        user=invoice.customer.assigned_to.user,
                        title=f"Invoice {invoice.invoice_number} Marked Overdue",
                        message=f"Invoice for {invoice.customer.company_name} in the amount of ${invoice.total_amount} has been marked as overdue.",
                        notification_type="deadline",
                        event_datetime=timezone.now(),
                        priority="high",
                        content_object=invoice,
                        action_url=reverse('invoice-detail', args=[invoice.id])
                    )
                except Exception as e:
                    logger.error(f"Error creating overdue notification: {str(e)}")

        invoice.save()
        messages.success(self.request, 'Invoice updated successfully.')
        return super().form_valid(form)




class InvoiceDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Invoice
    template_name = 'core/invoice_confirm_delete.html'
    success_url = reverse_lazy('invoice-list')

    def test_func(self):
        """Only superusers can delete invoices"""
        return self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Invoice deleted successfully.')
        return super().delete(request, *args, **kwargs)


# -------------------------------
# 💳 PAYMENT VIEWS
# -------------------------------

class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'core/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 10

    def get_queryset(self):
        """Ensure correct payments are retrieved, including completed ones from invoices"""
        queryset = Payment.objects.all().order_by('-transaction_date')
        search_query = self.request.GET.get('search', '').strip()

        if search_query:
            queryset = queryset.filter(
                Q(invoice__invoice_number__icontains=search_query) |
                Q(customer__company_name__icontains=search_query)
            )

        return queryset




class PaymentDetailView(LoginRequiredMixin, DetailView):
    model = Payment
    template_name = 'core/payment_detail.html'
    context_object_name = 'payment'


class PaymentCreateView(LoginRequiredMixin, FormView):
    template_name = 'core/payment_form.html'
    form_class = PaymentForm

    def get_initial(self):
        """Pre-fill invoice if provided in URL"""
        initial = {}
        invoice_id = self.request.GET.get('invoice')
        if invoice_id:
            try:
                invoice = Invoice.objects.get(pk=invoice_id)
                initial['invoice'] = invoice
                initial['customer'] = invoice.customer
                initial['amount'] = invoice.balance_due
            except Invoice.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        # Use transaction.atomic to ensure consistency
        with transaction.atomic():
            # Get cleaned data
            invoice = form.cleaned_data['invoice']
            customer = form.cleaned_data['customer']
            amount = form.cleaned_data['amount']
            payment_method = form.cleaned_data.get('payment_method')

            # Check balance before creating payment
            balance_due = invoice.balance_due
            if amount > balance_due:
                messages.error(self.request, f"Payment exceeds the outstanding balance of ${balance_due:.2f}!")
                return self.form_invalid(form)

            # Create payment
            payment = Payment.objects.create(
                customer=customer,
                invoice=invoice,
                amount=amount,
                status='completed',
                payment_method=payment_method
            )

            # Create transaction record
            Transaction.objects.create(
                customer=invoice.customer,
                invoice=invoice,
                payment=payment,
                transaction_type='invoice_payment',
                amount=payment.amount,
                reference=payment.reference,
                status='completed'
            )

            messages.success(self.request, f'Payment of ${payment.amount:.2f} applied to Invoice {invoice.invoice_number}.')

            # Use reverse instead of reverse_lazy
            return HttpResponseRedirect(reverse('payment-list'))




# -------------------------------
# 📜 SUBSCRIPTION VIEWS
# -------------------------------

class SubscriptionListView(LoginRequiredMixin, ListView):
    model = Subscription
    template_name = 'core/subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 10

    def get_queryset(self):
        """Filter subscriptions based on user role"""
        if self.request.user.is_superuser:
            return Subscription.objects.all().order_by('-start_date')
        return Subscription.objects.filter(customer__assigned_to=self.request.user.employee_proifle).order_by('-start_date')


class SubscriptionDetailView(LoginRequiredMixin, DetailView):
    model = Subscription
    template_name = 'core/subscription_detail.html'
    context_object_name = 'subscription'


class SubscriptionCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Subscription
    form_class = SubscriptionForm
    template_name = 'core/subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def test_func(self):
        """Only superusers can create subscriptions"""
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Subscription created successfully.')
        return super().form_valid(form)


class SubscriptionUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Subscription
    form_class = SubscriptionForm
    template_name = 'core/subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def test_func(self):
        """Only superusers can update subscriptions"""
        return self.request.user.is_superuser

    def form_valid(self, form):
        messages.success(self.request, 'Subscription updated successfully.')
        return super().form_valid(form)


class SubscriptionDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Subscription
    template_name = 'core/subscription_confirm_delete.html'
    success_url = reverse_lazy('subscription-list')

    def test_func(self):
        """Only superusers can delete subscriptions"""
        return self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Subscription deleted successfully.')
        return super().delete(request, *args, **kwargs)


# Billing Dashboard View
class BillingDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/billing_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get standard billing data
            context.update({
                'invoices': Invoice.objects.exclude(status='paid').order_by('-created_at'),  # Show only unpaid invoices
                'payments': Payment.objects.all().order_by('-transaction_date'),
                'subscriptions': Subscription.objects.all().order_by('-start_date'),
                'transactions': Transaction.objects.all().order_by('-transaction_date'),
            })

            # Add revenue statistics with Invoice Generator
            try:
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                # Get current month and year
                today = timezone.now().date()
                current_month = today.month
                current_year = today.year

                # Calculate monthly revenue
                monthly_revenue = Payment.objects.filter(
                    transaction_date__year=current_year,
                    transaction_date__month=current_month,
                    status='completed'
                ).aggregate(total=models.Sum('amount'))['total'] or 0

                # Calculate yearly revenue
                yearly_revenue = Payment.objects.filter(
                    transaction_date__year=current_year,
                    status='completed'
                ).aggregate(total=models.Sum('amount'))['total'] or 0

                # Calculate outstanding invoices amount
                outstanding_amount = Invoice.objects.filter(
                    status__in=['pending', 'partial', 'overdue']
                ).aggregate(total=models.Sum('amount_due'))['total'] or 0

                # Calculate overdue invoices amount
                overdue_amount = Invoice.objects.filter(
                    status='overdue'
                ).aggregate(total=models.Sum('amount_due'))['total'] or 0

                # Get revenue by service type
                from django.db.models import Sum, F
                revenue_by_service = []

                services = Service.objects.all()
                for service in services:
                    # Find all service subscriptions for this service
                    subscriptions = ServiceSubscription.objects.filter(service=service, is_active=True)

                    # Find invoices related to these subscriptions
                    service_invoices = Invoice.objects.filter(services__in=subscriptions)

                    # Calculate total paid for these invoices
                    paid_amount = Payment.objects.filter(
                        invoice__in=service_invoices,
                        status='completed'
                    ).aggregate(total=models.Sum('amount'))['total'] or 0

                    revenue_by_service.append({
                        'service': service.name,
                        'amount': paid_amount,
                        'subscriptions': subscriptions.count()
                    })

                # Add to context
                context.update({
                    'monthly_revenue': monthly_revenue,
                    'yearly_revenue': yearly_revenue,
                    'outstanding_amount': outstanding_amount,
                    'overdue_amount': overdue_amount,
                    'revenue_by_service': revenue_by_service
                })

                # Get pending invoice generations
                from django.db.models import Count
                service_subscriptions_needing_invoices = ServiceSubscription.objects.filter(
                    is_active=True,
                    invoice_generated=False
                ).count()

                context['subscriptions_needing_invoices'] = service_subscriptions_needing_invoices

                # Get upcoming invoice due dates
                upcoming_due_invoices = Invoice.objects.filter(
                    due_date__range=[today, today + timedelta(days=7)],
                    status__in=['pending', 'partial']
                ).order_by('due_date')

                context['upcoming_due_invoices'] = upcoming_due_invoices

            except Exception as e:
                logger.error(f"Error calculating revenue statistics: {str(e)}")

        except Exception as e:
            logger.error(f"Error loading billing dashboard data: {str(e)}")
            messages.error(self.request, f"Error loading billing data: {str(e)}")
            context.update({
                'invoices': [],
                'payments': [],
                'subscriptions': []
            })

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests for billing actions"""
        action = request.POST.get('action')

        if action == 'generate_pending_invoices':
            # Generate invoices for all pending subscriptions
            try:
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                # Generate subscription invoices
                invoices_created = invoice_generator.generate_subscription_invoices()

                # Generate project invoices if applicable
                if hasattr(invoice_generator, 'generate_project_invoices'):
                    project_invoices = invoice_generator.generate_project_invoices()
                    invoices_created += project_invoices

                if invoices_created > 0:
                    messages.success(request, f"Successfully generated {invoices_created} invoice(s)")
                else:
                    messages.info(request, "No new invoices were generated")

            except Exception as e:
                logger.error(f"Error generating invoices: {str(e)}")
                messages.error(request, f"Error generating invoices: {str(e)}")

        elif action == 'process_overdue_invoices':
            # Mark overdue invoices
            try:
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                count = invoice_generator.process_overdue_invoices()

                if count > 0:
                    messages.success(request, f"Marked {count} invoice(s) as overdue")
                else:
                    messages.info(request, "No invoices to mark as overdue")

            except Exception as e:
                logger.error(f"Error processing overdue invoices: {str(e)}")
                messages.error(request, f"Error processing overdue invoices: {str(e)}")

        elif action == 'send_invoice_reminders':
            # Send reminders for upcoming and overdue invoices
            try:
                from .invoice_automation import InvoiceGenerator
                invoice_generator = InvoiceGenerator()

                count = invoice_generator.send_invoice_reminders()

                if count > 0:
                    messages.success(request, f"Sent {count} invoice reminder(s)")
                else:
                    messages.info(request, "No invoice reminders to send")

            except Exception as e:
                logger.error(f"Error sending invoice reminders: {str(e)}")
                messages.error(request, f"Error sending invoice reminders: {str(e)}")

        return redirect('billing_dashboard')

# Invoice Views
class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'core/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 10

    def get_queryset(self):
        """Exclude paid invoices so they don't appear in the invoice list"""
        return Invoice.objects.exclude(status='paid').order_by('-created_at')

class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'core/invoice_detail.html'
    context_object_name = 'invoice'

class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    fields = ['customer', 'issue_date', 'due_date', 'total_amount', 'status']
    template_name = 'core/invoice_form.html'
    success_url = reverse_lazy('invoice-list')

    def form_valid(self, form):
        messages.success(self.request, 'Invoice created successfully.')
        return super().form_valid(form)

class InvoiceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'core/invoice_form.html'
    success_url = reverse_lazy('invoice-list')

    def test_func(self):
        """Only superusers can edit invoices"""
        return self.request.user.is_superuser

    def form_valid(self, form):
        invoice = form.save(commit=False)
        previous_status = self.get_object().status  # Get previous status before update

        # ✅ If invoice is marked as PAID, create a corresponding payment entry
        if invoice.status == 'paid' and previous_status != 'paid':
            existing_payment = Payment.objects.filter(invoice=invoice).exists()

            if not existing_payment:
                Payment.objects.create(
                    customer=invoice.customer,
                    invoice=invoice,
                    amount=invoice.total_amount,
                    status='completed',  # ✅ Ensuring "paid" invoices create "completed" payments
                    transaction_date=timezone.now(),
                )

                messages.success(self.request, 'Invoice marked as paid and moved to payments.')

        invoice.save()  # ✅ Ensure invoice status is saved
        messages.success(self.request, 'Invoice updated successfully.')
        return super().form_valid(form)


class InvoiceDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice
    template_name = 'core/invoice_confirm_delete.html'
    success_url = reverse_lazy('invoice-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Invoice deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Payment Views
class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'core/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 10

    def get_queryset(self):
        """Retrieve only completed payments for invoices marked as paid."""
        queryset = Payment.objects.filter(
            status='completed',
            invoice__status='paid'
        ).order_by('-transaction_date')

        # Apply search filter if a search query is provided
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(invoice__invoice_number__icontains=search_query) |
                Q(customer__company_name__icontains=search_query)
            )

        return queryset



class PaymentDetailView(LoginRequiredMixin, DetailView):
    model = Payment
    template_name = 'core/payment_detail.html'
    context_object_name = 'payment'


class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'core/payment_form.html'
    success_url = reverse_lazy('payment-list')


    def get_initial(self):
        """Pre-fill invoice if provided in URL"""
        initial = super().get_initial()
        invoice_id = self.request.GET.get('invoice')
        if invoice_id:
            try:
                invoice = Invoice.objects.get(pk=invoice_id)
                initial['invoice'] = invoice
                initial['customer'] = invoice.customer
                initial['amount'] = invoice.balance_due
            except Invoice.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        # Use transaction.atomic to ensure consistency
        with transaction.atomic():
            # Manually process the payment
            invoice = form.cleaned_data['invoice']

            # Check balance before creating payment
            balance_due = invoice.balance_due
            if form.cleaned_data['amount'] > balance_due:
                messages.error(self.request, f"Payment exceeds the outstanding balance of ${balance_due:.2f}!")
                return self.form_invalid(form)

            # Create payment
            payment = Payment.objects.create(
                customer=form.cleaned_data['customer'],
                invoice=invoice,
                amount=form.cleaned_data['amount'],
                status='completed',
                payment_method=form.cleaned_data.get('payment_method')
            )

            # Create transaction record
            Transaction.objects.create(
                customer=invoice.customer,
                invoice=invoice,
                payment=payment,
                transaction_type='invoice_payment',
                amount=payment.amount,
                reference=payment.reference,
                status='completed'
            )

            messages.success(self.request, f'Payment of ${payment.amount:.2f} applied to Invoice {invoice.invoice_number}.')

            return HttpResponseRedirect('/billing/payments/')





class PaymentUpdateView(LoginRequiredMixin, UpdateView):
    model = Payment
    fields = ['customer', 'amount', 'payment_method', 'payment_date', 'status']
    template_name = 'core/payment_form.html'
    success_url = reverse_lazy('payment-list')

    def form_valid(self, form):
        messages.success(self.request, 'Payment updated successfully.')
        return super().form_valid(form)

class PaymentDeleteView(LoginRequiredMixin, DeleteView):
    model = Payment
    template_name = 'core/payment_confirm_delete.html'
    success_url = reverse_lazy('payment-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Payment deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Subscription Views
class SubscriptionListView(LoginRequiredMixin, ListView):
    model = Subscription
    template_name = 'core/subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 10

class SubscriptionDetailView(LoginRequiredMixin, DetailView):
    model = Subscription
    template_name = 'core/subscription_detail.html'
    context_object_name = 'subscription'

class SubscriptionCreateView(LoginRequiredMixin, CreateView):
    model = Subscription
    fields = ['customer', 'plan', 'start_date', 'end_date', 'status']
    template_name = 'core/subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def form_valid(self, form):
        messages.success(self.request, 'Subscription created successfully.')
        return super().form_valid(form)

class SubscriptionUpdateView(LoginRequiredMixin, UpdateView):
    model = Subscription
    fields = ['customer', 'plan', 'start_date', 'end_date', 'status']
    template_name = 'core/subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def form_valid(self, form):
        messages.success(self.request, 'Subscription updated successfully.')
        return super().form_valid(form)

class SubscriptionCancelView(LoginRequiredMixin, DeleteView):
    model = Subscription
    template_name = 'core/subscription_confirm_cancel.html'
    success_url = reverse_lazy('subscription-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Subscription cancelled successfully.')
        return super().delete(request, *args, **kwargs)

# Billing Settings View
class BillingSettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'core/billing_settings.html'


class ServiceSubscriptionListView(ListView):
    model = ServiceSubscription
    template_name = 'core/service_subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 10

class ServiceSubscriptionCreateView(CreateView):
    model = ServiceSubscription
    form_class = ServiceSubscriptionForm
    template_name = 'core/service_subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def form_valid(self, form):
        try:
            # Save the form first
            service_subscription = form.save()

            # Generate invoice
            invoice = service_subscription.generate_invoice()

            messages.success(self.request,
                f'Service subscription and invoice {invoice.invoice_number} created successfully.')

            return super().form_valid(form)

        except Exception as e:
            # Detailed error logging
            import traceback
            print(f"Full error traceback:")
            traceback.print_exc()

            messages.error(self.request,
                f'Error creating service subscription: {str(e)}')

            # Return to the form with error
            return self.form_invalid(form)

class ServiceSubscriptionUpdateView(LoginRequiredMixin, UpdateView):
    model = ServiceSubscription
    form_class = ServiceSubscriptionForm
    template_name = 'core/service_subscription_form.html'
    success_url = reverse_lazy('subscription-list')

    def form_valid(self, form):
        """Ensure invoice generation upon service assignment."""
        messages.success(self.request, 'Service subscription created successfully.')
        response = super().form_valid(form)
        self.object.generate_invoice()
        return response

        # Save status changes
        if self.request.method == "POST":
            subscription.save()

        messages.success(self.request, "Subscription updated successfully.")
        return super().form_valid(form)


class ServiceSubscriptionDeleteView(LoginRequiredMixin, DeleteView):
    model = ServiceSubscription
    template_name = 'core/service_subscription_confirm_delete.html'
    success_url = reverse_lazy('customer-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Service removed from customer.")
        return super().delete(request, *args, **kwargs)


def custom_404(request, exception):
    return render(request, 'core/errors/404.html', status=404)

def custom_500(request):
    return render(request, 'core/errors/500.html', status=500)


class PaidInvoicesListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'core/paid_invoices.html'
    context_object_name = 'invoices'
    paginate_by = 10

    def get_queryset(self):
        """Show only fully paid invoices"""
        return Invoice.objects.filter(status='paid').order_by('-created_at')


def generate_invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)

    # Calculate amounts
    service_totals = [Decimal(service.calculate_total()) for service in invoice.services.all()]
    subtotal = sum(service_totals)
    tax_rate = Decimal("0.13")  # 13% tax rate
    tax_amount = subtotal * tax_rate
    total = subtotal + tax_amount

    # Prepare context for template
    context = {
        "invoice": invoice,
        "customer": invoice.customer,
        "services": invoice.services.all(),
        "payments": invoice.payments.all(),
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
    }

    # Render invoice template as HTML
    html_string = render_to_string("core/invoice_pdf.html", context)

    # Generate PDF in memory
    pdf_buffer = BytesIO()
    HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)

    # Return response as PDF file
    response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

    return response

def upload_ics(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)

    if request.method == 'POST':
        form = ICSUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            uploaded_file.customer = customer
            uploaded_file.save()

            file_path = uploaded_file.file.path

            with open(file_path, 'rb') as f:
                cal = Calendar.from_ical(f.read())

            for component in cal.walk():
                if component.name == "VEVENT":
                    title = component.get('SUMMARY', 'No Title')
                    description = component.get('DESCRIPTION', '')
                    location = component.get('LOCATION', '')
                    start_time = component.get('DTSTART').dt
                    end_time = component.get('DTEND').dt

                    if isinstance(start_time, datetime):
                        start_time = make_aware(start_time, pytz.UTC)
                    if isinstance(end_time, datetime):
                        end_time = make_aware(end_time, pytz.UTC)

                    Event.objects.create(
                        customer=customer,
                        title=title,
                        description=description,
                        location=location,
                        start_time=start_time,
                        end_time=end_time
                    )

            return redirect('customer-calendar', customer_id=customer.id)

    else:
        form = ICSUploadForm()

    return render(request, 'core/upload_ics.html', {'form': form, 'customer': customer})


@login_required
def customer_calendar(request, customer_id):
    try:
        customer = get_object_or_404(Customer, id=customer_id)

        # Get all related data
        events = Event.objects.filter(customer=customer)
        projects = Project.objects.filter(customer=customer)
        phases = ProjectPhase.objects.filter(project__customer=customer)
        project_tasks = ProjectTask.objects.filter(phase__project__customer=customer)
        meetings = Meeting.objects.filter(customers=customer)
        tasks = Task.objects.filter(customer=customer)

        context = {
            'customer': customer,
            'events': events,
            'projects': projects,
            'phases': phases,
            'project_tasks': project_tasks,
            'meetings': meetings,
            'tasks': tasks,
            'today': timezone.now().date()
        }

        return render(request, 'core/customer_calendar.html', context)

    except Exception as e:
        logger.error(f"Error displaying customer calendar: {str(e)}")
        messages.error(request, "Error loading calendar data.")
        return redirect('customer-detail', pk=customer_id)


# @login_required
# def customer_calendar_events(request, customer_id):
#     customer = get_object_or_404(Customer, id=customer_id)
#     events = []

#     # Get customer tasks
#     tasks = Task.objects.filter(customer=customer).select_related('assigned_to')
#     for task in tasks:
#         events.append({
#             'id': f'task_{task.id}',
#             'title': f'Task: {task.title}',
#             'start': task.due_date.isoformat(),
#             'end': task.due_date.isoformat(),
#             'url': reverse('task-detail', args=[task.id]),
#             'backgroundColor': '#ff9f89',
#             'borderColor': '#ff9f89',
#             'extendedProps': {
#                 'icon': 'fa-tasks',
#                 'assigned_to': task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'
#             }
#         })

#     # Get customer meetings
#     meetings = Meeting.objects.filter(customer=customer).prefetch_related('attendees')
#     for meeting in meetings:
#         events.append({
#             'id': f'meeting_{meeting.id}',
#             'title': f'Meeting: {meeting.title}',
#             'start': meeting.start_time.isoformat(),
#             'end': meeting.end_time.isoformat(),
#             'url': reverse('meeting-detail', args=[meeting.id]),
#             'backgroundColor': '#4e73df',
#             'borderColor': '#4e73df',
#             'extendedProps': {
#                 'icon': 'fa-video',
#                 'attendees': ', '.join([attendee.get_full_name() for attendee in meeting.attendees.all()])
#             }
#         })

#     return JsonResponse(events, safe=False)





@login_required
def user_calendar_events(request):
    """Retrieve events for displaying on the user's calendar"""
    try:
        # Get the employee profile of the current user
        employee = request.user.employee_profile
        events_list = []

        # Add projects
        projects = Project.objects.filter(
            Q(project_manager=employee) |
            Q(team_members=employee)
        ).distinct().select_related('customer')

        for project in projects:
            events_list.append({
                'id': f'project_{project.id}',
                'title': f'Project: {project.name}',
                'start': project.start_date.isoformat(),
                'end': project.target_end_date.isoformat(),
                'backgroundColor': '#4e73df',
                'borderColor': '#4e73df',
                'textColor': '#ffffff',
                'url': reverse('customer_projects:project-detail', args=[project.id]),
                'extendedProps': {
                    'type': 'project',
                    'status': project.get_status_display(),
                    'customer': project.customer.company_name,
                    'progress': f"{project.progress}%"
                }
            })

        # Add phases
        phases = ProjectPhase.objects.filter(
            project__in=projects
        ).select_related('project', 'project__customer')

        for phase in phases:
            events_list.append({
                'id': f'phase_{phase.id}',
                'title': f'Phase: {phase.name}',
                'start': phase.start_date.isoformat(),
                'end': phase.end_date.isoformat(),
                'backgroundColor': '#1cc88a',
                'borderColor': '#1cc88a',
                'textColor': '#ffffff',
                'url': reverse('customer_projects:phase-update', args=[phase.id]),
                'extendedProps': {
                    'type': 'phase',
                    'status': phase.get_status_display(),
                    'project': phase.project.name,
                    'customer': phase.project.customer.company_name,
                    'progress': f"{phase.progress}%"
                }
            })

        # Add tasks
        tasks = ProjectTask.objects.filter(
            Q(assigned_to=employee) |
            Q(phase__project__project_manager=employee)
        ).select_related('phase', 'phase__project', 'phase__project__customer')

        for task in tasks:
            events_list.append({
                'id': f'task_{task.id}',
                'title': f'Task: {task.title}',
                'start': task.start_date.isoformat(),
                'end': task.due_date.isoformat(),
                'backgroundColor': '#f6c23e',
                'borderColor': '#f6c23e',
                'textColor': '#000000',
                'url': reverse('customer_projects:task-detail', args=[task.id]),
                'extendedProps': {
                    'type': 'task',
                    'status': task.get_status_display(),
                    'project': task.phase.project.name,
                    'customer': task.phase.project.customer.company_name,
                    'phase': task.phase.name
                }
            })

        # Add meetings - Now with distinct() to prevent duplicates
        meetings = Meeting.objects.filter(
            Q(organizer=employee) |
            Q(attendees=employee)
        ).distinct().select_related('organizer').prefetch_related('customers')

        for meeting in meetings:
            events_list.append({
                'id': f'meeting_{meeting.id}',
                'title': f'Meeting: {meeting.title}',
                'start': meeting.start_time.isoformat(),
                'end': meeting.end_time.isoformat(),
                'backgroundColor': '#e74a3b',
                'borderColor': '#e74a3b',
                'textColor': '#ffffff',
                'url': reverse('meeting-detail', args=[meeting.id]),
                'extendedProps': {
                    'type': 'meeting',
                    'status': meeting.status,
                    'customer': meeting.customers.first().company_name if meeting.customers.exists() else None,
                    'meeting_type': meeting.get_meeting_type_display(),
                    'organizer': meeting.organizer.user.get_full_name(),
                }
            })

        # Add events
        events = Event.objects.filter(
            Q(created_by=employee) |
            Q(attendees=employee)
        ).distinct().select_related('created_by', 'customer')

        for event in events:
            events_list.append({
                'id': f'event_{event.id}',
                'title': event.title,
                'start': event.start_time.isoformat(),
                'end': event.end_time.isoformat(),
                'backgroundColor': '#858796',
                'borderColor': '#858796',
                'textColor': '#ffffff',
                'url': reverse('event-detail', args=[event.id]),
                'extendedProps': {
                    'type': 'event',
                    'customer': event.customer.company_name if event.customer else None,
                    'location': event.location or '',
                    'created_by': event.created_by.user.get_full_name() if event.created_by else None
                }
            })

        return JsonResponse(events_list, safe=False)

    except Exception as e:
        logger.error(f"Error getting calendar events: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def customer_calendar_events(request, customer_id):
    try:
        customer = get_object_or_404(Customer, id=customer_id)
        events = []

        # Get projects for this customer
        projects = Project.objects.filter(customer=customer).select_related('project_manager', 'project_manager__user')
        for project in projects:
            events.append({
                'id': f'project_{project.id}',
                'title': f'Project: {project.name}',
                'start': project.start_date.isoformat(),
                'end': project.target_end_date.isoformat(),
                'url': reverse('customer_projects:project-detail', args=[project.id]),
                'backgroundColor': '#4e73df',
                'borderColor': '#4e73df',
                'textColor': '#ffffff',
                'extendedProps': {
                    'type': 'project',
                    'icon': 'fa-project-diagram',
                    'status': project.get_status_display(),
                    'progress': f"{project.progress}%",
                    'manager': project.project_manager.user.get_full_name() if project.project_manager else 'Unassigned'
                }
            })

        # Get phases for all customer projects
        phases = ProjectPhase.objects.filter(project__customer=customer).select_related('project')
        for phase in phases:
            events.append({
                'id': f'phase_{phase.id}',
                'title': f'Phase: {phase.name}',
                'start': phase.start_date.isoformat(),
                'end': phase.end_date.isoformat(),
                'url': reverse('customer_projects:phase-update', args=[phase.id]),
                'backgroundColor': '#1cc88a',
                'borderColor': '#1cc88a',
                'textColor': '#ffffff',
                'extendedProps': {
                    'type': 'phase',
                    'icon': 'fa-tasks',
                    'project': phase.project.name,
                    'status': phase.get_status_display(),
                    'progress': f"{phase.progress}%"
                }
            })

        # Get project tasks
        project_tasks = ProjectTask.objects.filter(
            phase__project__customer=customer
        ).select_related('assigned_to', 'assigned_to__user', 'phase', 'phase__project')

        for task in project_tasks:
            events.append({
                'id': f'project_task_{task.id}',
                'title': f'Task: {task.title}',
                'start': task.start_date.isoformat(),
                'end': task.due_date.isoformat(),
                'url': reverse('customer_projects:task-detail', args=[task.id]),
                'backgroundColor': '#f6c23e',
                'borderColor': '#f6c23e',
                'textColor': '#000000',
                'extendedProps': {
                    'type': 'project_task',
                    'icon': 'fa-tasks',
                    'status': task.get_status_display(),
                    'project': task.phase.project.name,
                    'phase': task.phase.name,
                    'assigned_to': task.assigned_to.user.get_full_name() if task.assigned_to else 'Unassigned'
                }
            })

        # Get regular tasks
        tasks = Task.objects.filter(customer=customer).select_related('assigned_to', 'assigned_to__user')
        for task in tasks:
            if task.due_date:
                events.append({
                    'id': f'task_{task.id}',
                    'title': f'Regular Task: {task.title}',
                    'start': task.due_date.isoformat(),
                    'end': task.due_date.isoformat(),
                    'url': reverse('task-detail', args=[task.id]),
                    'backgroundColor': '#36b9cc',
                    'borderColor': '#36b9cc',
                    'textColor': '#ffffff',
                    'extendedProps': {
                        'type': 'task',
                        'icon': 'fa-tasks',
                        'status': task.get_status_display(),
                        'assigned_to': task.assigned_to.user.get_full_name() if task.assigned_to else 'Unassigned'
                    }
                })

        # Get meetings
        meetings = Meeting.objects.filter(customers=customer).prefetch_related('attendees', 'attendees__user')
        for meeting in meetings:
            if meeting.start_time:
                start_time = meeting.start_time.isoformat()
                end_time = meeting.end_time.isoformat() if meeting.end_time else start_time
                events.append({
                    'id': f'meeting_{meeting.id}',
                    'title': f'Meeting: {meeting.title}',
                    'start': start_time,
                    'end': end_time,
                    'url': reverse('meeting-detail', args=[meeting.id]),
                    'backgroundColor': '#e74a3b',
                    'borderColor': '#e74a3b',
                    'textColor': '#ffffff',
                    'extendedProps': {
                        'type': 'meeting',
                        'icon': 'fa-video',
                        'meeting_type': meeting.get_meeting_type_display(),
                        'attendees': ', '.join([attendee.user.get_full_name() for attendee in meeting.attendees.all()])
                    }
                })

        # Add customer events
        customer_events = Event.objects.filter(customer=customer).select_related('created_by', 'created_by__user')
        for event in customer_events:
            if event.start_time:
                start_time = event.start_time.isoformat()
                end_time = event.end_time.isoformat() if event.end_time else start_time
                events.append({
                    'id': f'event_{event.id}',
                    'title': f'Event: {event.title}',
                    'start': start_time,
                    'end': end_time,
                    'backgroundColor': '#858796',
                    'borderColor': '#858796',
                    'textColor': '#ffffff',
                    'extendedProps': {
                        'type': 'event',
                        'icon': 'fa-calendar',
                        'event_type': event.event_type,
                        'created_by': event.created_by.user.get_full_name() if event.created_by else 'Unknown'
                    }
                })

        return JsonResponse(events, safe=False)

    except Exception as e:
        logger.error(f"Error in customer_calendar_events: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def user_calendar_view(request):
    """
    Render the user's calendar page
    """
    return render(request, 'core/calendar.html')



@method_decorator(staff_member_required, name='dispatch')
class IPStatisticsView(TemplateView):
    template_name = 'ip_statistics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get top IPs
        context['top_ips'] = IPAccess.objects.values('ip_address')\
            .annotate(count=Count('ip_address'))\
            .order_by('-count')[:10]

        # Get recent accesses
        context['recent_accesses'] = IPAccess.objects.select_related('user')\
            .order_by('-access_time')[:50]

        # Get stats by path
        context['path_stats'] = IPAccess.objects.values('path')\
            .annotate(count=Count('path'))\
            .order_by('-count')[:10]

        return context

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class ScheduleRuleListView(LoginRequiredMixin, ListView):
    model = ScheduleRule
    template_name = 'core/schedule_rule_list.html'
    context_object_name = 'rules'

    def get_queryset(self):
        return ScheduleRule.objects.filter(user=self.request.user)

class ScheduleRuleCreateView(LoginRequiredMixin, CreateView):
    model = ScheduleRule
    form_class = ScheduleRuleForm
    template_name = 'core/schedule_rule_form.html'
    success_url = reverse_lazy('schedule-rule-list')


    def get_initial(self):
        """Set initial values for the form"""
        initial = super().get_initial()
        try:
            # Set default business hours
            initial['start_time'] = timezone.datetime.strptime('09:00', '%H:%M').time()
            initial['end_time'] = timezone.datetime.strptime('17:00', '%H:%M').time()
            initial['min_booking_duration'] = 30
            initial['max_booking_duration'] = 240
            initial['buffer_before'] = 15
            initial['buffer_after'] = 15
        except Exception as e:
            logger.error(f"Error setting initial schedule rule values: {str(e)}")
        return initial

    def get_context_data(self, **kwargs):
        """Add additional context for the template"""
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create New Schedule Rule'
        context['submit_text'] = 'Create Rule'

        # Add any existing rules for reference
        try:
            context['existing_rules'] = ScheduleRule.objects.filter(
                user=self.request.user,
                is_active=True
            )
        except Exception as e:
            logger.error(f"Error fetching existing rules: {str(e)}")
            context['existing_rules'] = []

        return context

    def form_valid(self, form):
        """Process the form if valid"""
        try:
            with transaction.atomic():
                # Set the user
                form.instance.user = self.request.user

                # Validate time constraints
                if form.cleaned_data['start_time'] >= form.cleaned_data['end_time']:
                    form.add_error(None, "End time must be after start time")
                    return self.form_invalid(form)

                # Validate booking durations
                min_duration = form.cleaned_data['min_booking_duration']
                max_duration = form.cleaned_data['max_booking_duration']
                if min_duration >= max_duration:
                    form.add_error(
                        None,
                        "Maximum booking duration must be greater than minimum duration"
                    )
                    return self.form_invalid(form)

                # Validate buffer times
                total_buffer = (form.cleaned_data['buffer_before'] +
                              form.cleaned_data['buffer_after'])
                available_minutes = (
                    timezone.datetime.combine(
                        timezone.now(),
                        form.cleaned_data['end_time']
                    ) -
                    timezone.datetime.combine(
                        timezone.now(),
                        form.cleaned_data['start_time']
                    )
                ).seconds / 60

                if total_buffer + min_duration > available_minutes:
                    form.add_error(
                        None,
                        "Buffer times plus minimum booking duration exceed available time"
                    )
                    return self.form_invalid(form)

                # Check for conflicting rules
                if self._has_conflicting_rules(form.cleaned_data):
                    form.add_error(
                        None,
                        "This rule conflicts with an existing active rule"
                    )
                    return self.form_invalid(form)

                # Save the rule
                response = super().form_valid(form)
                messages.success(
                    self.request,
                    f"Schedule rule '{form.instance.name}' created successfully"
                )
                return response

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error creating schedule rule: {str(e)}")
            form.add_error(None, "An error occurred while creating the schedule rule")
            return self.form_invalid(form)

    def _has_conflicting_rules(self, cleaned_data):
        """Check for conflicting schedule rules"""
        existing_rules = ScheduleRule.objects.filter(
            user=self.request.user,
            is_active=True,
            recurrence_type=cleaned_data['recurrence_type']
        )

        if cleaned_data['recurrence_type'] == 'weekly':
            existing_rules = existing_rules.filter(
                day_of_week=cleaned_data['day_of_week']
            )
        elif cleaned_data['recurrence_type'] == 'monthly':
            existing_rules = existing_rules.filter(
                day_of_month=cleaned_data['day_of_month']
            )
        elif cleaned_data['recurrence_type'] == 'yearly':
            existing_rules = existing_rules.filter(
                month=cleaned_data['month'],
                day_of_month=cleaned_data['day_of_month']
            )

        for rule in existing_rules:
            if (rule.start_time < cleaned_data['end_time'] and
                rule.end_time > cleaned_data['start_time']):
                return True
        return False

    def form_invalid(self, form):
        """Handle invalid form submission"""
        messages.error(
            self.request,
            "Please correct the errors below"
        )
        return super().form_invalid(form)

    def get_success_url(self):
        """Get URL to redirect to after successful creation"""
        if 'create_another' in self.request.POST:
            return reverse_lazy('schedule-rule-create')
        return self.success_url

class ScheduleRuleUpdateView(LoginRequiredMixin, UpdateView):
    model = ScheduleRule
    form_class = ScheduleRuleForm
    template_name = 'core/schedule_rule_form.html'
    success_url = reverse_lazy('schedule-rule-list')

    def get_queryset(self):
        # Ensure users can only edit their own rules
        return ScheduleRule.objects.filter(user=self.request.user)

class ScheduleRuleDeleteView(LoginRequiredMixin, DeleteView):
    model = ScheduleRule
    template_name = 'core/schedule_rule_confirm_delete.html'
    success_url = reverse_lazy('schedule-rule-list')

    def get_queryset(self):
        # Ensure users can only delete their own rules
        return ScheduleRule.objects.filter(user=self.request.user)


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if not (request.user.employee_profile == event.created_by or request.user.employee_profile in event.attendees.all()):
        messages.error(request, "You don't have permission to view this event.")
        return redirect('calendar')
    return render(request, 'core/event_detail.html', {'event': event})

# Event Views
class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = 'core/event_list.html'
    context_object_name = 'events'
    paginate_by = 10

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Event.objects.filter(
            Q(created_by=employee) | Q(attendees=employee)
        ).order_by('-start_time')

class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'core/event_detail.html'
    context_object_name = 'event'

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Event.objects.filter(
            Q(created_by=employee) | Q(attendees=employee)
        )

class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'core/event_form.html'
    success_url = reverse_lazy('event-list')

    def get_initial(self):
        initial = super().get_initial()
        initial['created_by'] = self.request.user.employee_profile

        # Pre-fill dates if provided in URL
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')

        if start:
            initial['start_time'] = parse(start)
        if end:
            initial['end_time'] = parse(end)

        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user.employee_profile
        messages.success(self.request, 'Event created successfully.')
        return super().form_valid(form)

class EventUpdateView(LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'core/event_form.html'
    success_url = reverse_lazy('event-list')

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Event.objects.filter(
            Q(created_by=employee) | Q(attendees=employee)
        )

    def form_valid(self, form):
        messages.success(self.request, 'Event updated successfully.')
        return super().form_valid(form)

class EventDeleteView(LoginRequiredMixin, DeleteView):
    model = Event
    template_name = 'core/event_confirm_delete.html'
    success_url = reverse_lazy('event-list')

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Event.objects.filter(
            Q(created_by=employee) | Q(attendees=employee)
        )

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Event deleted successfully.')
        return super().delete(request, *args, **kwargs)

# Customer Event Views
class CustomerEventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = 'core/customer_event_list.html'
    context_object_name = 'events'
    paginate_by = 10

    def get_queryset(self):
        customer_id = self.kwargs.get('customer_id')
        return Event.objects.filter(customer_id=customer_id).order_by('-start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customer'] = get_object_or_404(Customer, id=self.kwargs.get('customer_id'))
        return context

class CustomerEventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'core/event_form.html'

    def get_initial(self):
        initial = super().get_initial()
        customer = get_object_or_404(Customer, id=self.kwargs.get('customer_id'))
        initial['customer'] = customer

        # Pre-fill dates if provided in URL
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')

        try:
            if start:
                initial['start_time'] = parse(start)
            if end:
                initial['end_time'] = parse(end)
        except Exception as e:
            logger.error(f"Date parsing error: {e}")

        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user.employee_profile
        form.instance.customer = get_object_or_404(Customer, id=self.kwargs.get('customer_id'))
        messages.success(self.request, 'Customer event created successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('customer-calendar', kwargs={'customer_id': self.kwargs.get('customer_id')})

# Additional views to support existing functionality

@login_required
def customer_calendar_view(request, customer_id):
    """
    Render the customer's calendar page
    """
    customer = get_object_or_404(Customer, id=customer_id)
    return render(request, 'core/customer_calendar.html', {'customer': customer})

@login_required
def customer_calendar_events(request, customer_id):
    """
    Retrieve events specific to this customer
    """
    customer = get_object_or_404(Customer, id=customer_id)

    # Retrieve events specific to this customer
    events = Event.objects.filter(customer=customer)

    event_data = []
    for event in events:
        # Determine event color with fallback
        event_color = event.color if event.color else '#3788d8'

        # Determine text color based on background brightness
        def get_text_color(hex_color):
            hex_color = hex_color.lstrip('#')
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
            return 'black' if brightness > 125 else 'white'

        text_color = get_text_color(event_color)

        event_data.append({
            'id': f'event_{event.id}',
            'title': event.title,
            'start': event.start_time.isoformat(),
            'end': event.end_time.isoformat(),
            'allDay': False,
            'url': reverse('event-detail', args=[event.id]),
            'backgroundColor': event_color,
            'borderColor': event_color,
            'textColor': text_color,
            'extendedProps': {
                'type': event.event_type,
                'customer': customer.company_name,
                'description': event.description or '',
                'location': event.location or '',
                'attendees': [
                    {
                        'name': attendee.user.get_full_name(),
                        'email': attendee.user.email
                    } for attendee in event.attendees.all()
                ]
            }
        })

    return JsonResponse(event_data, safe=False)



@login_required
def chat_inbox(request):
    current_employee = request.user.employee_profile

    # Get all chat sessions for the current user with annotations
    chat_sessions = ChatSession.objects.filter(
        participants=current_employee
    ).annotate(
        unread_count=Count(
            'messages',
            filter=Q(
                messages__is_read=False,
                messages__receiver=current_employee
            )
        )
    ).prefetch_related(
        'participants',
        'participants__user',  # Add this to prefetch user data
        'messages'
    ).order_by('-updated_at')

    # Get the latest message for each session
    for session in chat_sessions:
        session.last_message = session.messages.order_by('-timestamp').first()
        # Get other participant
        session.other_participant = session.participants.exclude(id=current_employee.id).first()

    context = {
        'chat_sessions': chat_sessions,
        'available_employees': Employee.objects.exclude(id=current_employee.id).select_related('user'),  # Add select_related
    }

    return render(request, 'chat/chat_inbox.html', context)

logger = logging.getLogger(__name__)

@login_required
def chat_detail(request, session_id):
    """
    Display chat detail view with messages and allow adding new participants.
    """
    current_user = request.user.employee_profile

    try:
        # Get session and verify participant
        session = get_object_or_404(
            ChatSession.objects.prefetch_related(
                Prefetch(
                    "participants",
                    queryset=Employee.objects.select_related("user")
                )
            ),
            id=session_id,
            participants=current_user
        )

        # Get other participant for 1-on-1 chat
        other_participant = session.participants.exclude(id=current_user.id).first()

        if not other_participant and not session.is_group_chat:
            messages.error(request, "Chat session not found or you don't have access.")
            return redirect("chat_inbox")

        # Get chat messages and mark as read
        chat_messages = ChatMessage.objects.filter(
            session=session
        ).select_related(
            "sender__user",
            "receiver__user"
        ).order_by("timestamp")

        ChatMessage.objects.filter(
            session=session,
            receiver=current_user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )

        # Fetch employees NOT in the chat for "Add User" dropdown
        available_employees = Employee.objects.exclude(
            id__in=session.participants.values_list("id", flat=True)
        )

        return render(request, "chat/chat_detail.html", {
            "session": session,
            "chat_messages": chat_messages,
            "other_participant": other_participant,
            "available_employees": available_employees,  # ✅ Users available for selection in dropdown
        })

    except Exception as e:
        logger.error(f"Error in chat detail: {str(e)}")
        messages.error(request, "An error occurred while loading the chat.")
        return redirect("chat_inbox")



@login_required
def start_chat(request, employee_id):
    """
    Start a new chat with an employee or open existing chat
    """
    try:
        other_employee = get_object_or_404(Employee, employee_id=employee_id)
        current_user = request.user.employee_profile

        # Prevent self-chat
        if other_employee == current_user:
            messages.warning(request, "You cannot start a chat with yourself.")
            return redirect('chat_inbox')

        # Find existing session or create new one
        session = ChatSession.objects.filter(
            is_group_chat=False,
            participants=current_user
        ).filter(
            participants=other_employee
        ).first()

        if not session:
            session = ChatSession.objects.create(
                is_group_chat=False,
                name=f"Chat with {other_employee.get_full_name()}"
            )
            session.participants.add(current_user, other_employee)
            session.save()

        return redirect('chat_detail', session_id=session.id)

    except Exception as e:
        logger.error(f"Error starting chat: {str(e)}")
        messages.error(request, "An error occurred while starting the chat.")
        return redirect('chat_inbox')

@login_required
def send_message(request):
    """
    Handle sending messages
    """
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Get data from request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        content = data.get('content', '').strip()
        receiver_id = data.get('receiver_id')
        session_id = data.get('session_id')

        # Validate data
        if not content:
            return JsonResponse({'error': 'Message content cannot be empty'}, status=400)

        if not receiver_id:
            return JsonResponse({'error': 'Receiver ID is required'}, status=400)

        # Get sender and receiver
        sender = request.user.employee_profile
        try:
            receiver = Employee.objects.get(employee_id=receiver_id)
        except Employee.DoesNotExist:
            return JsonResponse({'error': 'Receiver not found'}, status=404)

        if sender == receiver:
            return JsonResponse({'error': 'Cannot send message to yourself'}, status=400)

        # Get or create session
        try:
            if session_id:
                session = ChatSession.objects.get(
                    id=session_id,
                    participants=sender
                )
                if receiver not in session.participants.all():
                    return JsonResponse({'error': 'Invalid receiver for this chat session'}, status=400)
            else:
                session = ChatSession.objects.create(is_group_chat=False)
                session.participants.add(sender, receiver)
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Chat session not found'}, status=404)

        # Create message
        message = ChatMessage.objects.create(
            session=session,
            sender=sender,
            receiver=receiver,
            content=content,
            timestamp=timezone.now()
        )

        # Update session timestamp
        session.updated_at = timezone.now()
        session.save()

        return JsonResponse({
            'status': 'success',
            'message': {
                'id': message.id,
                'content': message.content,
                'sender': {
                    'id': sender.employee_id,
                    'name': sender.get_full_name()
                },
                'receiver': {
                    'id': receiver.employee_id,
                    'name': receiver.get_full_name()
                },
                'timestamp': message.timestamp.isoformat(),
                'is_read': message.is_read
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return JsonResponse({'error': 'Error sending message'}, status=500)

@login_required
def get_messages(request, session_id):
    """
    Get messages for a chat session
    """
    try:
        session = get_object_or_404(
            ChatSession,
            id=session_id,
            participants=request.user.employee_profile
        )

        last_message_id = request.GET.get('last_id')
        limit = int(request.GET.get('limit', 50))

        messages_query = ChatMessage.objects.filter(session=session)

        if last_message_id:
            messages_query = messages_query.filter(id__lt=last_message_id)

        messages = messages_query.select_related(
            'sender__user',
            'receiver__user'
        ).order_by('-timestamp')[:limit]

        message_data = [{
            'id': msg.id,
            'content': msg.content,
            'sender': {
                'id': msg.sender.employee_id,
                'name': msg.sender.get_full_name()
            },
            'timestamp': msg.timestamp.isoformat(),
            'is_read': msg.is_read
        } for msg in messages]

        return JsonResponse({
            'messages': message_data,
            'has_more': messages.count() == limit
        })

    except Exception as e:
        logger.error(f"Error fetching messages: {str(e)}")
        return JsonResponse({'error': 'Error fetching messages'}, status=500)

@login_required
def get_unread_count(request):
    """
    Get count of unread messages
    """
    try:
        unread_count = ChatMessage.objects.filter(
            receiver=request.user.employee_profile,
            is_read=False
        ).count()

        return JsonResponse({'unread_count': unread_count})
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        return JsonResponse({'error': 'Error getting unread count'}, status=500)

@login_required
def mark_messages_read(request, session_id):
    """
    Mark all messages in a session as read
    """
    try:
        session = get_object_or_404(
            ChatSession,
            id=session_id,
            participants=request.user.employee_profile
        )

        updated_count = ChatMessage.objects.filter(
            session=session,
            receiver=request.user.employee_profile,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )

        return JsonResponse({
            'status': 'success',
            'messages_read': updated_count
        })

    except Exception as e:
        logger.error(f"Error marking messages as read: {str(e)}")
        return JsonResponse({'error': 'Error marking messages as read'}, status=500)


@login_required
def employee_list_api(request):
    employees = Employee.objects.exclude(id=request.user.employee_profile.id)
    data = [{'id': emp.id, 'name': emp.get_full_name()} for emp in employees]
    return JsonResponse(data, safe=False)



@login_required
def update_event(request):
    """API endpoint to update event date/time"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        event_id = data.get('id')
        start_time = data.get('start')
        end_time = data.get('end')

        event = get_object_or_404(Event, id=event_id)

        # Verify permissions
        if event.created_by != request.user.employee_profile and request.user.employee_profile not in event.attendees.all():
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Update event times
        event.start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        event.end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        event.save()

        return JsonResponse({'status': 'success'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error updating event: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def debug_calendar_items(request):
    """Debug endpoint to check what items exist"""
    employee = request.user.employee_profile

    tasks = Task.objects.filter(
        Q(assigned_to=employee) | Q(created_by=employee)
    )

    meetings = Meeting.objects.filter(
        Q(organizer=employee) | Q(attendees=employee)
    ).distinct()

    events = Event.objects.filter(
        Q(created_by=employee) | Q(attendees=employee)
    )

    debug_data = {
        'tasks': [
            {
                'id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assigned_to': task.assigned_to.user.username if task.assigned_to else None,
                'created_by': task.created_by.user.username if task.created_by else None,
            } for task in tasks
        ],
        'meetings': [
            {
                'id': meeting.id,
                'title': meeting.title,
                'start_time': meeting.start_time.isoformat() if meeting.start_time else None,
                'end_time': meeting.end_time.isoformat() if meeting.end_time else None,
                'organizer': meeting.organizer.user.username if meeting.organizer else None,
            } for meeting in meetings
        ],
        'events': [
            {
                'id': event.id,
                'title': event.title,
                'start_time': event.start_time.isoformat() if event.start_time else None,
                'end_time': event.end_time.isoformat() if event.end_time else None,
                'created_by': event.created_by.user.username if event.created_by else None,
            } for event in events
        ]
    }

    return JsonResponse({
        'employee': employee.user.username,
        'counts': {
            'tasks': tasks.count(),
            'meetings': meetings.count(),
            'events': events.count(),
        },
        'items': debug_data
    })


@login_required
def notifications_ws(request, employee_id):
    """
    Placeholder view for WebSocket URL routing
    This view is never called directly, but Django needs it for URL resolution
    """
    return HttpResponse(status=200)


logger = logging.getLogger(__name__)


class EmailInboxView(LoginRequiredMixin, ListView):
    """Display inbox emails"""
    model = EmailMessage
    template_name = 'core/email_inbox.html'
    context_object_name = 'emails'
    paginate_by = 20

    class EmailInboxView(LoginRequiredMixin, ListView):
        """Display inbox emails"""
        model = EmailMessage
        template_name = 'core/email_inbox.html'
        context_object_name = 'emails'
        paginate_by = 20

    def get_queryset(self):
        """Retrieve emails for the user's associated EmailAccount"""
        user = self.request.user

        # Ensure user has an Employee profile
        if not hasattr(user, 'employee_profile'):
            raise ValidationError("User does not have an associated employee profile.")

        employee = user.employee_profile

        # Ensure Employee has an EmailAccount
        email_account = getattr(employee, 'email_account', None)
        if not email_account:
            raise ValidationError("User does not have an associated email account.")

        return EmailMessage.objects.filter(
            account=email_account,
            message_type='incoming',
            is_archived=False,
            is_spam=False
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.request.user.employee_profile.email_account

        # Fetch the latest email thread (if any)
        latest_thread = EmailMessage.objects.filter(account=account).order_by('-created_at').first()

        context['latest_thread'] = latest_thread
        return context


@login_required
def email_account_create(request):
    """View for creating an email account"""
    if request.method == 'POST':
        form = EmailAccountForm(request.POST)
        if form.is_valid():
            email_account = form.save(commit=False)
            email_account.employee = request.user.employee_profile  # Associate with logged-in employee
            email_account.save()
            messages.success(request, 'Email account registered successfully!')
            return redirect('email_account_list')
    else:
        form = EmailAccountForm()

    return render(request, 'core/email_account_form.html', {'form': form, 'title': 'Create Email Account'})


@login_required
def email_account_update(request, pk):
    """View for updating an email account"""
    email_account = get_object_or_404(EmailAccount, pk=pk, employee=request.user.employee_profile)

    if request.method == 'POST':
        form = EmailAccountForm(request.POST, instance=email_account)
        if form.is_valid():
            form.save()
            messages.success(request, 'Email account updated successfully!')
            return redirect('email_inbox')  # ✅ Redirect to inbox after successful update
        else:
            messages.error(request, 'Error updating email account. Please check the form and try again.')  # ✅ Flash an error message

    else:
        form = EmailAccountForm(instance=email_account)

    return render(request, 'core/email_account_form.html', {
        'form': form,
        'title': 'Update Email Account'
    })

@login_required
def activate_email_account(request):
    """Activate existing email account by setting password"""
    try:
        email_account = request.user.employee_profile.email_account

        # If account is already active, redirect to inbox
        if email_account.is_active:
            messages.info(request, "Your email account is already activated.")
            return redirect('email_inbox')

        if request.method == 'POST':
            password = request.POST.get('password')
            if not password:
                messages.error(request, "Password is required.")
                return render(request, 'core/email_activation.html', {
                    'email_address': email_account.email_address
                })

            try:
                # Test the email credentials before saving
                provider = email_account.provider
                if provider:
                    # Initialize test connection based on provider
                    if '@gmail.com' in email_account.email_address:
                        # Gmail specific test
                        with smtplib.SMTP(provider.smtp_server, provider.smtp_port) as server:
                            server.starttls()
                            server.login(email_account.email_address, password)
                    else:
                        # Generic test for other providers
                        with smtplib.SMTP(provider.smtp_server, provider.smtp_port) as server:
                            server.starttls()
                            server.login(email_account.email_address, password)

                    # If login successful, save the credentials
                    email_account.password = password
                    email_account.is_active = True
                    email_account.save()

                    messages.success(request,
                        "Email account activated successfully! You can now send and receive emails."
                    )
                    return redirect('email_inbox')

            except smtplib.SMTPAuthenticationError:
                messages.error(request,
                    "Invalid password. If you're using Gmail with 2FA, please use an App Password."
                )
            except Exception as e:
                logger.error(f"Email activation error: {str(e)}")
                messages.error(request,
                    "Error connecting to email server. Please verify your password and try again."
                )

        # Show the activation form
        return render(request, 'core/email_activation.html', {
            'email_address': email_account.email_address,
            'provider_name': email_account.provider.name if email_account.provider else 'Unknown'
        })

    except EmailAccount.DoesNotExist:
        # Create email account if it doesn't exist
        try:
            provider = EmailProvider.get_provider_for_email(request.user.email)
            EmailAccount.objects.create(
                employee=request.user.employee_profile,
                email_address=request.user.email,
                provider=provider,
                username=request.user.email,
                is_active=False
            )
            messages.info(request, "Email account created. Please activate it by entering your password.")
            return redirect('activate_email_account')
        except Exception as e:
            logger.error(f"Error creating email account: {str(e)}")
            messages.error(request, "Error setting up email account. Please contact support.")
            return redirect('dashboard')


@login_required
def email_account_delete(request, pk):
    """View for deleting an email account"""
    email_account = get_object_or_404(EmailAccount, pk=pk, employee=request.user.employee_profile)

    if request.method == 'POST':
        email_account.delete()
        messages.success(request, 'Email account deleted successfully!')
        return redirect('email_account_list')

    return render(request, 'core/email_account_confirm_delete.html', {'email_account': email_account})


@login_required
def email_account_list(request):
    """List all email accounts for the logged-in employee"""
    email_accounts = EmailAccount.objects.filter(employee=request.user.employee_profile)
    return render(request, 'core/email_account_list.html', {'email_accounts': email_accounts})

@login_required
def compose_email(request):
    """Compose and send a new email"""
    employee = request.user.employee_profile

    # Check if email account exists and needs activation
    try:
        email_account = employee.email_account
        if not email_account.is_active:
            messages.info(request, "Please activate your email account to send emails.")
            return redirect('activate_email_account')
    except EmailAccount.DoesNotExist:
        provider = EmailProvider.get_provider_for_email(employee.user.email)
        EmailAccount.objects.create(
            employee=employee,
            email_address=employee.user.email,
            provider=provider,
            username=employee.user.email,
            is_active=False
        )
        messages.info(request, "Please activate your email account to send emails.")
        return redirect('activate_email_account')

    context = {
        'form': None,
        'reply_to': request.GET.get('reply_to'),
        'forward': request.GET.get('forward'),
        'customer_id': request.GET.get('customer'),
        'lead_id': request.GET.get('lead')
    }

    if request.method == 'POST':
        form = EmailComposeForm(request.POST, request.FILES)
        files = request.FILES.getlist('attachments')

        if form.is_valid():
            try:
                with transaction.atomic():
                    email_message = form.save(commit=False)
                    email_message.account = email_account
                    email_message.from_email = email_account.email_address
                    email_message.message_type = 'outgoing'
                    email_message.message_id = uuid.uuid4()

                    # Convert email fields from string to lists
                    email_message.to_emails = [email.strip() for email in request.POST.get('to_emails', '').split(',') if email.strip()]
                    email_message.cc_emails = [email.strip() for email in request.POST.get('cc_emails', '').split(',') if email.strip()]
                    email_message.bcc_emails = [email.strip() for email in request.POST.get('bcc_emails', '').split(',') if email.strip()]

                    # Ensure at least one recipient exists
                    if not email_message.to_emails:
                        messages.error(request, "At least one recipient (To) is required.")
                        return render(request, 'core/email_compose.html', {'form': form})

                    # Handle related entities
                    if context['customer_id']:
                        email_message.related_customer = get_object_or_404(Customer, id=context['customer_id'])
                    if context['lead_id']:
                        email_message.related_lead = get_object_or_404(Lead, id=context['lead_id'])

                    # Save the email message first
                    email_message.save()

                    # Handle attachments separately
                    for file in files:
                        EmailAttachment.objects.create(
                            email=email_message,
                            file=file,
                            filename=file.name,
                            content_type=file.content_type,
                            size=file.size
                        )

                    # Handle scheduled sending
                    if form.cleaned_data.get('schedule_send'):
                        email_message.status = 'scheduled'
                        email_message.scheduled_time = form.cleaned_data.get('scheduled_time')
                        email_message.save()
                        messages.success(request, f"Email scheduled for {email_message.scheduled_time}")
                    else:
                        # Send email immediately
                        try:
                            with smtplib.SMTP(email_account.smtp_server, email_account.smtp_port) as server:
                                server.starttls()
                                server.login(email_account.username, email_account.password)

                                # Create email message
                                msg = MIMEMultipart('alternative')
                                msg['Subject'] = email_message.subject
                                msg['From'] = email_message.from_email
                                msg['To'] = ', '.join(email_message.to_emails)
                                if email_message.cc_emails:
                                    msg['Cc'] = ', '.join(email_message.cc_emails)

                                # Add text and HTML parts
                                msg.attach(MIMEText(email_message.body_text, 'plain'))
                                if email_message.body_html:
                                    msg.attach(MIMEText(email_message.body_html, 'html'))

                                # Add attachments
                                for file in files:
                                    part = MIMEBase('application', 'octet-stream')
                                    part.set_payload(file.read())
                                    encoders.encode_base64(part)
                                    part.add_header(
                                        'Content-Disposition',
                                        f'attachment; filename="{file.name}"'
                                    )
                                    msg.attach(part)

                                # Send email
                                recipients = email_message.to_emails
                                if email_message.cc_emails:
                                    recipients.extend(email_message.cc_emails)
                                if email_message.bcc_emails:
                                    recipients.extend(email_message.bcc_emails)

                                server.send_message(msg)

                                # Update email status
                                email_message.status = 'sent'
                                email_message.sent_at = timezone.now()
                                email_message.save()

                                # Create sent folder if it doesn't exist
                                sent_folder, _ = EmailFolder.objects.get_or_create(
                                    account=email_account,
                                    name='Sent',
                                    system_type='sent',
                                    is_system=True
                                )

                                # Add message to sent folder
                                EmailFolderMessage.objects.create(
                                    folder=sent_folder,
                                    message=email_message
                                )

                                messages.success(request, "Email sent successfully!")
                                return redirect('email_inbox')

                        except Exception as e:
                            email_message.status = 'failed'
                            email_message.save()
                            messages.error(request, f"Failed to send email: {str(e)}")
                            return render(request, 'core/email_compose.html', {'form': form})

            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, 'core/email_compose.html', {'form': form})
    else:
        initial = {}

        if context['reply_to'] or context['forward']:
            try:
                original_email = EmailMessage.objects.get(message_id=context['reply_to'] or context['forward'])
                initial['subject'] = f"{'Re: ' if context['reply_to'] else 'Fwd: '}{original_email.subject}"
                initial['to_emails'] = original_email.from_email if context['reply_to'] else ''
                initial['body_text'] = f"\n\n{'On ' + original_email.created_at.strftime('%Y-%m-%d %H:%M') + ' ' + original_email.from_email + ' wrote:' if context['reply_to'] else 'Forwarded message:'}\n> " + original_email.body_text.replace('\n', '\n> ')
            except EmailMessage.DoesNotExist:
                messages.error(request, "Original email not found.")

        if context['customer_id']:
            customer = get_object_or_404(Customer, id=context['customer_id'])
            initial['to_emails'] = customer.email

        if context['lead_id']:
            lead = get_object_or_404(Lead, id=context['lead_id'])
            initial['to_emails'] = lead.email

        form = EmailComposeForm(initial=initial)

    return render(request, 'core/email_compose.html', {'form': form})



@login_required
def view_email(request, message_id):
    """View email details"""
    user = request.user

    # Ensure user has an Employee profile
    if not hasattr(user, 'employee_profile'):
        messages.error(request, "No employee profile found for this user.")
        return redirect('dashboard')

    employee = user.employee_profile

    # Ensure Employee has an EmailAccount
    if not hasattr(employee, 'email_account'):
        messages.error(request, "No email account found for this employee.")
        return redirect('dashboard')

    email_account = employee.email_account

    email_message = get_object_or_404(
        EmailMessage,
        message_id=message_id,
        account=email_account
    )

    if not email_message.is_read:
        email_message.is_read = True
        email_message.read_at = timezone.now()
        email_message.save()

    return render(request, 'core/view_email.html', {
        'email': email_message,
        'thread': EmailMessage.objects.filter(thread_id=email_message.thread_id).order_by('created_at')
    })


@login_required
def reply_email(request, message_id):
    """Reply to an email with attachment support"""
    user = request.user

    # Ensure user has an Employee profile
    if not hasattr(user, 'employee_profile'):
        messages.error(request, "No employee profile found for this user.")
        return redirect('dashboard')

    employee = user.employee_profile

    # Ensure Employee has an EmailAccount
    if not hasattr(employee, 'email_account'):
        messages.error(request, "No email account found for this employee.")
        return redirect('dashboard')

    email_account = employee.email_account

    original_email = get_object_or_404(
        EmailMessage,
        message_id=message_id,
        account=email_account
    )

    if request.method == 'POST':
        form = EmailComposeForm(request.POST, request.FILES)
        files = request.FILES.getlist('attachments')  # ✅ Get multiple file attachments

        if form.is_valid():
            reply = form.save(commit=False)
            reply.account = email_account
            reply.from_email = email_account.email_address
            reply.message_type = 'outgoing'
            reply.thread_id = original_email.thread_id or original_email.message_id
            reply.in_reply_to = original_email
            reply.message_id = uuid.uuid4()  # ✅ Ensure a unique message ID

            # ✅ Save email before handling attachments
            reply.save()

            # ✅ Save attachments
            for file in files:
                EmailAttachment.objects.create(
                    email=reply,
                    file=file,
                    filename=file.name,
                    content_type=file.content_type,
                    size=file.size
                )

            try:
                # ✅ Call the function to send the email
                send_email_message(reply)
                reply.status = 'sent'
                reply.sent_at = timezone.now()
                reply.save()
                messages.success(request, 'Reply sent successfully.')
            except Exception as e:
                messages.error(request, f'Failed to send reply: {str(e)}')

            return redirect('view_email', message_id=message_id)

    else:
        # ✅ Prepopulate form fields with original email data
        quoted_body_text = original_email.body_text.replace('\n', '\n> ')
        form = EmailComposeForm(initial={
            'subject': f"Re: {original_email.subject}",
            'body_text': f"\n\nOn {original_email.created_at.strftime('%Y-%m-%d %H:%M')} {original_email.from_email} wrote:\n> {quoted_body_text}"
})

    return render(request, 'core/reply_email.html', {
        'form': form,
        'original_email': original_email
    })


class SentMailView(LoginRequiredMixin, ListView):
    """Display sent emails"""
    model = EmailMessage
    template_name = 'core/email_sent.html'
    context_object_name = 'emails'
    paginate_by = 20

    def get_queryset(self):
        try:
            account = self.request.user.employee_profile.email_account
            return EmailMessage.objects.filter(
                account=account,
                message_type='outgoing',
                is_archived=False
            ).order_by('-created_at')
        except EmailAccount.DoesNotExist:
            messages.error(self.request, "No email account found.")
            return EmailMessage.objects.none()

class DeletedMailView(LoginRequiredMixin, ListView):
    """Display deleted (trashed) emails"""
    model = EmailMessage
    template_name = 'core/email_deleted.html'
    context_object_name = 'emails'
    paginate_by = 20

    def get_queryset(self):
        try:
            account = self.request.user.employee_profile.email_account
            return EmailMessage.objects.filter(
                account=account,
                is_archived=True  # Marked as deleted
            ).order_by('-created_at')
        except EmailAccount.DoesNotExist:
            messages.error(self.request, "No email account found.")
            return EmailMessage.objects.none()

class EmailThreadView(LoginRequiredMixin, ListView):
    """Display an email thread"""
    model = EmailMessage
    template_name = 'core/email_thread.html'
    context_object_name = 'emails'

    def get_queryset(self):
        message_id = self.kwargs.get('message_id')
        original_email = get_object_or_404(EmailMessage, message_id=message_id)
        return EmailMessage.objects.filter(
            thread_id=original_email.thread_id
        ).order_by('created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_email = get_object_or_404(EmailMessage, message_id=self.kwargs.get('message_id'))
        context['original_email'] = original_email
        return context



logger = logging.getLogger(__name__)

class IntegratedBillingDashboardView(LoginRequiredMixin, TemplateView):
    """
    Integrated dashboard showing all billing-related information in one place
    """
    template_name = 'core/integrated_billing_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Get invoices that are not paid, matching your working InvoiceListView
            invoices = Invoice.objects.exclude(status='paid').order_by('-issue_date')

            # Get payments - matching your working PaymentListView
            payments = Payment.objects.all().order_by('-transaction_date')[:10]

            # Get active subscriptions - ServiceSubscription has is_active field
            subscriptions = ServiceSubscription.objects.filter(is_active=True).order_by('-start_date')

            # Add all data to context
            context.update({
                'invoices': invoices,
                'payments': payments,
                'subscriptions': subscriptions
            })

        except Exception as e:
            logger.error(f"Error loading billing dashboard data: {str(e)}")
            messages.error(self.request, f"Error loading billing data: {str(e)}")
            context.update({
                'invoices': [],
                'payments': [],
                'subscriptions': []
            })

        return context

@csrf_exempt
def update_invoice_status(request, invoice_id):
    """Update invoice status dynamically via AJAX"""
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, id=invoice_id)
        new_status = request.POST.get('status')

        if new_status in ['paid', 'pending', 'overdue']:
            invoice.status = new_status
            invoice.save()
            return JsonResponse({'success': True, 'new_status': invoice.get_status_display()})
        return JsonResponse({'success': False, 'error': 'Invalid status'})

@csrf_exempt
def process_payment(request):
    """Process payment and update invoice status accordingly"""
    if request.method == 'POST':
        invoice_id = request.POST.get('invoice_id')
        amount = request.POST.get('amount')

        if not invoice_id or not amount:
            return JsonResponse({'success': False, 'error': 'Missing invoice ID or amount'})

        invoice = get_object_or_404(Invoice, id=invoice_id)
        amount = float(amount)  # Convert input to float

        # Ensure valid payment amount
        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid payment amount'})

        # Create the payment entry
        Payment.objects.create(invoice=invoice, amount=amount)

        # Calculate remaining balance
        total_paid = sum(payment.amount for payment in invoice.payment_set.all())
        remaining_balance = invoice.total_amount - total_paid

        # Determine new status
        if remaining_balance <= 0:
            invoice.status = 'paid'
            new_status_display = 'Paid'
        else:
            invoice.status = 'partial'
            new_status_display = 'Partial Payment'

        invoice.save()

        return JsonResponse({
            'success': True,
            'invoice_id': invoice.id,
            'new_status': new_status_display,
            'remaining_balance': remaining_balance
        })

    return JsonResponse({'success': False, 'error': 'Invalid request'})


logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

@csrf_exempt  # Temporarily exempt from CSRF to test functionality
@require_POST
def process_payment_ajax(request):
    """Handles payment processing via AJAX."""
    invoice_id = request.POST.get('invoice_id')
    amount = request.POST.get('amount')
    payment_method = request.POST.get('payment_method', 'online')  # Default method

    if not invoice_id or not amount:
        return JsonResponse({'success': False, 'error': 'Missing required fields: invoice ID or amount'})

    try:
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        customer = invoice.customer

        # Convert amount to Decimal to match Django's model fields
        amount = Decimal(amount)

        # Validate amount
        if amount <= Decimal('0'):
            return JsonResponse({'success': False, 'error': 'Invalid payment amount.'})

        # Get balance due using the property from your model
        balance_due = invoice.balance_due

        if amount > balance_due:
            return JsonResponse({'success': False, 'error': f"Payment exceeds outstanding balance of ${balance_due:.2f}!"})

        with transaction.atomic():
            # Generate reference number with timestamp
            reference_number = f"PAY-{invoice.invoice_number}-{int(time.time())}"

            # Create payment record - using fields that match your model and PaymentCreateView
            payment = Payment.objects.create(
                customer=customer,
                invoice=invoice,
                amount=amount,
                status='completed',  # Status used in your PaymentCreateView
                payment_method=payment_method,
                transaction_date=timezone.now()
            )

            # Create transaction record - following your PaymentCreateView example
            Transaction.objects.create(
                customer=customer,
                invoice=invoice,
                payment=payment,
                transaction_type='invoice_payment',
                amount=amount,
                reference=reference_number,
                status='completed'
            )

            # Update invoice status - using Decimal for calculations
            remaining_balance = invoice.balance_due - amount

            if remaining_balance <= Decimal('0'):
                invoice.status = 'paid'
                status_label = "Paid"
            else:
                invoice.status = 'partial'
                status_label = "Partial Payment"

            invoice.save()

        # Convert to float for JSON serialization
        remaining_balance_float = float(remaining_balance)

        return JsonResponse({
            'success': True,
            'invoice_id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'new_status': status_label,
            'remaining_balance': remaining_balance_float,
            'payment_reference': reference_number
        })

    except Invoice.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invoice not found'})
    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Invalid amount format: {str(e)}'})
    except Exception as e:
        # Log the error
        logger.error(f"Payment processing error for invoice {invoice_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f"An error occurred: {str(e)}"})

@login_required
def chat_sessions_api(request):
    """API endpoint to get chat sessions for AJAX updates"""
    current_employee = request.user.employee_profile

    # Get all chat sessions for the current user with annotations
    chat_sessions = ChatSession.objects.filter(
        participants=current_employee
    ).annotate(
        unread_count=Count(
            'messages',
            filter=Q(
                messages__is_read=False,
                messages__receiver=current_employee
            )
        )
    ).prefetch_related(
        'participants',
        'participants__user',
        'messages'
    ).order_by('-updated_at')

    # Get the latest message for each session
    for session in chat_sessions:
        session.last_message = session.messages.order_by('-timestamp').first()
        # Get other participant
        session.other_participant = session.participants.exclude(id=current_employee.id).first()

    # Render just the chat list part as HTML
    html = render_to_string('chat/includes/chat_list.html', {
        'chat_sessions': chat_sessions,
        'request': request
    })

    return JsonResponse({
        'html': html,
        'count': chat_sessions.count()
    })




def websocket_test(request):
    return render(request, 'websocket_test.html')


@csrf_exempt
def add_user_to_chat(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            session = ChatSession.objects.get(id=data["session_id"])
            new_user = Employee.objects.get(employee_id=data["user_id"])

            session.participants.add(new_user)
            return JsonResponse({"success": True})

        except ChatSession.DoesNotExist:
            return JsonResponse({"success": False, "error": "Chat session not found"})
        except Employee.DoesNotExist:
            return JsonResponse({"success": False, "error": "User not found"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request"})


@login_required
def leave_chat(request, session_id):
    """
    Allow a user to leave a chat session.
    """
    try:
        # Get the employee profile for the current user
        employee = Employee.objects.get(user=request.user)

        # Get the chat session
        session = get_object_or_404(ChatSession, id=session_id)

        # Check if user is a participant
        if employee not in session.participants.all():
            return JsonResponse({
                "success": False,
                "error": "You are not a participant in this chat."
            })

        # For group chats, simply remove the user
        if session.is_group_chat:
            session.participants.remove(employee)

            # If no participants remain, mark the chat as inactive
            if session.participants.count() == 0:
                session.is_active = False
                session.save()

            # Add system message about user leaving
            user_name = employee.get_full_name()
            system_message = f"{user_name} has left the chat."

            # Log the action
            logger.info(f"User {employee.employee_id} left chat session {session_id}")

            return JsonResponse({"success": True, "message": system_message})
        else:
            # For direct chats, we can either mark it as inactive or disallow leaving
            # Here we'll disallow leaving direct chats
            return JsonResponse({
                "success": False,
                "error": "You cannot leave direct chat sessions. Please delete the conversation instead."
            })

    except Employee.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Employee profile not found for this user."
        })
    except Exception as e:
        logger.error(f"Error in leave_chat view: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": f"An error occurred: {str(e)}"
        })


@login_required
def notifications_list(request):
    """
    View for displaying all notifications
    """
    # Get notifications for the current user
    notifications = GeneralNotifier.objects.filter(
        user=request.user
    ).order_by('-event_datetime')

    # Group by read status
    unread_notifications = notifications.filter(is_read=False, is_dismissed=False)
    read_notifications = notifications.filter(is_read=True, is_dismissed=False)
    dismissed_notifications = notifications.filter(is_dismissed=True)

    return render(request, 'core/notifications_list.html', {
        'unread_notifications': unread_notifications,
        'read_notifications': read_notifications,
        'dismissed_notifications': dismissed_notifications
    })

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    Mark a single notification as read
    """
    notification = get_object_or_404(GeneralNotifier, id=notification_id, user=request.user)
    notification.mark_as_read()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    return redirect('notifications_list')

@login_required
@require_POST
def mark_all_read(request):
    """
    Mark all notifications as read
    """
    GeneralNotifier.objects.filter(
        user=request.user,
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now()
    )

    # Check if this is an AJAX request (modern way)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    return redirect('notifications_list')

@login_required
@require_POST
def dismiss_notification(request, notification_id):
    """
    Dismiss a notification
    """
    notification = get_object_or_404(GeneralNotifier, id=notification_id, user=request.user)
    notification.dismiss()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})

    return redirect('notifications_list')

@login_required
def get_notifications_json(request):
    """
    Get notifications as JSON for AJAX updates
    """
    unread_notifications = GeneralNotifier.objects.filter(
        user=request.user,
        is_read=False,
        is_dismissed=False
    ).order_by('event_datetime')

    # Convert notifications to JSON-serializable format
    notifications_data = []
    for notification in unread_notifications:
        # Calculate time left until event
        time_left = None
        urgency_class = ''

        if notification.event_datetime > timezone.now():
            delta = notification.event_datetime - timezone.now()
            minutes = delta.total_seconds() / 60

            if minutes <= 5:
                time_left = "In less than 5 minutes"
                urgency_class = 'immediate'
            elif minutes <= 30:
                time_left = "In less than 30 minutes"
                urgency_class = 'very-soon'
            elif minutes <= 60:
                time_left = "In less than an hour"
                urgency_class = 'soon'
            elif minutes <= 1440:  # 24 hours
                hours = round(minutes / 60)
                time_left = f"In about {hours} hour{'s' if hours != 1 else ''}"
                urgency_class = 'today'
            else:
                days = round(minutes / 1440)
                time_left = f"In about {days} day{'s' if days != 1 else ''}"
                urgency_class = 'upcoming'
        else:
            time_left = "Now"
            urgency_class = 'immediate'

        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'type': notification.notification_type,
            'priority': notification.priority,
            'time_left': time_left,
            'urgency_class': urgency_class,
            'action_url': notification.action_url
        })

    # Calculate notification counts by type and urgency
    notification_counts = {
        'total': unread_notifications.count(),
        'meeting': unread_notifications.filter(notification_type='meeting').count(),
        'task': unread_notifications.filter(notification_type='task').count(),
        'event': unread_notifications.filter(notification_type='event').count(),
        'document': unread_notifications.filter(notification_type='document').count(),
        'video_conference': unread_notifications.filter(notification_type='video_conference').count(),
        'deadline': unread_notifications.filter(notification_type='deadline').count(),
        'other': unread_notifications.filter(notification_type='other').count(),
        'immediate': sum(1 for n in notifications_data if n['urgency_class'] == 'immediate'),
        'very_soon': sum(1 for n in notifications_data if n['urgency_class'] == 'very-soon'),
        'soon': sum(1 for n in notifications_data if n['urgency_class'] == 'soon'),
    }

    return JsonResponse({
        'notifications': notifications_data,
        'counts': notification_counts
    })


def cookie_policy(request):
    return render(request, 'core/cookie_policy.html')

def privacy_policy(request):
    return render(request, 'core/privacy_policy.html')


@login_required
def employee_diagnostic(request):
    """Diagnostic view to check employee availability"""
    try:
        # Get current employee
        # Try all possible ways to get the employee
        employee_from_profile = None
        employee_from_employee = None
        current_employee = None

        if hasattr(request.user, 'employee_profile'):
            employee_from_profile = request.user.employee_profile

        if hasattr(request.user, 'employee_employee'):
            employee_from_employee = request.user.employee_employee

        # Determine which one to use
        if employee_from_profile:
            current_employee = employee_from_profile
            employee_source = "employee_profile"
        elif employee_from_employee:
            current_employee = employee_from_employee
            employee_source = "employee_employee"
        else:
            # Try direct query
            try:
                current_employee = Employee.objects.get(user=request.user)
                employee_source = "direct_query"
            except Employee.DoesNotExist:
                employee_source = "none_found"

        # Get all employees
        all_employees = Employee.objects.all()

        # Try different query approaches
        employees_exclude_id = []
        employees_exclude_user = []
        employees_exclude_employee_id = []

        if current_employee:
            # By ID
            employees_exclude_id = Employee.objects.exclude(id=current_employee.id)

            # By User
            if hasattr(current_employee, 'user') and current_employee.user:
                employees_exclude_user = Employee.objects.exclude(user=current_employee.user)

            # By employee_id
            if hasattr(current_employee, 'employee_id'):
                employees_exclude_employee_id = Employee.objects.exclude(employee_id=current_employee.employee_id)

        # Return the diagnostic info
        return JsonResponse({
            'status': 'success',
            'user_id': request.user.id,
            'username': request.user.username,
            'employee_source': employee_source,
            'current_employee': {
                'id': current_employee.id if current_employee else None,
                'employee_id': current_employee.employee_id if current_employee and hasattr(current_employee, 'employee_id') else None,
                'user_id': current_employee.user.id if current_employee and hasattr(current_employee, 'user') else None,
                'is_active': current_employee.is_active if current_employee and hasattr(current_employee, 'is_active') else None,
                'attributes': dir(current_employee) if current_employee else []
            },
            'counts': {
                'all_employees': all_employees.count(),
                'exclude_id': len(employees_exclude_id),
                'exclude_user': len(employees_exclude_user),
                'exclude_employee_id': len(employees_exclude_employee_id),
            },
            'employees': [
                {
                    'id': emp.id,
                    'employee_id': emp.employee_id if hasattr(emp, 'employee_id') else None,
                    'username': emp.user.username if hasattr(emp, 'user') else None,
                    'is_active': emp.is_active if hasattr(emp, 'is_active') else None,
                }
                for emp in all_employees[:10]  # First 10 for brevity
            ]
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        })


@login_required
def calendar_employee_debug(request):
    """Standalone debug view to test employee selection"""

    # Get current employee
    try:
        current_employee = request.user.employee_profile
    except:
        try:
            current_employee = Employee.objects.get(user=request.user)
        except:
            current_employee = None

    # Get all employees (no filtering)
    all_employees = Employee.objects.all()

    # Get available employees (all employees excluding current)
    if current_employee:
        available_employees = Employee.objects.exclude(id=current_employee.id)
    else:
        available_employees = Employee.objects.all()

    # Prepare the context
    context = {
        'current_employee': current_employee,
        'all_employees': all_employees,
        'available_employees': available_employees,
        'employee_count': available_employees.count(),
    }

    # Render a minimal template
    return render(request, 'core/employee_debug.html', context)


# @login_required
# def minimal_calendar_view(request):
#     """Enhanced minimal calendar view with scheduling functionality"""

#     # Get current employee directly from request.user (PRESERVED)
#     try:
#         current_employee = request.user.employee_profile
#     except:
#         try:
#             current_employee = Employee.objects.get(user=request.user)
#         except:
#             messages.error(request, "You don't have an employee profile")
#             return redirect('dashboard')

#     # Get all active employees except current user
#     available_employees = Employee.objects.exclude(id=current_employee.id).filter(is_active=True)

#     # Get schedule rule information
#     schedule_rules = ScheduleRule.objects.filter(
#         user=request.user,
#         is_active=True
#     )

#     # Format rule information for display
#     rule_info = []
#     for rule in schedule_rules:
#         rule_info.append({
#             'name': rule.name,
#             'recurrence': rule.get_recurrence_type_display(),
#             'time_range': f"{rule.start_time.strftime('%I:%M %p')} - {rule.end_time.strftime('%I:%M %p')}",
#             'day_info': _get_rule_day_info(rule),
#             'buffer': f"{rule.buffer_before} min before, {rule.buffer_after} min after"
#         })

#     # Add scheduling service data if available
#     try:
#         from .scheduling_service import SchedulingService
#         scheduling_service = SchedulingService(request.user)

#         # Get availability for today
#         today = timezone.now().date()
#         availability_data = {
#             'today': scheduling_service.get_availability(today)
#         }

#         # Get suggested meeting slots
#         available_slots = []
#         for duration in [30, 60]:
#             next_start, next_end = scheduling_service.get_next_available_slot(
#                 from_datetime=timezone.now(),
#                 duration_minutes=duration
#             )

#             if next_start and next_end:
#                 available_slots.append({
#                     'duration': duration,
#                     'start': next_start,
#                     'end': next_end,
#                     'label': f"{duration} min at {next_start.strftime('%I:%M %p')} on {next_start.strftime('%b %d')}"
#                 })

#     except Exception as e:
#         logger.error(f"Error getting scheduling data: {str(e)}")
#         availability_data = {}
#         available_slots = []

#     if request.method == 'POST':
#         action = request.POST.get('action')

#         if action == 'suggest_meeting':
#             # Get selected employees and duration
#             employee_ids = request.POST.getlist('employees')
#             duration = int(request.POST.get('duration', 60))  # Default to 1 hour

#             if not employee_ids:
#                 messages.error(request, "Please select at least one participant")
#                 return redirect('minimal_calendar')

#             # Get Employee objects for selected IDs
#             selected_employees = Employee.objects.filter(id__in=employee_ids)

#             # Find optimal time for all participants
#             try:
#                 from .scheduling_service import SchedulingService
#                 scheduling_service = SchedulingService(request.user)

#                 # Find optimal time for all participants
#                 suggestion = scheduling_service.suggest_meeting_time(
#                     participants=list(selected_employees) + [current_employee],
#                     duration_minutes=duration,
#                     within_days=7
#                 )

#                 # If successful, redirect to meeting creation
#                 if suggestion.get('success'):
#                     start_datetime = suggestion['start_datetime']
#                     end_datetime = suggestion['end_datetime']

#                     # Format for URL
#                     start_str = start_datetime.strftime('%Y-%m-%dT%H:%M')
#                     end_str = end_datetime.strftime('%Y-%m-%dT%H:%M')

#                     # Create attendee param string for all selected employees
#                     attendee_params = '&'.join([f'attendees={emp_id}' for emp_id in employee_ids])

#                     # Success message
#                     messages.success(
#                         request,
#                         f"Found optimal time: {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%H:%M')}"
#                     )

#                     # Redirect to meeting creation with suggested time and attendees
#                     return redirect(f'/meetings/create/?start_time={start_str}&end_time={end_str}&{attendee_params}')
#                 else:
#                     # Could not find a time
#                     error_reason = suggestion.get('reason', 'No available time slots found')
#                     messages.warning(request, f"Could not find a time that works for all participants: {error_reason}")
#             except ImportError:
#                 messages.error(request, "Scheduling service not available")
#             except Exception as e:
#                 logger.error(f"Error suggesting meeting time: {str(e)}")
#                 messages.error(request, f"Error finding optimal meeting time: {str(e)}")

#             return redirect('minimal_calendar')

#         elif action == 'availability_check':
#             # Handle availability check form
#             date_str = request.POST.get('date')
#             start_time_str = request.POST.get('start_time')
#             duration = int(request.POST.get('duration', 60))

#             try:
#                 # Parse date and time
#                 date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
#                 start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()

#                 # Combine to create datetime
#                 start_datetime = timezone.make_aware(datetime.combine(date_obj, start_time_obj))
#                 end_datetime = start_datetime + timedelta(minutes=duration)

#                 # Check availability using scheduling service
#                 scheduling_service = SchedulingService(request.user)
#                 is_available = scheduling_service.check_availability(
#                     start_datetime,
#                     end_datetime,
#                     duration
#                 )

#                 if is_available:
#                     messages.success(request, f"Time slot is available on {date_str} at {start_time_str}")
#                 else:
#                     # Get next available slot
#                     next_start, next_end = scheduling_service.get_next_available_slot(
#                         from_datetime=start_datetime,
#                         duration_minutes=duration
#                     )

#                     if next_start and next_end:
#                         messages.warning(
#                             request,
#                             f"Selected time is not available. Next available: {next_start.strftime('%Y-%m-%d %H:%M')}"
#                         )
#                     else:
#                         messages.error(request, "Selected time is not available and no alternative found")
#             except ValueError:
#                 messages.error(request, "Invalid date or time format")
#             except Exception as e:
#                 logger.error(f"Error checking availability: {str(e)}")
#                 messages.error(request, f"Error checking availability: {str(e)}")

#             return redirect('minimal_calendar')

#     # Comprehensive context with all required data
#     context = {
#         'current_employee': current_employee,
#         'available_employees': available_employees,
#         'employee_count': available_employees.count(),
#         'schedule_rules': rule_info,
#         'availability_data': availability_data,
#         'available_slots': available_slots,
#         'today': timezone.now().date(),
#     }

#     # Render the minimal template with enhanced context
#     return render(request, 'core/minimal_calendar.html', context)

# # Helper function for formatting rule day info (moved outside the view)
# def _get_rule_day_info(rule):
#     """Format day information for a schedule rule"""
#     if rule.recurrence_type == 'daily':
#         return "Every day"
#     elif rule.recurrence_type == 'weekly':
#         return f"Every {rule.get_day_of_week_display()}"
#     elif rule.recurrence_type == 'monthly':
#         return f"Day {rule.day_of_month} of each month"
#     elif rule.recurrence_type == 'yearly':
#         return f"{rule.get_month_display()} {rule.day_of_month}"
#     return ""


@login_required
def minimal_calendar_view(request):
    """Enhanced minimal calendar view with scheduling functionality"""

    # Get current employee directly from request.user (PRESERVED)
    try:
        current_employee = request.user.employee_profile
    except:
        try:
            current_employee = Employee.objects.get(user=request.user)
        except:
            messages.error(request, "You don't have an employee profile")
            return redirect('dashboard')

    # Get all active employees except current user
    available_employees = Employee.objects.exclude(id=current_employee.id).filter(is_active=True)

    # Get schedule rule information
    schedule_rules = ScheduleRule.objects.filter(
        user=request.user,
        is_active=True
    )

    # Format rule information for display
    rule_info = []
    for rule in schedule_rules:
        rule_info.append({
            'name': rule.name,
            'recurrence': rule.get_recurrence_type_display(),
            'time_range': f"{rule.start_time.strftime('%I:%M %p')} - {rule.end_time.strftime('%I:%M %p')}",
            'day_info': _get_rule_day_info(rule),
            'buffer': f"{rule.buffer_before} min before, {rule.buffer_after} min after"
        })

    # Add scheduling service data if available
    try:
        from .scheduling_service import SchedulingService
        scheduling_service = SchedulingService(request.user)

        # Get availability for today
        today = timezone.now().date()
        availability_data = {
            'today': scheduling_service.get_availability(today)
        }

        # Get suggested meeting slots
        available_slots = []
        for duration in [30, 60]:
            next_start, next_end = scheduling_service.get_next_available_slot(
                from_datetime=timezone.now(),
                duration_minutes=duration
            )

            if next_start and next_end:
                available_slots.append({
                    'duration': duration,
                    'start': next_start,
                    'end': next_end,
                    'label': f"{duration} min at {next_start.strftime('%I:%M %p')} on {next_start.strftime('%b %d')}"
                })

    except Exception as e:
        logger.error(f"Error getting scheduling data: {str(e)}")
        availability_data = {}
        available_slots = []

    # Create forms for calendar imports
    from django import forms

    class IcsUploadForm(forms.Form):
        ics_file = forms.FileField(label="Select ICS file")

    class GoogleCalendarForm(forms.Form):
        pass  # Google auth will be handled by the view

    class UniversalCalendarForm(forms.Form):
        calendar_url = forms.URLField(label="Calendar URL (iCal/WebCal)")
        provider = forms.ChoiceField(
            choices=[
                ('', 'Select Provider'),
                ('outlook', 'Outlook'),
                ('ical', 'Apple iCalendar'),
                ('yahoo', 'Yahoo Calendar'),
                ('other', 'Other')
            ],
            required=True
        )

    ics_form = IcsUploadForm()
    google_form = GoogleCalendarForm()
    universal_form = UniversalCalendarForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        # Original functionality preserved
        if action == 'suggest_meeting':
            # Get selected employees and duration
            employee_ids = request.POST.getlist('employees')
            duration = int(request.POST.get('duration', 60))  # Default to 1 hour

            if not employee_ids:
                messages.error(request, "Please select at least one participant")
                return redirect('calendar')

            # Get Employee objects for selected IDs
            selected_employees = Employee.objects.filter(id__in=employee_ids)

            # Find optimal time for all participants
            try:
                from .scheduling_service import SchedulingService
                scheduling_service = SchedulingService(request.user)

                # Find optimal time for all participants
                suggestion = scheduling_service.suggest_meeting_time(
                    participants=list(selected_employees) + [current_employee],
                    duration_minutes=duration,
                    within_days=7
                )

                # If successful, redirect to meeting creation
                if suggestion.get('success'):
                    start_datetime = suggestion['start_datetime']
                    end_datetime = suggestion['end_datetime']

                    # Format for URL
                    start_str = start_datetime.strftime('%Y-%m-%dT%H:%M')
                    end_str = end_datetime.strftime('%Y-%m-%dT%H:%M')

                    # Create attendee param string for all selected employees
                    attendee_params = '&'.join([f'attendees={emp_id}' for emp_id in employee_ids])

                    # Success message
                    messages.success(
                        request,
                        f"Found optimal time: {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%H:%M')}"
                    )

                    # Redirect to meeting creation with suggested time and attendees
                    return redirect(f'/meetings/create/?start_time={start_str}&end_time={end_str}&{attendee_params}')
                else:
                    # Could not find a time
                    error_reason = suggestion.get('reason', 'No available time slots found')
                    messages.warning(request, f"Could not find a time that works for all participants: {error_reason}")
            except ImportError:
                messages.error(request, "Scheduling service not available")
            except Exception as e:
                logger.error(f"Error suggesting meeting time: {str(e)}")
                messages.error(request, f"Error finding optimal meeting time: {str(e)}")

            return redirect('calendar')

        elif action == 'availability_check':
            # Handle availability check form
            date_str = request.POST.get('date')
            start_time_str = request.POST.get('start_time')
            duration = int(request.POST.get('duration', 60))

            try:
                # Parse date and time
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()

                # Combine to create datetime
                start_datetime = timezone.make_aware(datetime.combine(date_obj, start_time_obj))
                end_datetime = start_datetime + timedelta(minutes=duration)

                # Check availability using scheduling service
                scheduling_service = SchedulingService(request.user)
                is_available = scheduling_service.check_availability(
                    start_datetime,
                    end_datetime,
                    duration
                )

                if is_available:
                    messages.success(request, f"Time slot is available on {date_str} at {start_time_str}")
                else:
                    # Get next available slot
                    next_start, next_end = scheduling_service.get_next_available_slot(
                        from_datetime=start_datetime,
                        duration_minutes=duration
                    )

                    if next_start and next_end:
                        messages.warning(
                            request,
                            f"Selected time is not available. Next available: {next_start.strftime('%Y-%m-%d %H:%M')}"
                        )
                    else:
                        messages.error(request, "Selected time is not available and no alternative found")
            except ValueError:
                messages.error(request, "Invalid date or time format")
            except Exception as e:
                logger.error(f"Error checking availability: {str(e)}")
                messages.error(request, f"Error checking availability: {str(e)}")

            return redirect('calendar')

        # NEW FUNCTIONALITY: ICS file upload
        elif 'ics_upload' in request.POST:
            ics_form = IcsUploadForm(request.POST, request.FILES)
            if ics_form.is_valid():
                try:
                    from icalendar import Calendar
                    from .models import Meeting  # Import your Meeting model

                    ics_file = request.FILES['ics_file']
                    cal = Calendar.from_ical(ics_file.read())

                    events_imported = 0
                    for component in cal.walk():
                        if component.name == "VEVENT":
                            # Extract event details
                            summary = str(component.get('summary', 'Imported Event'))
                            start_time = component.get('dtstart').dt
                            end_time = component.get('dtend').dt
                            description = str(component.get('description', ''))
                            location = str(component.get('location', ''))

                            # Convert to timezone-aware if datetime objects
                            if isinstance(start_time, datetime) and start_time.tzinfo is None:
                                start_time = timezone.make_aware(start_time)
                            if isinstance(end_time, datetime) and end_time.tzinfo is None:
                                end_time = timezone.make_aware(end_time)

                            # Create meeting object with organizer (not user)
                            Meeting.objects.create(
                                organizer=request.user,
                                title=summary,
                                start_time=start_time,
                                end_time=end_time,
                                description=description,
                                location=location,
                                meeting_type='imported',
                                status='scheduled'
                            )
                            events_imported += 1

                    messages.success(request, f"Successfully imported {events_imported} events from ICS file")
                except Exception as e:
                    logger.error(f"Error importing ICS file: {str(e)}")
                    messages.error(request, f"Error importing ICS file: {str(e)}")
            else:
                messages.error(request, "Invalid form submission")

            return redirect('calendar')

        # NEW FUNCTIONALITY: Google Calendar import
        elif 'import_google_calendar' in request.POST:
            try:
                # Check if we have valid Google credentials
                from .google_calendar_service import get_google_calendar_service

                # Attempt to get the service or redirect to authentication
                service = get_google_calendar_service(request)

                if isinstance(service, str) and service.startswith('http'):
                    # This is a redirect URL for authentication
                    return redirect(service)

                # We have a valid service, fetch events
                from .models import Meeting

                # Get events from primary calendar for next 30 days
                now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
                end_date = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'

                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=now,
                    timeMax=end_date,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()

                events = events_result.get('items', [])
                events_imported = 0

                for event in events:
                    # Extract event details
                    summary = event.get('summary', 'Google Calendar Event')

                    # Handle start time
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    if 'T' in start:  # This is a datetime
                        start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    else:  # This is a date
                        start_time = datetime.strptime(start, '%Y-%m-%d')

                    # Handle end time
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    if 'T' in end:  # This is a datetime
                        end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    else:  # This is a date
                        end_time = datetime.strptime(end, '%Y-%m-%d')

                    # Convert to timezone-aware
                    if start_time.tzinfo is None:
                        start_time = timezone.make_aware(start_time)
                    if end_time.tzinfo is None:
                        end_time = timezone.make_aware(end_time)

                    # Create meeting object with organizer (not user)
                    Meeting.objects.create(
                        organizer=request.user,
                        title=summary,
                        start_time=start_time,
                        end_time=end_time,
                        description=event.get('description', ''),
                        location=event.get('location', ''),
                        meeting_type='google_import',
                        status='scheduled'
                    )
                    events_imported += 1

                messages.success(request, f"Successfully imported {events_imported} events from Google Calendar")

            except Exception as e:
                logger.error(f"Error importing from Google Calendar: {str(e)}")
                messages.error(request, f"Error importing from Google Calendar: {str(e)}")

            return redirect('calendar')

        # NEW FUNCTIONALITY: Universal Calendar import (iCal/WebCal URLs)
        elif 'universal_calendar' in request.POST:
            universal_form = UniversalCalendarForm(request.POST)
            if universal_form.is_valid():
                try:
                    import requests
                    from icalendar import Calendar
                    from .models import Meeting

                    calendar_url = universal_form.cleaned_data['calendar_url']
                    provider = universal_form.cleaned_data['provider']

                    # Fetch the calendar data
                    response = requests.get(calendar_url)
                    if response.status_code != 200:
                        messages.error(request, f"Failed to fetch calendar: HTTP {response.status_code}")
                        return redirect('calendar')

                    # Parse the calendar data
                    cal = Calendar.from_ical(response.content)

                    events_imported = 0
                    for component in cal.walk():
                        if component.name == "VEVENT":
                            # Extract event details
                            summary = str(component.get('summary', f'Imported Event from {provider}'))
                            start_time = component.get('dtstart').dt
                            end_time = component.get('dtend').dt
                            description = str(component.get('description', ''))
                            location = str(component.get('location', ''))

                            # Convert to timezone-aware if datetime objects
                            if isinstance(start_time, datetime) and start_time.tzinfo is None:
                                start_time = timezone.make_aware(start_time)
                            if isinstance(end_time, datetime) and end_time.tzinfo is None:
                                end_time = timezone.make_aware(end_time)

                            # Create meeting object with organizer (not user)
                            Meeting.objects.create(
                                organizer=request.user,
                                title=summary,
                                start_time=start_time,
                                end_time=end_time,
                                description=description,
                                location=location,
                                meeting_type=f'{provider}_import',
                                status='scheduled'
                            )
                            events_imported += 1

                    messages.success(request, f"Successfully imported {events_imported} events from {provider} Calendar")
                except Exception as e:
                    logger.error(f"Error importing calendar from URL: {str(e)}")
                    messages.error(request, f"Error importing calendar: {str(e)}")
            else:
                messages.error(request, "Invalid form submission")

            return redirect('minimal_calendar')

    # Get meetings for display
    from .models import Meeting
    current_date = timezone.now().date()

    # Get user's meetings for the next 30 days
    meetings = Meeting.objects.filter(
        organizer=request.user.employee_profile,  # Changed from user to organizer
        start_time__date__gte=current_date,
        start_time__date__lte=current_date + timedelta(days=30)
    ).order_by('start_time')

    # Comprehensive context with all required data
    context = {
        'current_employee': current_employee,
        'available_employees': available_employees,
        'employee_count': available_employees.count(),
        'schedule_rules': rule_info,
        'availability_data': availability_data,
        'available_slots': available_slots,
        'today': timezone.now().date(),
        'current_date': current_date,
        'meetings': meetings,
        'ics_form': ics_form,
        'google_form': google_form,
        'universal_form': universal_form,
    }

    # Render the minimal template with enhanced context
    return render(request, 'core/minimal_calendar.html', context)

# Helper function for formatting rule day info (moved outside the view)
def _get_rule_day_info(rule):
    """Format day information for a schedule rule"""
    if rule.recurrence_type == 'daily':
        return "Every day"
    elif rule.recurrence_type == 'weekly':
        return f"Every {rule.get_day_of_week_display()}"
    elif rule.recurrence_type == 'monthly':
        return f"Day {rule.day_of_month} of each month"
    elif rule.recurrence_type == 'yearly':
        return f"{rule.get_month_display()} {rule.day_of_month}"
    return ""

def handle_google_callback(request):
    """
    Handle the callback from Google OAuth. Add this to your urls.py:
    path('calendar/google/callback/', views.handle_google_callback, name='google_callback')
    """
    from django.shortcuts import redirect
    from django.contrib import messages

    try:
        # Get the authorization code from the request
        code = request.GET.get('code')
        if not code:
            messages.error(request, "Authorization failed - no code received")
            return redirect('minimal_calendar')

        # Get flow object
        credentials_file = settings.GOOGLE_CALENDAR_CREDENTIALS_FILE
        flow = Flow.from_client_secrets_file(
            credentials_file,
            scopes=['https://www.googleapis.com/auth/calendar.readonly'],
            redirect_uri=request.build_absolute_uri('/calendar/google/callback/')
        )

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Save credentials
        user_token_file = f'token_{request.user.id}.pickle'
        token_path = os.path.join(os.path.dirname(__file__), user_token_file)
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

        # Redirect back to the original page
        redirect_path = request.session.get('calendar_redirect', 'minimal_calendar')

        messages.success(request, "Successfully connected to Google Calendar")
        return redirect(redirect_path)

    except Exception as e:
        messages.error(request, f"Error connecting to Google Calendar: {str(e)}")
        return redirect('calendar')


def authenticated_user_only(user):
    print(f"User: {user}, Authenticated: {user.is_authenticated}")  # Debugging
    return user.is_authenticated



class CalendarViewSimplified(LoginRequiredMixin, TemplateView):
    """
    Simplified calendar view focused only on employee selection
    """
    template_name = 'core/calendar_simplified.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Direct access to employee profile without mixin
            if hasattr(self.request.user, 'employee_profile'):
                current_employee = self.request.user.employee_profile

                # Get all employees except the current one
                all_employees = Employee.objects.all()
                available_employees = Employee.objects.exclude(id=current_employee.id)
                active_employees = Employee.objects.filter(is_active=True)

                # Log all employees for debugging
                for emp in all_employees:
                    print(f"Employee: {emp.id} - {emp.user.username if hasattr(emp, 'user') else 'No user'}")

                # Add data to context
                context.update({
                    'current_employee': current_employee,
                    'all_employees': all_employees,
                    'available_employees': available_employees,
                    'active_employees': active_employees,
                    'employee_count': available_employees.count(),
                })
            else:
                context.update({
                    'error_message': 'No employee profile found',
                    'available_employees': [],
                    'employee_count': 0,
                })

        except Exception as e:
            import traceback
            print(f"Error getting calendar data: {str(e)}")
            print(traceback.format_exc())
            context.update({
                'error_message': str(e),
                'available_employees': [],
                'employee_count': 0,
            })

        return context

@login_required
def get_employees_json(request):
    """API to get employees for a select dropdown"""
    try:
        if hasattr(request.user, 'employee_profile'):
            current_employee = request.user.employee_profile
            available_employees = Employee.objects.exclude(id=current_employee.id).filter(is_active=True)

            employee_list = []
            for emp in available_employees:
                employee_list.append({
                    'id': emp.id,
                    'name': emp.user.get_full_name() or emp.user.username,
                    'employee_id': emp.employee_id
                })

            return JsonResponse({
                'status': 'success',
                'employees': employee_list,
                'count': len(employee_list)
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'No employee profile found',
                'employees': [],
                'count': 0
            })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'employees': [],
            'count': 0
        })

@login_required
def complete_task(request, pk):
    """Mark a task as completed"""
    task = get_object_or_404(Task, pk=pk)

    # Check if the user has permission to complete this task
    # User can complete a task if they are assigned to it or created it
    if request.method == 'POST' or request.method == 'GET':  # Allow both POST and GET for convenience
        # Update the task status
        task.status = 'completed'
        task.save()

        messages.success(request, f'Task "{task.title}" marked as completed.')

        # Redirect back to task list or the referring page
        return redirect(request.META.get('HTTP_REFERER', 'task-list'))

    # If not POST or GET, redirect to task detail page
    return redirect('task-detail', pk=task.pk)


@login_required
def check_uninvoiced_entries(request):
    """API endpoint to check for uninvoiced time entries"""
    customer_id = request.GET.get('customer_id')
    if not customer_id:
        return JsonResponse({'error': 'Customer ID is required'}, status=400)

    try:
        customer = get_object_or_404(Customer, id=customer_id)

        # Check for uninvoiced time entries
        from customer_projects.models import TimeEntry
        from django.db.models import Sum, Count

        uninvoiced_data = TimeEntry.objects.filter(
            is_billable=True,
            is_invoiced=False,
            task__phase__project__customer=customer
        ).aggregate(
            count=Count('id'),
            total_hours=Sum('hours')
        )

        count = uninvoiced_data['count'] or 0
        hours = float(uninvoiced_data['total_hours'] or 0)

        return JsonResponse({
            'has_uninvoiced_entries': count > 0,
            'count': count,
            'hours': hours
        })

    except Exception as e:
        logger.error(f"Error checking uninvoiced entries: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def index(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            name = data.get('name')
            company = data.get('company')
            industry = data.get('industry')
            contact = data.get('contact')
            website = data.get('website', '')
            email_address = data.get('email_address', '')

            # Log the request data (for debugging)
            print(f"Demo Request Received:\nName: {name}\nCompany: {company}\nIndustry: {industry}\nContact: {contact}\nWebsite: {website}\nEmail Address: {email_address}")

            # Send data to Google Sheets
            success = send_to_google_sheets(name, company, industry, contact, website, email_address)

            if success:
                return JsonResponse({'message': 'Demo request received successfully.'})
            else:
                return JsonResponse({'error': 'Failed to save data to Google Sheets'}, status=500)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    # Define all the services for display in the frontend
    services = [
        {
            "name": "Customer Relationship Management (CRM)",
            "description": "Manage leads, interactions, and customer data in one place.",
            "icon": "img/dashboard.jpg"
        },
        {
            "name": "Email",
            "description": "Integrated company-wide email service with smart sorting and filters.",
            "icon": "img/email.png"
        },
        {
            "name": "Project Management",
            "description": "Track projects, assign tasks, set deadlines, and manage progress.",
            "icon": "img/project.png"
        },
        {
            "name": "Document Management",
            "description": "Securely store, edit, and share company documents with access controls.",
            "icon": "img/documents.png"
        },
        {
            "name": "Route Management",
            "description": "Optimize delivery routes and monitor logistics in real-time.",
            "icon": "img/routes.png"
        },
        {
            "name": "Video Conferencing",
            "description": "Hold meetings and collaborate in real-time with built-in video tools.",
            "icon": "img/video.png"
        },
        {
            "name": "Company Chat",
            "description": "Keep teams connected with a streamlined internal chat platform.",
            "icon": "img/chat.png"
        },
        {
            "name": "Customer Onboarding",
            "description": "Guide new customers through onboarding with checklists and automation.",
            "icon": "img/onboarding.png"
        },
    ]

    return render(request, 'core/index.html', {'services': services})

def send_to_google_sheets(name, company, industry, contact, website, email_address):
    try:
        # Path to credentials - better to use environment variable if possible
        # For example: credentials_path = settings.GOOGLE_CREDENTIALS_PATH


        # Define scopes
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

        # Create credentials
        credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_CREDENTIALS_FILE,  # path already stored in settings
            scopes=SCOPES)

        # Build the service
        service = build('sheets', 'v4', credentials=credentials)

        # Your Google Sheet ID - better to store in settings.py or as environment variable
        # For example: SPREADSHEET_ID = settings.GOOGLE_SHEET_ID
        SPREADSHEET_ID = settings.GOOGLE_SHEET_ID

        # The range where data will be added
        RANGE_NAME = 'Sheet1!A:F1'

        # Create the data to be inserted
        values = [[name, company, industry, contact, website, email_address]]
        body = {'values': values}

        # Call the Sheets API to append the data
        result = service.spreadsheets().values().append(
            spreadsheetId=settings.GOOGLE_SHEET_ID,
            range=RANGE_NAME,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body).execute()

        return True
    except Exception as e:
        print(f"Google Sheets Error: {e}")
        return False
