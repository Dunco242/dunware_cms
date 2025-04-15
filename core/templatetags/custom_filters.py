from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(value, arg):
    css_classes = value.field.widget.attrs.get('class', '')
    if css_classes:
        css_classes = f"{css_classes} {arg}"
    else:
        css_classes = arg
    return value.as_widget(attrs={'class': css_classes})


@register.filter
def split(value, arg):
    """
    Split the value by the argument and return a list.
    Example: {{ value|split:"," }}
    """
    return value.split(arg)

@register.filter(name='replace')
def replace(value, arg):
    """Replaces occurrences of arg in value with the empty string."""
    if not isinstance(value, str):
        value = str(value)  # Convert to string if it's not already
    if not isinstance(arg, str):
        arg = str(arg)
    return value.replace(arg, "")

@register.filter(name='replace_spaces')
def replace_spaces(value):
    if not isinstance(value, str):
        value = str(value)
    return value.replace("_", " ")
