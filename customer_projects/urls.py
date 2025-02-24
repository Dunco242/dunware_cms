from django.urls import path
from . import views
from .views import (
    RiskCreateView, TeamListView, RiskListView, DocumentFormView,
    PhaseListView, PhaseCreateView, PhaseUpdateView, PhaseDeleteView,
    ProjectTaskDetailView, ProjectTaskListView, TaskDetailView,
    TaskCreateView, TaskUpdateView, TaskDeleteView, TimeEntryCreateView,
    TimeEntryUpdateView
)

app_name = 'customer_projects'

urlpatterns = [
    # Dashboard & Analytics
    path('', views.ProjectDashboardView.as_view(), name='dashboard'),
    path('analytics/', views.ProjectAnalyticsView.as_view(), name='analytics'),

    # Project Management
    path('projects/', views.ProjectListView.as_view(), name='project-list'),
    path('projects/create/', views.ProjectCreateView.as_view(), name='project-create'),
    path('projects/<int:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),
    path('projects/<int:pk>/update/', views.ProjectUpdateView.as_view(), name='project-update'),
    path('projects/<int:pk>/delete/', views.ProjectDeleteView.as_view(), name='project-delete'),
    path('projects/<int:pk>/report/', views.ProjectReportView.as_view(), name='project-report'),
    path('projects/<int:project_id>/export/', views.export_project_data, name='project-export'),
    path('projects/<int:project_id>/progress/', views.project_progress_update, name='project-progress-update'),

    # Team Management
    path('projects/<int:project_id>/team/', TeamListView.as_view(), name='team-list'),
    path('projects/<int:project_id>/team/add/', views.TeamMemberCreateView.as_view(), name='team-member-add'),
    path('team/create/', views.TeamMemberCreateView.as_view(), name='team-member-create'),
    path('team/<int:pk>/update/', views.TeamMemberUpdateView.as_view(), name='team-member-update'),

    # Phase Management
    path('projects/<int:project_id>/phases/', PhaseListView.as_view(), name='phase-list'),
    path('projects/<int:project_id>/phases/create/', PhaseCreateView.as_view(), name='phase-create'),
    path('phases/<int:pk>/update/', PhaseUpdateView.as_view(), name='phase-update'),
    path('phases/<int:pk>/delete/', PhaseDeleteView.as_view(), name='phase-delete'),

    # Task Management - Consolidated and Reorganized
    # Project and Phase specific task routes
    path('projects/<int:project_id>/phases/<int:phase_id>/tasks/',
         ProjectTaskListView.as_view(),
         name='project-task-list'),
    path('projects/<int:project_id>/phases/<int:phase_id>/tasks/create/',
         TaskCreateView.as_view(),
         name='task-create'),
    path('projects/<int:project_id>/phases/<int:phase_id>/tasks/<int:pk>/',
         ProjectTaskDetailView.as_view(),
         name='project-task-detail'),

    # Task CRUD operations
    path('tasks/<int:pk>/update/', TaskUpdateView.as_view(), name='task-update'),
    path('tasks/<int:pk>/delete/', TaskDeleteView.as_view(), name='task-delete'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/update-status/', views.update_task_status, name='task-status-update'),

    # Time Tracking
    path('tasks/<int:task_id>/time-entry/create/',
         views.TimeEntryCreateView.as_view(),
         name='time-entry-create'),
    path('time-entries/<int:pk>/update/',
         views.TimeEntryUpdateView.as_view(),
         name='time-entry-update'),

    # Document Management
    path('projects/<int:project_id>/documents/', views.DocumentListView.as_view(), name='document-list'),
    path('projects/<int:project_id>/documents/upload/', views.DocumentUploadView.as_view(), name='document-upload'),
    path('projects/<int:project_id>/documents/bulk-upload/', views.bulk_document_upload, name='bulk-document-upload'),
    path('projects/<int:project_id>/documents/upload/', DocumentFormView.as_view(), name='document-form'),
    path('documents/<int:document_id>/download/', views.document_download, name='document-download'),

    # Risk Management
    path('projects/<int:project_id>/risks/', views.RiskListView.as_view(), name='risk-list'),
    path('projects/<int:project_id>/risks/create/', views.RiskCreateView.as_view(), name='risk-create'),
    path('risks/<int:pk>/update/', views.RiskUpdateView.as_view(), name='risk-update'),

    # Reports
    path('projects/<int:project_id>/reports/', views.ReportListView.as_view(), name='report-list'),
    path('projects/<int:project_id>/reports/create/', views.ReportCreateView.as_view(), name='report-create'),
    path('reports/<int:pk>/update/', views.ReportUpdateView.as_view(), name='report-update'),

    # Comments
    path('projects/<int:project_id>/comment/', views.add_comment, name='add-comment'),
    path('comments/create/', views.ProjectCommentCreateView.as_view(), name='comment-create'),

    # API Endpoints
    path('api/tasks/update-status/', views.update_task_status, name='api-task-status-update'),
    path('api/projects/progress/', views.project_progress_update, name='api-project-progress-update'),
    path('api/phases/<int:pk>/update-status/', views.update_phase_status, name='phase-status-update'),
]
