# core/urls.py

from django.urls import path
from . import views
from .views import ServiceSubscriptionListView, ServiceSubscriptionCreateView, PaidInvoicesListView, generate_invoice_pdf

urlpatterns = [
    # Authentication URLs
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('profile/change-password/', views.change_password, name='change-password'),

    # Employee URLs
    path('employees/', views.EmployeeListView.as_view(), name='employee-list'),
    path('employees/create/', views.EmployeeCreateView.as_view(), name='employee-create'),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/update/', views.EmployeeUpdateView.as_view(), name='employee-update'),
    path('employees/<int:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee-delete'),

    # Customer URLs
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/update/', views.CustomerUpdateView.as_view(), name='customer-update'),
    path('customers/<int:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer-delete'),

    # Lead URLs
    path('leads/', views.LeadListView.as_view(), name='lead-list'),
    path('leads/create/', views.LeadCreateView.as_view(), name='lead-create'),
    path('leads/<int:pk>/', views.LeadDetailView.as_view(), name='lead-detail'),
    path('leads/<int:pk>/update/', views.LeadUpdateView.as_view(), name='lead-update'),
    path('leads/<int:pk>/delete/', views.LeadDeleteView.as_view(), name='lead-delete'),
    path('leads/<int:pk>/convert/', views.convert_lead_to_customer, name='lead-convert'),

    # Service URLs
    path('services/', views.ServiceListView.as_view(), name='service-list'),
    path('services/create/', views.ServiceCreateView.as_view(), name='service-create'),
    path('services/<int:pk>/', views.ServiceDetailView.as_view(), name='service-detail'),
    path('services/<int:pk>/update/', views.ServiceUpdateView.as_view(), name='service-update'),
    path('services/<int:pk>/delete/', views.ServiceDeleteView.as_view(), name='service-delete'),

    # Note URLs
    path('notes/', views.NoteListView.as_view(), name='note-list'),
    path('notes/create/', views.NoteCreateView.as_view(), name='note-create'),
    path('notes/<int:pk>/', views.NoteDetailView.as_view(), name='note-detail'),
    path('notes/<int:pk>/update/', views.NoteUpdateView.as_view(), name='note-update'),
    path('notes/<int:pk>/delete/', views.NoteDeleteView.as_view(), name='note-delete'),

    # Task URLs
    path('tasks/', views.TaskListView.as_view(), name='task-list'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task-create'),
    path('tasks/<int:pk>/', views.TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<int:pk>/update/', views.TaskUpdateView.as_view(), name='task-update'),
    path('tasks/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task-delete'),
    path('tasks/<int:pk>/status/', views.task_status_update, name='task-status-update'),

    # Meeting URLs
    path('meetings/', views.MeetingListView.as_view(), name='meeting-list'),
    path('meetings/create/', views.MeetingCreateView.as_view(), name='meeting-create'),
    path('meetings/<int:pk>/', views.MeetingDetailView.as_view(), name='meeting-detail'),
    path('meetings/<int:pk>/update/', views.MeetingUpdateView.as_view(), name='meeting-update'),
    path('meetings/<int:pk>/delete/', views.MeetingDeleteView.as_view(), name='meeting-delete'),

    # Calendar System URLs
    # Personal Calendar Routes
    path('calendar/', views.user_calendar_view, name='calendar'),
    path('api/user-calendar-events/', views.user_calendar_events, name='user-calendar-events'),
    path('calendar/upload-ics/', views.upload_ics, name='upload-ics'),
    path('event/create/', views.create_event, name='create-event-user'),

    # Customer Calendar Routes
    path('customer/<int:customer_id>/calendar/', views.CalendarView.as_view(), name='customer-calendar'),
    path('api/customer/<int:customer_id>/events/', views.customer_calendar_events, name='customer-events'),
    path('customer/<int:customer_id>/upload-ics/', views.upload_ics, name='customer-upload-ics'),
    path('customer/<int:customer_id>/event/create/', views.create_event, name='create-event'),

    # Event Management Routes
    path('event/<int:event_id>/edit/', views.edit_event, name='edit-event'),
    path('event/<int:event_id>/delete/', views.delete_event, name='delete-event'),
    path('event/update/', views.update_event, name='update-event'),

    # Calendar API Routes
    path('api/tasks/update-status/', views.update_task_status, name='api-update-task-status'),
    path('api/meetings/check-availability/', views.check_meeting_availability, name='api-check-meeting-availability'),
    path('api/meetings/schedule/', views.schedule_meeting, name='api-schedule-meeting'),

    # Billing URLs
    path('billing/', views.BillingDashboardView.as_view(), name='billing-dashboard'),
    path('billing/invoices/paid/', PaidInvoicesListView.as_view(), name='paid-invoices'),

    # Invoices
    path('billing/invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path('billing/invoices/create/', views.InvoiceCreateView.as_view(), name='invoice-create'),
    path('billing/invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('billing/invoices/<int:pk>/update/', views.InvoiceUpdateView.as_view(), name='invoice-update'),
    path('billing/invoices/<int:pk>/delete/', views.InvoiceDeleteView.as_view(), name='invoice-delete'),
    path("billing/invoice/<int:invoice_id>/pdf/", generate_invoice_pdf, name="invoice-pdf"),

    # Payments
    path('billing/payments/', views.PaymentListView.as_view(), name='payment-list'),
    path('billing/payments/create/', views.PaymentCreateView.as_view(), name='payment-create'),
    path('billing/payments/<int:pk>/', views.PaymentDetailView.as_view(), name='payment-detail'),
    path('billing/payments/<int:pk>/update/', views.PaymentUpdateView.as_view(), name='payment-update'),
    path('billing/payments/<int:pk>/delete/', views.PaymentDeleteView.as_view(), name='payment-delete'),

    # Subscriptions
    path('billing/subscriptions/', views.SubscriptionListView.as_view(), name='service-subscription-list'),
    path('billing/subscriptions/create/', views.SubscriptionCreateView.as_view(), name='subscription-create'),
    path('billing/subscriptions/<int:pk>/', views.SubscriptionDetailView.as_view(), name='subscription-detail'),
    path('billing/subscriptions/<int:pk>/update/', views.SubscriptionUpdateView.as_view(), name='subscription-update'),
    path('billing/subscriptions/<int:pk>/cancel/', views.SubscriptionCancelView.as_view(), name='subscription-cancel'),

    # Service Subscription URLs
    path('subscriptions/', ServiceSubscriptionListView.as_view(), name='subscription-list'),
    path('subscriptions/create/', ServiceSubscriptionCreateView.as_view(), name='subscription-create'),
    path('customers/subscriptions/<int:pk>/edit/', views.ServiceSubscriptionUpdateView.as_view(), name='subscription-update'),
    path('customers/subscriptions/<int:pk>/delete/', views.ServiceSubscriptionDeleteView.as_view(), name='subscription-delete'),

    # Billing Settings
    path('billing/settings/', views.BillingSettingsView.as_view(), name='billing-settings'),

    # Export URLs
    path('export/customers/', views.export_customers, name='export-customers'),
    path('export/leads/', views.export_leads, name='export-leads'),
    path('export/tasks/', views.export_tasks, name='export-tasks'),
    path('export/meetings/', views.export_meetings, name='export-meetings'),
]

handler404 = 'core.views.custom_404'
handler500 = 'core.views.custom_500'
