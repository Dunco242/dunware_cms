from django.contrib import admin
from django.utils.html import format_html
from .models import *

class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'department', 'position', 'is_active')
    list_filter = ('department', 'position', 'is_active')
    search_fields = ('employee_id', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'employee_id', 'profile_picture')
        }),
        ('Employment Details', {
            'fields': ('department', 'position', 'hire_date', 'termination_date')
        }),
        ('Contact Information', {
            'fields': ('phone', 'carrier')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'email', 'phone', 'status', 'assigned_to')
    list_filter = ('status', 'assigned_to')
    search_fields = ('company_name', 'contact_person', 'email')
    readonly_fields = ('created_at', 'updated_at', 'last_contact_date')

class LeadAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'email', 'status', 'source', 'assigned_to')
    list_filter = ('status', 'source', 'priority', 'assigned_to')
    search_fields = ('company_name', 'contact_person', 'email')
    readonly_fields = ('created_at', 'updated_at', 'last_contacted', 'conversion_date')

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')

class NoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'note_type', 'created_by', 'customer', 'lead', 'created_at')
    list_filter = ('note_type', 'created_by')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')

class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'due_date', 'status', 'priority', 'assigned_to', 'created_by')
    list_filter = ('status', 'priority', 'assigned_to', 'created_by')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at')

class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time', 'meeting_type', 'status', 'organizer')
    list_filter = ('meeting_type', 'status', 'organizer')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('attendees', 'customers', 'leads')

class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'issue_date', 'due_date', 'total', 'status')
    list_filter = ('status', 'customer')
    search_fields = ('invoice_number', 'customer__company_name')
    readonly_fields = ('created_at',)

    fieldsets = [
        (None, {
            'fields': ['customer', 'invoice_number', 'project', 'status']
        }),
        ('Dates', {
            'fields': ['issue_date', 'due_date', 'created_at']
        }),
        ('Financial Details', {
            'fields': ['subtotal', 'tax_amount', 'amount_paid', 'total', 'notes']
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        """Make invoice_number readonly only if this is an existing invoice"""
        if obj:  # editing an existing object
            return self.readonly_fields + ('invoice_number',)
        return self.readonly_fields


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'invoice', 'amount', 'status', 'payment_method', 'transaction_date')
    list_filter = ('status', 'payment_method', 'transaction_date')
    search_fields = ('reference', 'customer__company_name', 'invoice__invoice_number')
    readonly_fields = ('transaction_date',)

class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'start_date')
    search_fields = ('customer__company_name', 'plan')

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'transaction_type', 'amount', 'status', 'transaction_date')
    list_filter = ('transaction_type', 'status', 'transaction_date')
    search_fields = ('reference', 'customer__company_name')
    readonly_fields = ('transaction_date', 'created_by')

class ServiceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'service', 'status', 'billing_cycle', 'start_date', 'end_date', 'is_active')
    list_filter = ('status', 'billing_cycle', 'is_active')
    search_fields = ('customer__company_name', 'service__name')
    readonly_fields = ('invoice_generated',)

class UploadedICSFileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'uploaded_by', 'uploaded_at')
    list_filter = ('customer', 'uploaded_by')
    readonly_fields = ('uploaded_at',)

class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_type', 'start_time', 'end_time', 'status', 'created_by')
    list_filter = ('event_type', 'status', 'is_recurring', 'created_by')
    search_fields = ('title', 'description', 'location')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('attendees',)

class IPAccessAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'user', 'path', 'access_time', 'method')
    list_filter = ('user', 'method', 'is_secure')
    search_fields = ('ip_address', 'path', 'user_agent')
    readonly_fields = ('access_time',)

class ScheduleRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'recurrence_type', 'start_time', 'end_time', 'is_active')
    list_filter = ('user', 'recurrence_type', 'is_active')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')

class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'is_available', 'reason')
    list_filter = ('user', 'date', 'is_available')
    search_fields = ('user__username', 'reason')

class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_group_chat', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_group_chat', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('participants',)

class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'sender', 'receiver', 'message_type', 'timestamp', 'is_read')
    list_filter = ('message_type', 'is_read', 'session')
    search_fields = ('content',)
    readonly_fields = ('timestamp', 'read_at')

class ChatNotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'is_seen', 'created_at')
    list_filter = ('is_seen', 'recipient')
    readonly_fields = ('created_at', 'seen_at')

class EmailProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain', 'smtp_server', 'smtp_port', 'imap_server', 'imap_port')
    search_fields = ('name', 'domain')

class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ('employee', 'email_address', 'provider', 'is_active', 'last_sync')
    list_filter = ('provider', 'is_active')
    search_fields = ('email_address', 'employee__user__username')
    readonly_fields = ('last_sync',)

class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'created_by', 'is_shared', 'created_at')
    list_filter = ('is_shared', 'created_by')
    search_fields = ('name', 'subject', 'body')
    readonly_fields = ('created_at', 'updated_at')

class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'from_email', 'message_type', 'status', 'created_at')
    list_filter = ('message_type', 'status', 'is_read', 'is_starred', 'is_spam', 'is_archived')
    search_fields = ('subject', 'body_text', 'from_email')
    readonly_fields = ('created_at', 'updated_at', 'sent_at', 'read_at')

class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'email', 'content_type', 'size', 'created_at')
    list_filter = ('content_type',)
    search_fields = ('filename',)
    readonly_fields = ('created_at',)

class EmailFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'is_system', 'system_type', 'parent')
    list_filter = ('is_system', 'system_type', 'account')
    search_fields = ('name',)

class EmailFolderMessageAdmin(admin.ModelAdmin):
    list_display = ('folder', 'message', 'added_at')
    list_filter = ('folder',)
    readonly_fields = ('added_at',)

class EmailTrackerAdmin(admin.ModelAdmin):
    list_display = ('email', 'recipient_email', 'opened_count', 'opened_at', 'created_at')
    list_filter = ('opened_count',)
    search_fields = ('recipient_email',)
    readonly_fields = ('tracker_id', 'created_at', 'updated_at', 'opened_at')

class GeneralNotifierAdmin(admin.ModelAdmin):
    list_display = ('title', 'notification_type', 'priority', 'user', 'is_read', 'is_dismissed', 'event_datetime')
    list_filter = ('notification_type', 'priority', 'is_read', 'is_dismissed')
    search_fields = ('title', 'message', 'user__username')
    readonly_fields = ('created_at', 'read_at')

# Register all models
admin.site.register(Employee, EmployeeAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Lead, LeadAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(Note, NoteAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(Meeting, MeetingAdmin)
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(ServiceSubscription, ServiceSubscriptionAdmin)
admin.site.register(UploadedICSFile, UploadedICSFileAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(IPAccess, IPAccessAdmin)
admin.site.register(ScheduleRule, ScheduleRuleAdmin)
admin.site.register(ScheduleException, ScheduleExceptionAdmin)
admin.site.register(ChatSession, ChatSessionAdmin)
admin.site.register(ChatMessage, ChatMessageAdmin)
admin.site.register(ChatNotification, ChatNotificationAdmin)
admin.site.register(EmailProvider, EmailProviderAdmin)
admin.site.register(EmailAccount, EmailAccountAdmin)
admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(EmailMessage, EmailMessageAdmin)
admin.site.register(EmailAttachment, EmailAttachmentAdmin)
admin.site.register(EmailFolder, EmailFolderAdmin)
admin.site.register(EmailFolderMessage, EmailFolderMessageAdmin)
admin.site.register(EmailTracker, EmailTrackerAdmin)
admin.site.register(GeneralNotifier, GeneralNotifierAdmin)
