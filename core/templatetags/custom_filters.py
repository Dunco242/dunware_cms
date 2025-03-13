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
