from django.contrib import admin
from .models import (
    OnboardingPlan, OnboardingStep, CustomerOnboarding,
    OnboardingStepCompletion, DataImportJob, OnboardingFeedback,
    OnboardingChecklistItem, ChecklistItemCompletion,
    OnboardingNotification
)

class OnboardingStepInline(admin.TabularInline):
    model = OnboardingStep
    extra = 1
    fields = ('name', 'step_type', 'order', 'is_required', 'estimated_minutes')


class OnboardingChecklistItemInline(admin.TabularInline):
    model = OnboardingChecklistItem
    extra = 1
    fields = ('text', 'order', 'is_required')


class ChecklistItemCompletionInline(admin.TabularInline):
    model = ChecklistItemCompletion
    extra = 0
    readonly_fields = ('completed_date', 'completed_by')
    fields = ('checklist_item', 'is_completed', 'completed_date', 'completed_by', 'notes')
    can_delete = False


class OnboardingStepCompletionInline(admin.TabularInline):
    model = OnboardingStepCompletion
    extra = 0
    readonly_fields = ('step', 'completed_date', 'completed_by')
    fields = ('step', 'is_completed', 'completed_date', 'completed_by', 'notes', 'satisfaction_rating')
    can_delete = False


@admin.register(OnboardingPlan)
class OnboardingPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'tier', 'is_active', 'estimated_days', 'created_at')
    list_filter = ('tier', 'is_active')
    search_fields = ('name', 'description')
    inlines = [OnboardingStepInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'tier', 'description', 'is_active')
        }),
        ('Timing', {
            'fields': ('estimated_days',)
        }),
    )


@admin.register(OnboardingStep)
class OnboardingStepAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan', 'step_type', 'order', 'is_required', 'estimated_minutes')
    list_filter = ('plan', 'step_type', 'is_required')
    search_fields = ('name', 'description')
    inlines = [OnboardingChecklistItemInline]
    fieldsets = (
        (None, {
            'fields': ('plan', 'name', 'step_type', 'description', 'order', 'is_required')
        }),
        ('Timing', {
            'fields': ('estimated_minutes',)
        }),
        ('Navigation', {
            'fields': ('url_name',)
        }),
        ('Resources', {
            'fields': ('video_url', 'documentation_url')
        }),
    )


@admin.register(CustomerOnboarding)
class CustomerOnboardingAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'status', 'progress_percentage', 'assigned_to', 'start_date')
    list_filter = ('status', 'plan', 'assigned_to')
    search_fields = ('customer__company_name', 'customer__first_name', 'customer__last_name')
    inlines = [OnboardingStepCompletionInline]
    readonly_fields = ('created_at', 'updated_at', 'progress_percentage')
    fieldsets = (
        (None, {
            'fields': ('customer', 'plan', 'status', 'progress_percentage')
        }),
        ('Assignment', {
            'fields': ('assigned_to',)
        }),
        ('Dates', {
            'fields': ('start_date', 'completed_date', 'last_activity_date')
        }),
        ('Current Progress', {
            'fields': ('current_step',)
        }),
        ('Reminders', {
            'fields': ('next_reminder_date', 'send_reminders')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        # Include related objects for better performance
        return super().get_queryset(request).select_related(
            'customer', 'plan', 'assigned_to', 'current_step'
        )


@admin.register(OnboardingStepCompletion)
class OnboardingStepCompletionAdmin(admin.ModelAdmin):
    list_display = ('step', 'customer_onboarding', 'is_completed', 'completed_date', 'completed_by')
    list_filter = ('is_completed', 'step__step_type')
    search_fields = ('customer_onboarding__customer__company_name', 'step__name')
    inlines = [ChecklistItemCompletionInline]
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('customer_onboarding', 'step', 'is_completed')
        }),
        ('Completion Details', {
            'fields': ('completed_date', 'completed_by', 'notes', 'satisfaction_rating')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DataImportJob)
class DataImportJobAdmin(admin.ModelAdmin):
    list_display = ('source_name', 'import_type', 'customer_onboarding', 'status', 'records_total', 'created_at')
    list_filter = ('status', 'import_type')
    search_fields = ('source_name', 'customer_onboarding__customer__company_name')
    readonly_fields = ('created_at', 'updated_at', 'progress_percentage')
    fieldsets = (
        (None, {
            'fields': ('customer_onboarding', 'import_type', 'source_name', 'source_file', 'status')
        }),
        ('Processing Details', {
            'fields': ('records_total', 'records_processed', 'records_succeeded', 'records_failed')
        }),
        ('Related Items', {
            'fields': ('related_step',)
        }),
        ('Notes and Errors', {
            'fields': ('notes', 'error_details')
        }),
        ('Processing Dates', {
            'fields': ('started_at', 'completed_at', 'created_at', 'updated_at')
        }),
    )

    def progress_percentage(self, obj):
        return f"{obj.progress_percentage}%"
    progress_percentage.short_description = "Progress"


@admin.register(OnboardingFeedback)
class OnboardingFeedbackAdmin(admin.ModelAdmin):
    list_display = ('customer_onboarding', 'feedback_type', 'overall_rating', 'step', 'submitted_at')
    list_filter = ('feedback_type', 'overall_rating')
    search_fields = ('customer_onboarding__customer__company_name', 'what_worked_well', 'what_could_improve')
    readonly_fields = ('submitted_at',)
    fieldsets = (
        (None, {
            'fields': ('customer_onboarding', 'feedback_type', 'step')
        }),
        ('Ratings', {
            'fields': ('overall_rating', 'ease_of_use_rating', 'support_rating')
        }),
        ('Feedback Text', {
            'fields': ('what_worked_well', 'what_could_improve', 'additional_comments')
        }),
        ('Submission Details', {
            'fields': ('submitted_by', 'submitted_at')
        }),
    )


@admin.register(OnboardingChecklistItem)
class OnboardingChecklistItemAdmin(admin.ModelAdmin):
    list_display = ('text', 'step', 'order', 'is_required')
    list_filter = ('is_required', 'step__step_type')
    search_fields = ('text', 'description', 'step__name')
    fieldsets = (
        (None, {
            'fields': ('step', 'text', 'description', 'order', 'is_required')
        }),
    )


@admin.register(ChecklistItemCompletion)
class ChecklistItemCompletionAdmin(admin.ModelAdmin):
    list_display = ('checklist_item', 'onboarding_step_completion', 'is_completed', 'completed_date')
    list_filter = ('is_completed',)
    search_fields = ('checklist_item__text', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('onboarding_step_completion', 'checklist_item', 'is_completed')
        }),
        ('Completion Details', {
            'fields': ('completed_date', 'completed_by', 'notes')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(OnboardingNotification)
class OnboardingNotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'title', 'recipient', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'email_sent')
    search_fields = ('title', 'message', 'recipient__username')
    readonly_fields = ('created_at', 'read_at', 'email_sent_at')
    fieldsets = (
        (None, {
            'fields': ('customer_onboarding', 'notification_type', 'title', 'message')
        }),
        ('Related Items', {
            'fields': ('related_step',)
        }),
        ('Recipient Details', {
            'fields': ('recipient', 'is_read', 'read_at')
        }),
        ('Email Status', {
            'fields': ('email_sent', 'email_sent_at')
        }),
        ('System Fields', {
            'fields': ('created_at',)
        }),
    )
