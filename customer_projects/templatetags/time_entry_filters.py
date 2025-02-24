from django import template
from django.db.models import Sum
from decimal import Decimal

register = template.Library()

# Register each filter with an explicit name
@register.filter(name='time_sum_hours')
def sum_hours(time_entries):
    """Calculate total hours from time entries"""
    if not time_entries:
        return Decimal('0.0')
    total = time_entries.aggregate(total=Sum('hours'))['total']
    return total if total is not None else Decimal('0.0')

@register.filter(name='time_billable_hours')
def billable_hours(time_entries):
    """Calculate billable hours from time entries"""
    if not time_entries:
        return Decimal('0.0')
    total = time_entries.filter(is_billable=True).aggregate(total=Sum('hours'))['total']
    return total if total is not None else Decimal('0.0')

@register.filter(name='time_non_billable_hours')
def non_billable_hours(time_entries):
    """Calculate non-billable hours from time entries"""
    if not time_entries:
        return Decimal('0.0')
    total = time_entries.filter(is_billable=False).aggregate(total=Sum('hours'))['total']
    return total if total is not None else Decimal('0.0')

@register.filter(name='time_progress_percentage')
def progress_percentage(current, total):
    """Calculate progress percentage"""
    if not total or not current:
        return 0
    return (float(current) / float(total)) * 100

@register.filter(name='time_multiply')
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter(name='time_divide')
def divide(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0
