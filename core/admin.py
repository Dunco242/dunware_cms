# core/admin.py

from django.contrib import admin
from .models import (
    Employee, Customer, Lead, Service,
    Note, Task, Meeting
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
