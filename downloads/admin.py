from django.contrib import admin
from .models import VerificationCode


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'is_used',
        'used_at',
        'download_ip',
        'short_user_agent',
    )
    list_filter = ('is_used', 'used_at')
    search_fields = ('code', 'download_ip', 'download_user_agent')

    readonly_fields = (
        'code',
        'is_used',
        'used_at',
        'download_ip',
        'download_user_agent',
    )

    def short_user_agent(self, obj):
        if obj.download_user_agent:
            return obj.download_user_agent[:60] + '...' if len(obj.download_user_agent) > 60 else obj.download_user_agent
        return "-"
    short_user_agent.short_description = 'User Agent'

    fieldsets = (
        (None, {
            'fields': ('code', 'is_used', 'used_at')
        }),
        ('Audit Trail', {
            'classes': ('collapse',),
            'fields': ('download_ip', 'download_user_agent'),
        }),
    )
