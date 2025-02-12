from django.contrib import admin
from .models import (
    Employee, Customer, Lead, Service,
    Note, Task, Meeting, Invoice, Payment,
    Subscription, Transaction, ServiceSubscription, IPAccess, PrivacyPolicyAcceptance, LegalDocument, ScheduleRule, ScheduleException
)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'department', 'position', 'is_active')
    search_fields = ('employee_id', 'user__username', 'user__email')
    list_filter = ('department', 'is_active', 'hire_date')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'email', 'status', 'assigned_to')
    search_fields = ('company_name', 'contact_person', 'email')
    list_filter = ('status', 'city', 'state')

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'email', 'status', 'source', 'assigned_to')
    search_fields = ('company_name', 'contact_person', 'email')
    list_filter = ('status', 'source')

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'note_type', 'created_by', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('note_type', 'created_at')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'priority', 'status', 'due_date', 'assigned_to')
    search_fields = ('title', 'description')
    list_filter = ('priority', 'status', 'due_date')

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting_type', 'start_time', 'end_time', 'organizer')
    search_fields = ('title', 'description')
    list_filter = ('meeting_type', 'start_time')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'issue_date', 'due_date', 'total_amount', 'status')
    search_fields = ('invoice_number', 'customer__company_name')
    list_filter = ('status', 'issue_date', 'due_date')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'invoice', 'amount', 'status', 'transaction_date')
    search_fields = ('customer__company_name', 'invoice__invoice_number')
    list_filter = ('status', 'transaction_date')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'start_date', 'end_date', 'status')
    search_fields = ('customer__company_name', 'plan')
    list_filter = ('status', 'start_date', 'end_date')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'transaction_type', 'amount', 'transaction_date', 'reference')
    search_fields = ('customer__company_name', 'reference')
    list_filter = ('transaction_type', 'transaction_date')

@admin.register(ServiceSubscription)
class ServiceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'service', 'billing_cycle', 'price', 'status')
    search_fields = ('customer__company_name', 'service__name')
    list_filter = ('status', 'billing_cycle')


@admin.register(IPAccess)
class IPAccessAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'user', 'path', 'access_time', 'method']
    list_filter = ['access_time', 'method', 'is_secure']
    search_fields = ['ip_address', 'user__username', 'path']
    date_hierarchy = 'access_time'
    readonly_fields = ['access_time']

    def has_add_permission(self, request):
        return False  # Prevent manual creation

@admin.register(PrivacyPolicyAcceptance)
class PrivacyPolicyAcceptanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'policy_version', 'accepted_at', 'ip_address']
    list_filter = ['policy_version', 'accepted_at']
    search_fields = ['user__username', 'user__email', 'ip_address']
    readonly_fields = ['accepted_at', 'ip_address', 'user_agent']
    date_hierarchy = 'accepted_at'

    def has_add_permission(self, request):
        return False  # Prevent manual creation

    def has_change_permission(self, request, obj=None):
        return False  # Make it read-only


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('type', 'version', 'created_at', 'is_current')
    list_filter = ('type', 'is_current')

    def save_model(self, request, obj, form, change):
        # Automatically set is_current when creating a new version
        if not change:
            obj.is_current = True
        super().save_model(request, obj, form, change)


@admin.register(ScheduleRule)
class ScheduleRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'recurrence_type', 'start_time', 'end_time', 'is_active')
    list_filter = ('user', 'recurrence_type', 'is_active')

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'is_available', 'reason')
    list_filter = ('user', 'date', 'is_available')
