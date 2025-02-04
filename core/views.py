# core/views.py

from django.shortcuts import render, redirect, get_object_or_404
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
import tempfile
import os
from io import BytesIO
from zoomus import ZoomClient
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.urls import reverse_lazy
from decimal import Decimal
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from weasyprint import HTML
import tempfile

from .models import (
    Employee, Customer, Lead, Service, Note, Task, Meeting, Invoice, Payment, Subscription, Transaction, ServiceSubscription
)
from .forms import (
    UserRegistrationForm, EmployeeForm, CustomerForm, LeadForm,
    ServiceForm, NoteForm, TaskForm, MeetingForm,
    MeetingSearchForm, TaskSearchForm, InvoiceForm, PaymentForm, SubscriptionForm, ServiceSubscriptionForm
)

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if user is authenticated
        if not self.request.user.is_authenticated:
            return context

        try:
            employee = self.request.user.employee
        except AttributeError:
            messages.warning(self.request, 'No employee profile found. Please contact an administrator.')
            return context

        # Get today's date
        today = timezone.now().date()

        context.update({
            'total_customers': Customer.objects.filter(assigned_to=employee).count(),
            'total_leads': Lead.objects.filter(assigned_to=employee).count(),
            'upcoming_tasks': Task.objects.filter(
                assigned_to=employee,
                status__in=['pending', 'in_progress'],
                due_date__gte=today
            ).order_by('due_date')[:5],
            'upcoming_meetings': Meeting.objects.filter(
                Q(organizer=employee) | Q(attendees=employee),
                start_time__gte=timezone.now()
            ).order_by('start_time')[:5],
            'recent_notes': Note.objects.filter(
                created_by=employee
            ).order_by('-created_at')[:5],
            'overdue_tasks': Task.objects.filter(
                assigned_to=employee,
                status__in=['pending', 'in_progress'],
                due_date__lt=today
            ).count(),
        })
        return context

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        return super().dispatch(request, *args, **kwargs)

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

    context = {
        'form': form,
        'employee': employee
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

class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'core/customer_detail.html'
    context_object_name = 'customer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.get_object()
        context.update({
            'invoices': customer.invoices.all().order_by('-created_at'),
            'notes': Note.objects.filter(customer=customer).order_by('-created_at'),
            'tasks': Task.objects.filter(customer=customer).order_by('-created_at'),
            'meetings': Meeting.objects.filter(customers=customer).order_by('-start_time'),
        })
        return context

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
            lead.save()

            messages.success(request, 'Lead successfully converted to customer.')
            return redirect('customer-detail', pk=customer.pk)
    else:
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
        form.instance.created_by = self.request.user.employee
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
        user = self.request.user

        # ✅ Check if the user has an employee profile
        if not hasattr(user, 'employee'):
            return Task.objects.none()  # Return empty queryset instead of raising an error

        queryset = Task.objects.filter(
            Q(assigned_to=user.employee) |
            Q(created_by=user.employee)
        )

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
        context.update({
            'status_choices': Task.STATUS_CHOICES,
            'priority_choices': Task.PRIORITY_CHOICES,
            'search_form': TaskSearchForm(self.request.GET)
        })
        return context

class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = 'core/task_detail.html'
    context_object_name = 'task'

class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = reverse_lazy('task-list')

    def form_valid(self, form):
        user = self.request.user

        # ✅ Check if the user has an Employee profile
        if hasattr(user, 'employee'):
            form.instance.created_by = user.employee
        else:
            messages.error(self.request, "Error: You do not have an associated employee profile.")
            return self.form_invalid(form)  # Prevent submission

        messages.success(self.request, 'Task created successfully.')
        return super().form_valid(form)

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
        employee = self.request.user.employee
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

class MeetingCreateView(LoginRequiredMixin, CreateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'core/meeting_form.html'
    success_url = reverse_lazy('meeting-list')

    def form_valid(self, form):
        form.instance.organizer = self.request.user.employee
        response = super().form_valid(form)

        if form.instance.meeting_type == 'zoom':
            # Create Zoom meeting
            try:
                zoom_meeting = create_zoom_meeting(form.instance)
                form.instance.zoom_meeting_id = zoom_meeting['id']
                form.instance.zoom_join_url = zoom_meeting['join_url']
                form.instance.save()
            except Exception as e:
                messages.error(self.request, f'Error creating Zoom meeting: {str(e)}')
                return self.form_invalid(form)

        messages.success(self.request, 'Meeting created successfully.')
        return response

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


class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'core/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee
        today = timezone.now().date()

        # Get upcoming meetings
        meetings = Meeting.objects.filter(
            Q(organizer=employee) | Q(attendees=employee),
            start_time__gte=today
        ).order_by('start_time')

        # Get upcoming tasks
        tasks = Task.objects.filter(
            assigned_to=employee,
            status__in=['pending', 'in_progress'],
            due_date__gte=today
        ).order_by('due_date')

        context.update({
            'meetings': meetings,
            'tasks': tasks,
            'today': today,
        })
        return context

    def get_events_data(self):
        """Helper method to get calendar events in the required format"""
        employee = self.request.user.employee
        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        except (TypeError, ValueError):
            # Default to current month if dates not provided
            today = timezone.now()
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=45)).replace(day=1)

        # Get meetings
        meetings = Meeting.objects.filter(
            Q(organizer=employee) | Q(attendees=employee),
            start_time__range=[start_date, end_date]
        )

        # Get tasks
        tasks = Task.objects.filter(
            assigned_to=employee,
            due_date__range=[start_date, end_date]
        )

        events = []

        # Add meetings to events
        for meeting in meetings:
            events.append({
                'id': f'meeting_{meeting.id}',
                'title': meeting.title,
                'start': meeting.start_time.isoformat(),
                'end': meeting.end_time.isoformat(),
                'url': meeting.get_absolute_url(),
                'type': 'meeting',
                'className': f'event-meeting event-{meeting.meeting_type}',
                'extendedProps': {
                    'description': meeting.description,
                    'meetingType': meeting.get_meeting_type_display(),
                    'organizer': meeting.organizer.user.get_full_name()
                }
            })

        # Add tasks to events
        for task in tasks:
            events.append({
                'id': f'task_{task.id}',
                'title': task.title,
                'start': task.due_date.isoformat(),
                'allDay': True,
                'url': task.get_absolute_url(),
                'type': 'task',
                'className': f'event-task event-priority-{task.priority}',
                'extendedProps': {
                    'description': task.description,
                    'priority': task.get_priority_display(),
                    'status': task.get_status_display()
                }
            })

        return events

def calendar_events(request):
    view = CalendarView()
    view.request = request
    events = view.get_events_data()
    return JsonResponse(events, safe=False)

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
    employee = request.user.employee
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
            if request.user.employee != task.assigned_to and request.user.employee != task.created_by:
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
    """Check if a time slot is available for a meeting"""
    start_time = request.GET.get('start_time')
    end_time = request.GET.get('end_time')
    meeting_id = request.GET.get('meeting_id')  # For excluding current meeting when updating

    try:
        start_time = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Check for conflicting meetings
    conflicts = Meeting.objects.filter(
        Q(organizer=request.user.employee) | Q(attendees=request.user.employee),
        Q(start_time__lt=end_time, end_time__gt=start_time)
    )

    if meeting_id:
        conflicts = conflicts.exclude(id=meeting_id)

    if conflicts.exists():
        return JsonResponse({
            'available': False,
            'conflicts': [{
                'title': m.title,
                'start': m.start_time.strftime('%Y-%m-%dT%H:%M'),
                'end': m.end_time.strftime('%Y-%m-%dT%H:%M')
            } for m in conflicts]
        })

    return JsonResponse({'available': True})

@login_required
def schedule_meeting(request):
    """Schedule a meeting via API endpoint"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data = json.loads(request.body)
    form = MeetingForm(data)

    if form.is_valid():
        meeting = form.save(commit=False)
        meeting.organizer = request.user.employee

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
        Q(assigned_to=request.user.employee) |
        Q(created_by=request.user.employee)
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
        Q(organizer=request.user.employee) |
        Q(attendees=request.user.employee)
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
            customer__assigned_to=self.request.user.employee
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

        # ✅ Check if payment record should be created
        if invoice.status in status_mapping and previous_status != invoice.status:
            existing_payment = Payment.objects.filter(invoice=invoice).exists()

            if not existing_payment:
                Payment.objects.create(
                    customer=invoice.customer,
                    invoice=invoice,
                    amount=invoice.total_amount,
                    status=status_mapping[invoice.status],  # ✅ Apply status mapping
                    transaction_date=timezone.now(),
                )
                messages.success(self.request, f'Invoice marked as {invoice.status}, payment recorded.')

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


class PaymentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'core/payment_form.html'
    success_url = reverse_lazy('payment-list')

    def test_func(self):
        """Only superusers can process payments"""
        return self.request.user.is_superuser

    def get_initial(self):
        """Pre-fill invoice if provided in URL"""
        initial = super().get_initial()
        invoice_id = self.request.GET.get('invoice')
        if invoice_id:
            try:
                invoice = Invoice.objects.get(pk=invoice_id)
                initial['invoice'] = invoice
                initial['customer'] = invoice.customer
                initial['amount'] = invoice.amount_due  # ✅ Correct field for remaining balance
            except Invoice.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        payment = form.save(commit=False)
        invoice = payment.invoice

        # ✅ Prevent overpayment
        balance_due = invoice.amount_due  # ✅ Use correct field
        if payment.amount > balance_due:
            messages.error(self.request, f"Payment exceeds the outstanding balance of ${balance_due:.2f}!")
            return self.form_invalid(form)

        # ✅ Assign a transaction ID
        payment.transaction_id = f"TXN-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        payment.status = 'completed' if payment.amount > 0 else 'pending'
        payment.save()

        # ✅ Update invoice balance and status
        invoice.update_balance()  # ✅ Correctly track payments

        # ✅ Log Transaction
        Transaction.objects.create(
            customer=invoice.customer,
            invoice=invoice,
            transaction_type='invoice_payment',
            amount=payment.amount,
            reference=payment.transaction_id
        )

        messages.success(self.request, f'Payment of ${payment.amount:.2f} applied to Invoice {invoice.invoice_number}.')
        return super().form_valid(form)




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
        return Subscription.objects.filter(customer__assigned_to=self.request.user.employee).order_by('-start_date')


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
        context.update({
            'invoices': Invoice.objects.exclude(status='paid').order_by('-created_at'),  # ✅ Show only unpaid invoices
            'payments': Payment.objects.all().order_by('-transaction_date'),
            'subscriptions': Subscription.objects.all().order_by('-start_date'),
            'transactions': Transaction.objects.all().order_by('-transaction_date'),
        })
        return context


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


class PaymentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'core/payment_form.html'
    success_url = reverse_lazy('payment-list')

    def test_func(self):
        """Only superusers can process payments"""
        return self.request.user.is_superuser

    def get_initial(self):
        """Pre-fill invoice if provided in URL"""
        initial = super().get_initial()
        invoice_id = self.request.GET.get('invoice')
        if invoice_id:
            try:
                invoice = Invoice.objects.get(pk=invoice_id)
                initial['invoice'] = invoice
                initial['customer'] = invoice.customer
                initial['amount'] = invoice.balance_due  # ✅ Correctly reference balance_due property
            except Invoice.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        payment = form.save(commit=False)
        invoice = payment.invoice

        # ✅ Prevent overpayment
        balance_due = invoice.balance_due  # Use the correct property
        if payment.amount > balance_due:
            messages.error(self.request, f"Payment exceeds the outstanding balance of ${balance_due:.2f}!")
            return self.form_invalid(form)

        # ✅ Assign a transaction ID
        payment.transaction_id = f"TXN-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        payment.status = 'completed' if payment.amount > 0 else 'pending'
        payment.save()

        # ✅ Update invoice status
        invoice.update_status()  # Correct method instead of `update_balance()`

        # ✅ Log Transaction
        Transaction.objects.create(
            customer=invoice.customer,
            invoice=invoice,
            transaction_type='invoice_payment',
            amount=payment.amount,
            reference=payment.transaction_id
        )

        messages.success(self.request, f'Payment of ${payment.amount:.2f} applied to Invoice {invoice.invoice_number}.')
        return super().form_valid(form)




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
        messages.success(self.request, 'Service subscription created successfully.')
        response = super().form_valid(form)
        self.object.generate_invoice()  # ✅ Generate invoice on subscription
        return response

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
