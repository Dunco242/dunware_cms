from django.urls import path
from . import views
from . import consumers
from .views import (
    # Authentication Views
    register, profile, change_password,

    # Employee Views
    EmployeeListView, EmployeeCreateView, EmployeeDetailView,
    EmployeeUpdateView, EmployeeDeleteView,

    # Customer Views
    CustomerListView, CustomerCreateView, CustomerDetailView,
    CustomerUpdateView, CustomerDeleteView,

    # Lead Views
    LeadListView, LeadCreateView, LeadDetailView,
    LeadUpdateView, LeadDeleteView, convert_lead_to_customer,

    # Event Views
    EventListView, EventCreateView, EventDetailView,
    EventUpdateView, EventDeleteView,
    CustomerEventListView, CustomerEventCreateView,

    # Service Views
    ServiceListView, ServiceCreateView, ServiceDetailView,
    ServiceUpdateView, ServiceDeleteView,

    # Note Views
    NoteListView, NoteCreateView, NoteDetailView,
    NoteUpdateView, NoteDeleteView,

    # Meeting Views
    MeetingListView, MeetingCreateView, MeetingDetailView,
    MeetingUpdateView, MeetingDeleteView,

    # Billing Views
    BillingDashboardView, PaidInvoicesListView,
    InvoiceListView, InvoiceCreateView, InvoiceDetailView,
    InvoiceUpdateView, InvoiceDeleteView, generate_invoice_pdf,
    PaymentListView, PaymentCreateView, PaymentDetailView,
    PaymentUpdateView, PaymentDeleteView,
    ServiceSubscriptionListView, ServiceSubscriptionCreateView,
    ServiceSubscriptionUpdateView, ServiceSubscriptionDeleteView,
    SubscriptionDetailView, SubscriptionUpdateView, SubscriptionCancelView,
    BillingSettingsView,

    # Schedule Views
    ScheduleRuleListView, ScheduleRuleCreateView,
    ScheduleRuleUpdateView, ScheduleRuleDeleteView,

    # Task Views
    TaskListView, TaskCreateView, TaskDetailView,
    TaskUpdateView, TaskDeleteView, task_status_update,

    #chat
    employee_list_api,
    # Other Views
    IPStatisticsView,

    # Email
    EmailInboxView, compose_email,
    view_email,
    reply_email,
    email_account_create,
    email_account_update,
    email_account_delete,
    email_account_list,
    activate_email_account,
    compose_email,
    SentMailView,
    DeletedMailView,
    EmailThreadView
)

urlpatterns = [
    # Authentication URLs
    path('register/', register, name='register'),
    path('profile/', profile, name='profile'),
    path('profile/change-password/', change_password, name='change-password'),

    # Employee URLs
    path('employees/', EmployeeListView.as_view(), name='employee-list'),
    path('employees/create/', EmployeeCreateView.as_view(), name='employee-create'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/update/', EmployeeUpdateView.as_view(), name='employee-update'),
    path('employees/<int:pk>/delete/', EmployeeDeleteView.as_view(), name='employee-delete'),

    # Customer URLs
    path('customers/', CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/update/', CustomerUpdateView.as_view(), name='customer-update'),
    path('customers/<int:pk>/delete/', CustomerDeleteView.as_view(), name='customer-delete'),

    # Lead URLs
    path('leads/', LeadListView.as_view(), name='lead-list'),
    path('leads/create/', LeadCreateView.as_view(), name='lead-create'),
    path('leads/<int:pk>/', LeadDetailView.as_view(), name='lead-detail'),
    path('leads/<int:pk>/update/', LeadUpdateView.as_view(), name='lead-update'),
    path('leads/<int:pk>/delete/', LeadDeleteView.as_view(), name='lead-delete'),
    path('leads/<int:pk>/convert/', convert_lead_to_customer, name='lead-convert'),

    # Note URLs
    path('notes/', NoteListView.as_view(), name='note-list'),
    path('notes/create/', NoteCreateView.as_view(), name='note-create'),
    path('notes/<int:pk>/', NoteDetailView.as_view(), name='note-detail'),
    path('notes/<int:pk>/update/', NoteUpdateView.as_view(), name='note-update'),
    path('notes/<int:pk>/delete/', NoteDeleteView.as_view(), name='note-delete'),

    # Meeting URLs
    path('meetings/', MeetingListView.as_view(), name='meeting-list'),
    path('meetings/create/', MeetingCreateView.as_view(), name='meeting-create'),
    path('meetings/<int:pk>/', MeetingDetailView.as_view(), name='meeting-detail'),
    path('meetings/<int:pk>/update/', MeetingUpdateView.as_view(), name='meeting-update'),
    path('meetings/<int:pk>/delete/', MeetingDeleteView.as_view(), name='meeting-delete'),

    # Event Management Routes - User
    path('events/', EventListView.as_view(), name='event-list'),
    path('events/create/', EventCreateView.as_view(), name='event-create'),
    path('events/<int:pk>/', EventDetailView.as_view(), name='event-detail'),
    path('events/<int:pk>/update/', EventUpdateView.as_view(), name='event-update'),
    path('events/<int:pk>/delete/', EventDeleteView.as_view(), name='event-delete'),
    path('event/<int:pk>/', views.event_detail, name='event-detail'),

    # Customer Event Management Routes
    path('customers/<int:customer_id>/events/', CustomerEventListView.as_view(), name='customer-event-list'),
    path('customers/<int:customer_id>/events/create/', CustomerEventCreateView.as_view(), name='customer-event-create'),
    path('customers/<int:customer_id>/calendar/', views.customer_calendar_view, name='customer-calendar'),
    path('api/customers/<int:customer_id>/calendar-events/', views.customer_calendar_events, name='customer-calendar-events'),
    path('customer/<int:customer_id>/upload-ics/', views.upload_ics, name='customer-upload-ics'),

    # Calendar System URLs
    path('calendar/', views.user_calendar_view, name='calendar'),
    path('api/user-calendar-events/', views.user_calendar_events, name='user-calendar-events'),
    path('calendar/upload-ics/', views.upload_ics, name='upload-ics'),

    # Service URLs
    path('services/', ServiceListView.as_view(), name='service-list'),
    path('services/create/', ServiceCreateView.as_view(), name='service-create'),
    path('services/<int:pk>/', ServiceDetailView.as_view(), name='service-detail'),
    path('services/<int:pk>/update/', ServiceUpdateView.as_view(), name='service-update'),
    path('services/<int:pk>/delete/', ServiceDeleteView.as_view(), name='service-delete'),

    # Scheduling System URLs
    path('scheduling/rules/', ScheduleRuleListView.as_view(), name='schedule-rule-list'),
    path('scheduling/rules/create/', ScheduleRuleCreateView.as_view(), name='schedule-rule-create'),
    path('scheduling/rules/<int:pk>/update/', ScheduleRuleUpdateView.as_view(), name='schedule-rule-update'),
    path('scheduling/rules/<int:pk>/delete/', ScheduleRuleDeleteView.as_view(), name='schedule-rule-delete'),

    # Billing URLs
    path('billing/', BillingDashboardView.as_view(), name='billing-dashboard'),
    path('billing/invoices/paid/', PaidInvoicesListView.as_view(), name='paid-invoices'),
    path('billing/settings/', BillingSettingsView.as_view(), name='billing-settings'),

    # Invoice URLs
    path('billing/invoices/', InvoiceListView.as_view(), name='invoice-list'),
    path('billing/invoices/create/', InvoiceCreateView.as_view(), name='invoice-create'),
    path('billing/invoices/<int:pk>/', InvoiceDetailView.as_view(), name='invoice-detail'),
    path('billing/invoices/<int:pk>/update/', InvoiceUpdateView.as_view(), name='invoice-update'),
    path('billing/invoices/<int:pk>/delete/', InvoiceDeleteView.as_view(), name='invoice-delete'),
    path("billing/invoice/<int:invoice_id>/pdf/", generate_invoice_pdf, name="invoice-pdf"),

    # Payment URLs
    path('billing/payments/', PaymentListView.as_view(), name='payment-list'),
    path('billing/payments/create/', PaymentCreateView.as_view(), name='payment-create'),
    path('billing/payments/<int:pk>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('billing/payments/<int:pk>/update/', PaymentUpdateView.as_view(), name='payment-update'),
    path('billing/payments/<int:pk>/delete/', PaymentDeleteView.as_view(), name='payment-delete'),

    # Subscription URLs
    path('subscriptions/', ServiceSubscriptionListView.as_view(), name='subscription-list'),
    path('subscriptions/create/', ServiceSubscriptionCreateView.as_view(), name='subscription-create'),
    path('customers/subscriptions/<int:pk>/edit/', ServiceSubscriptionUpdateView.as_view(), name='subscription-update'),
    path('customers/subscriptions/<int:pk>/delete/', ServiceSubscriptionDeleteView.as_view(), name='subscription-delete'),
    path('billing/subscriptions/<int:pk>/', SubscriptionDetailView.as_view(), name='subscription-detail'),
    path('billing/subscriptions/<int:pk>/update/', SubscriptionUpdateView.as_view(), name='subscription-update'),
    path('billing/subscriptions/<int:pk>/cancel/', SubscriptionCancelView.as_view(), name='subscription-cancel'),

    # Task URLs
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/create/', TaskCreateView.as_view(), name='task-create'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<int:pk>/update/', TaskUpdateView.as_view(), name='task-update'),
    path('tasks/<int:pk>/delete/', TaskDeleteView.as_view(), name='task-delete'),
    path('tasks/<int:pk>/status/', task_status_update, name='task-status-update'),

    # Export URLs
    path('export/customers/', views.export_customers, name='export-customers'),
    path('export/leads/', views.export_leads, name='export-leads'),
    path('export/tasks/', views.export_tasks, name='export-tasks'),
    path('export/meetings/', views.export_meetings, name='export-meetings'),

    # API Routes
    path('api/tasks/update-status/', views.update_task_status, name='api-update-task-status'),
    path('api/meetings/check-availability/', views.check_meeting_availability, name='api-check-meeting-availability'),
    path('api/meetings/schedule/', views.schedule_meeting, name='api-schedule-meeting'),

    # Privacy and Statistics URLs
    path('ip-statistics/', IPStatisticsView.as_view(), name='ip_statistics'),
    path('privacy-policy/', views.privacy_policy_view, name='privacy_policy'),
    path('accept-privacy-policy/', views.accept_privacy_policy, name='accept_privacy_policy'),

   # Chat UI Routes
    path('chat/', views.chat_inbox, name='chat_inbox'),
    path('chat/session/<int:session_id>/', views.chat_detail, name='chat_detail'),
    path('chat/start/<str:employee_id>/', views.start_chat, name='start_chat'),

    # Chat API Routes
    path('chat/send/', views.send_message, name='send_message'),
    path('chat/messages/<int:session_id>/', views.get_messages, name='get_messages'),
    path('chat/unread/', views.get_unread_count, name='get_unread_count'),
    path('chat/read/<int:session_id>/', views.mark_messages_read, name='mark_messages_read'),
    path('chat/employee-list/', views.employee_list_api, name='employee-list-api'),
    path('ws/notifications/<int:employee_id>/', views.notifications_ws, name='notifications-ws'),

    path('api/calendar/events/', views.user_calendar_events, name='user-calendar-events'),
    path('api/task/update/', views.update_task_status, name='api-update-task'),
    path('api/meeting/schedule/', views.schedule_meeting, name='api-schedule-meeting'),
    path('api/event/update/', views.update_event, name='api-update-event'),
    path('api/calendar/debug-items/', views.debug_calendar_items, name='debug-calendar-items'),

    # Email URLs
    path('inbox/', EmailInboxView.as_view(), name='email_inbox'),
    path('sent/', SentMailView.as_view(), name='email_sent'),
    path('deleted/', DeletedMailView.as_view(), name='email_deleted'),
    path('thread/<str:message_id>/', EmailThreadView.as_view(), name='email_thread'),

    path('compose/', compose_email, name='compose_email'),
    path('view/<str:message_id>/', view_email, name='view_email'),
    path('reply/<str:message_id>/', reply_email, name='reply_email'),

    path('email-accounts/', email_account_list, name='email_account_list'),
    path('email-accounts/create/', email_account_create, name='email_account_create'),
    path('email-accounts/<int:pk>/update/', email_account_update, name='email_account_update'),
    path('email-accounts/<int:pk>/delete/', email_account_delete, name='email_account_delete'),

    path('email/activate/', activate_email_account, name='activate_email_account'),
]



# Error Handlers
handler404 = 'core.views.custom_404'
handler500 = 'core.views.custom_500'
