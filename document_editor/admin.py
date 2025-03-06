# document_editor/admin.py
from django.contrib import admin
from .models import (
    Document, DocumentVersion, DocumentCollaborator, DocumentComment,
    DocumentTemplate, DocumentEditSession, DocumentApprovalWorkflow,
    DocumentApprovalStep, DocumentApprovalRequest, DocumentTemplateVariable
)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'document_type', 'status', 'author', 'customer', 'created_at', 'version')
    list_filter = ('document_type', 'status', 'is_template', 'is_public')
    search_fields = ('title', 'plain_text', 'tags')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ('document', 'version_number', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('document__title', 'comment')
    readonly_fields = ('created_at',)

@admin.register(DocumentCollaborator)
class DocumentCollaboratorAdmin(admin.ModelAdmin):
    list_display = ('document', 'employee', 'permission', 'added_by', 'added_at')
    list_filter = ('permission', 'added_at')
    search_fields = ('document__title', 'employee__user__username')
    readonly_fields = ('added_at',)

@admin.register(DocumentComment)
class DocumentCommentAdmin(admin.ModelAdmin):
    list_display = ('document', 'author', 'created_at', 'is_resolved')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('document__title', 'content', 'author__user__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_by', 'is_public', 'created_at')
    list_filter = ('category', 'is_public', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(DocumentEditSession)
class DocumentEditSessionAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'start_time', 'end_time', 'is_active')
    list_filter = ('is_active', 'start_time')
    search_fields = ('document__title', 'user__username')
    readonly_fields = ('start_time', 'last_activity')

@admin.register(DocumentApprovalWorkflow)
class DocumentApprovalWorkflowAdmin(admin.ModelAdmin):
    list_display = ('document', 'status', 'current_approver', 'started_at', 'completed_at')
    list_filter = ('status', 'started_at')
    search_fields = ('document__title',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(DocumentApprovalStep)
class DocumentApprovalStepAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'approver', 'order', 'department_required', 'position_required')
    list_filter = ('department_required', 'position_required')
    search_fields = ('workflow__document__title', 'approver__user__username')

@admin.register(DocumentApprovalRequest)
class DocumentApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'approver', 'status', 'request_date', 'response_date')
    list_filter = ('status', 'request_date')
    search_fields = ('workflow__document__title', 'approver__user__username', 'comments')
    readonly_fields = ('request_date',)

@admin.register(DocumentTemplateVariable)
class DocumentTemplateVariableAdmin(admin.ModelAdmin):
    list_display = ('template', 'name', 'display_name', 'variable_type', 'required')
    list_filter = ('variable_type', 'required')
    search_fields = ('template__name', 'name', 'display_name')
