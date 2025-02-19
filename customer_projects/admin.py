from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from .models import (
    Project, ProjectTeamMember, ProjectPhase, ProjectTask,
    ProjectDocument, ProjectRisk, TimeEntry, ProjectComment,
    ProjectReport
)

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_code', 'name', 'customer', 'project_manager',
                   'status', 'priority', 'progress', 'start_date', 'target_end_date')
    list_filter = ('status', 'priority', 'customer', 'project_manager')
    search_fields = ('name', 'project_code', 'description',
                    'customer__company_name', 'project_manager__user__username')
    readonly_fields = ('project_code', 'created_at', 'updated_at')
    date_hierarchy = 'start_date'

    fieldsets = (
        ('Basic Information', {
            'fields': ('project_code', 'name', 'description', 'customer')
        }),
        ('Project Management', {
            'fields': ('project_manager', 'status', 'priority', 'progress')
        }),
        ('Dates', {
            'fields': ('start_date', 'target_end_date', 'actual_end_date')
        }),
        ('Financial Details', {
            'fields': ('budget', 'actual_cost', 'hourly_rate'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ProjectTeamMember)
class ProjectTeamMemberAdmin(admin.ModelAdmin):
    list_display = ('employee', 'project', 'role', 'allocation_percentage')
    list_filter = ('role', 'project')
    search_fields = ('employee__user__username', 'project__name')
    raw_id_fields = ('employee', 'project')

@admin.register(ProjectPhase)
class ProjectPhaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'status', 'start_date',
                   'end_date', 'progress', 'is_completed')
    list_filter = ('status', 'is_completed', 'project')
    search_fields = ('name', 'project__name', 'description')
    date_hierarchy = 'start_date'

@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'phase', 'status', 'priority',
                   'assigned_to', 'start_date', 'due_date')
    list_filter = ('status', 'priority', 'phase__project')
    search_fields = ('title', 'description', 'assigned_to__user__username')
    raw_id_fields = ('assigned_to', 'dependencies')
    date_hierarchy = 'start_date'

    def phase_project(self, obj):
        return obj.phase.project
    phase_project.short_description = 'Project'

@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'document_type', 'version',
                   'uploaded_by', 'upload_date')
    list_filter = ('document_type', 'upload_date', 'project')
    search_fields = ('title', 'description', 'project__name')
    date_hierarchy = 'upload_date'

@admin.register(ProjectRisk)
class ProjectRiskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'risk_level', 'status',
                   'probability', 'impact', 'risk_score')
    list_filter = ('risk_level', 'status', 'project')
    search_fields = ('title', 'description', 'project__name')
    readonly_fields = ('risk_score',)

    def risk_score(self, obj):
        return f"{obj.risk_score:.2f}"
    risk_score.short_description = 'Risk Score'

@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('task', 'employee', 'date', 'hours',
                   'is_billable', 'created_at')
    list_filter = ('is_billable', 'date', 'task__phase__project')
    search_fields = ('description', 'employee__user__username',
                    'task__title')
    date_hierarchy = 'date'

    def task_project(self, obj):
        return obj.task.phase.project
    task_project.short_description = 'Project'

@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ('get_content_object', 'author', 'text_preview', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('text', 'author__user__username')
    date_hierarchy = 'created_at'

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Comment'

    def get_content_object(self, obj):
        if obj.content_object:
            return str(obj.content_object)
        return 'N/A'
    get_content_object.short_description = 'Related To'

@admin.register(ProjectReport)
class ProjectReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'report_type', 'generated_by',
                   'created_at', 'has_attachment')
    list_filter = ('report_type', 'created_at', 'project')
    search_fields = ('title', 'content', 'project__name')
    date_hierarchy = 'created_at'

    def has_attachment(self, obj):
        return bool(obj.attachments)
    has_attachment.boolean = True
    has_attachment.short_description = 'Has Attachment'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'project', 'generated_by'
        )

# Optional: Register custom admin site
# class ProjectManagementAdminSite(admin.AdminSite):
#     site_header = 'Project Management Administration'
#     site_title = 'Project Management Admin'
#     index_title = 'Project Management'

# Uncomment these lines if you want to use a custom admin site
# project_admin = ProjectManagementAdminSite(name='project_admin')
# project_admin.register(Project, ProjectAdmin)
# project_admin.register(ProjectTeamMember, ProjectTeamMemberAdmin)
# project_admin.register(ProjectPhase, ProjectPhaseAdmin)
# project_admin.register(ProjectTask, ProjectTaskAdmin)
# project_admin.register(ProjectDocument, ProjectDocumentAdmin)
# project_admin.register(ProjectRisk, ProjectRiskAdmin)
# project_admin.register(TimeEntry, TimeEntryAdmin)
# project_admin.register(ProjectComment, ProjectCommentAdmin)
# project_admin.register(ProjectReport, ProjectReportAdmin)
