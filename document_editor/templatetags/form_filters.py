from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(value, arg):
    """
    Adds a CSS class to a form field

    Usage in template: {{ form.field|add_class:"some-class" }}
    """
    css_classes = value.field.widget.attrs.get('class', '')
    # If the class already exists, append the new class
    if css_classes:
        css_classes = f"{css_classes} {arg}"
    else:
        css_classes = arg
    return value.as_widget(attrs={'class': css_classes})
