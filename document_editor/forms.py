from django import forms
from .models import Document, DocumentTemplate, DocumentCollaborator, DocumentComment
from core.models import Employee, Customer


class DocumentForm(forms.ModelForm):
    """Form for creating and editing documents"""

    class Meta:
        model = Document
        fields = [
            'title', 'document_type', 'status',
            'customer', 'tags', 'is_template', 'is_public'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-control select2'}),
            'tags': forms.TextInput(attrs={'class': 'form-control'}),
            'is_template': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make some fields optional
        self.fields['customer'].required = False
        self.fields['tags'].required = False

        # Add field help text
        self.fields['tags'].help_text = "Enter comma-separated tags"
        self.fields['is_template'].help_text = "Make this document available as a template"
        self.fields['is_public'].help_text = "Allow others to see this document"

        # Add CSS classes for Tailwind
        for field in self.fields.values():
            if 'class' in field.widget.attrs:
                field.widget.attrs['class'] += ' focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
            else:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'


class DocumentTemplateForm(forms.ModelForm):
    """Form for creating and editing document templates"""

    class Meta:
        model = DocumentTemplate
        fields = ['name', 'description', 'category', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add field help text
        self.fields['is_public'].help_text = "Make this template available to all users"

        # Add CSS classes for Tailwind
        for field in self.fields.values():
            if 'class' in field.widget.attrs:
                field.widget.attrs['class'] += ' focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
            else:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'


class DocumentCollaboratorForm(forms.ModelForm):
    """Form for adding collaborators to a document"""

    class Meta:
        model = DocumentCollaborator
        fields = ['employee', 'permission']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control select2'}),
            'permission': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        document = kwargs.pop('document', None)
        super().__init__(*args, **kwargs)

        # Filter out existing collaborators and the document author
        if document:
            existing_collaborators = DocumentCollaborator.objects.filter(
                document=document
            ).values_list('employee_id', flat=True)

            self.fields['employee'].queryset = Employee.objects.filter(
                is_active=True
            ).exclude(
                id__in=existing_collaborators
            ).exclude(
                id=document.author_id
            )
        else:
            self.fields['employee'].queryset = Employee.objects.filter(is_active=True)

        # Add CSS classes for Tailwind
        for field in self.fields.values():
            if 'class' in field.widget.attrs:
                field.widget.attrs['class'] += ' focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
            else:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'


class DocumentCommentForm(forms.ModelForm):
    """Form for adding comments to a document"""

    class Meta:
        model = DocumentComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add CSS classes for Tailwind
        for field in self.fields.values():
            if 'class' in field.widget.attrs:
                field.widget.attrs['class'] += ' focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
            else:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
