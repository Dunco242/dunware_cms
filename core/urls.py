# core/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
   # path('', views.DashboardView.as_view(), name='dashboard'),

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

    # Calendar URLs
    path('calendar/', views.CalendarView.as_view(), name='calendar'),
    path('calendar/events/', views.calendar_events, name='calendar-events'),
    path('calendar/available-slots/', views.available_slots, name='calendar-available-slots'),

    # API URLs
    path('api/tasks/update-status/', views.update_task_status, name='api-update-task-status'),
    path('api/meetings/check-availability/', views.check_meeting_availability, name='api-check-meeting-availability'),
    path('api/meetings/schedule/', views.schedule_meeting, name='api-schedule-meeting'),

    # Export URLs
    path('export/customers/', views.export_customers, name='export-customers'),
    path('export/leads/', views.export_leads, name='export-leads'),
    path('export/tasks/', views.export_tasks, name='export-tasks'),
    path('export/meetings/', views.export_meetings, name='export-meetings'),
]

handler404 = 'core.views.custom_404'
handler500 = 'core.views.custom_500'

# Add these view functions to core/views.py
def custom_404(request, exception):
    return render(request, 'core/errors/404.html', status=404)

def custom_500(request):
    return render(request, 'core/errors/500.html', status=500)
