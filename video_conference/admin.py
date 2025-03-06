from django.contrib import admin
from .models import VideoConference

@admin.register(VideoConference)
class VideoConferenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'channel_name', 'host_user', 'created_at', 'scheduled_for', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('channel_name', 'host_user__username')
    readonly_fields = ('id', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        (None, {
            'fields': ('id', 'channel_name', 'host_user')
        }),
        ('Schedule Information', {
            'fields': ('scheduled_for', 'is_active')
        }),
        ('Security', {
            'fields': ('passcode',)
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
