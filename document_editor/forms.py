from django import forms
from .models import (Document, DocumentTemplate, DocumentCollaborator, DocumentComment, Document, DocumentTemplate, DocumentCollaborator, DocumentComment,
                DocumentTemplateVariable, DocumentApprovalWorkflow, DocumentApprovalStep, preview_with_variables)
from core.models import Employee, Customer
from customer_projects.models import Project


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



class DocumentTemplateVariableForm(forms.ModelForm):
    """Form for creating and editing document template variables"""

    class Meta:
        model = DocumentTemplateVariable
        fields = [
            'name', 'display_name', 'variable_type', 'field_mapping',
            'default_value', 'description', 'required',
            'date_format', 'number_format'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'display_name': forms.TextInput(attrs={'class': 'form-control'}),
            'variable_type': forms.Select(attrs={'class': 'form-control'}),
            'field_mapping': forms.TextInput(attrs={'class': 'form-control'}),
            'default_value': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'date_format': forms.TextInput(attrs={'class': 'form-control'}),
            'number_format': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        template = kwargs.pop('template', None)
        super().__init__(*args, **kwargs)

        if template:
            self.instance.template = template

        # Add conditional field visibility based on variable_type
        self.fields['field_mapping'].widget.attrs['data-show-for'] = 'customer,project,employee'
        self.fields['date_format'].widget.attrs['data-show-for'] = 'date'
        self.fields['number_format'].widget.attrs['data-show-for'] = 'number,currency'

        # Help text for fields
        self.fields['name'].help_text = "Variable name used in templates (e.g., customer_name)"
        self.fields['display_name'].help_text = "Human-readable name shown to users"
        self.fields['field_mapping'].help_text = "For Customer/Project/Employee fields only (e.g., company_name, email)"
        self.fields['date_format'].help_text = "Python date format (e.g., %Y-%m-%d for 2023-01-31)"
        self.fields['number_format'].help_text = "Python format string (e.g., {:.2f} for 2 decimal places)"

        # Add CSS classes for better UI
        for field in self.fields.values():
            if 'class' in field.widget.attrs:
                field.widget.attrs['class'] += ' focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'
            else:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'

    def clean_name(self):
        """Ensure variable name is valid for template usage"""
        name = self.cleaned_data.get('name')
        if name:
            # Ensure the name contains only alphanumeric and underscore
            import re
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
                raise forms.ValidationError(
                    "Variable name must start with a letter and contain only letters, "
                    "numbers, and underscores."
                )
        return name


class DocumentTemplateFormWithVariables(forms.ModelForm):
    """Extended form for document templates with variables support"""

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


class ApplyTemplateForm(forms.Form):
    """Form for applying a template and its variables to create a document"""

    template = forms.ModelChoiceField(
        queryset=DocumentTemplate.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control select2'})
    )

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    document_type = forms.ChoiceField(
        choices=Document.DOCUMENT_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control select2'})
    )

    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),  # Will be populated based on customer
        required=False,
        widget=forms.Select(attrs={'class': 'form-control select2'})
    )

    # Dynamic fields for template variables will be added in __init__

    def __init__(self, *args, **kwargs):
        template_id = kwargs.pop('template_id', None)
        super().__init__(*args, **kwargs)

        # Initialize template variables if a template is provided
        if template_id:
            try:
                template = DocumentTemplate.objects.get(id=template_id)
                self.fields['template'].initial = template

                # Add dynamic fields for template variables
                for variable in template.variables.all():
                    field_name = f"var_{variable.name}"

                    # Create the appropriate field based on variable type
                    if variable.variable_type == 'date':
                        self.fields[field_name] = forms.DateField(
                            label=variable.display_name,
                            required=variable.required,
                            widget=forms.DateInput(attrs={
                                'class': 'form-control datepicker',
                                'placeholder': variable.date_format or 'YYYY-MM-DD'
                            }),
                            help_text=variable.description
                        )
                    elif variable.variable_type == 'number':
                        self.fields[field_name] = forms.FloatField(
                            label=variable.display_name,
                            required=variable.required,
                            widget=forms.NumberInput(attrs={
                                'class': 'form-control',
                                'step': 'any'
                            }),
                            help_text=variable.description
                        )
                    elif variable.variable_type == 'boolean':
                        self.fields[field_name] = forms.BooleanField(
                            label=variable.display_name,
                            required=False,
                            widget=forms.CheckboxInput(attrs={
                                'class': 'form-check-input'
                            }),
                            help_text=variable.description
                        )
                    elif variable.variable_type == 'currency':
                        self.fields[field_name] = forms.DecimalField(
                            label=variable.display_name,
                            required=variable.required,
                            decimal_places=2,
                            widget=forms.NumberInput(attrs={
                                'class': 'form-control',
                                'step': '0.01'
                            }),
                            help_text=variable.description
                        )
                    else:
                        # Default to text field
                        self.fields[field_name] = forms.CharField(
                            label=variable.display_name,
                            required=variable.required,
                            widget=forms.TextInput(attrs={'class': 'form-control'}),
                            help_text=variable.description
                        )

                    # Set initial value if default exists
                    if variable.default_value:
                        self.fields[field_name].initial = variable.default_value
            except DocumentTemplate.DoesNotExist:
                pass

        # Apply CSS classes for Tailwind
        for field in self.fields.values():
            if hasattr(field.widget, 'attrs') and 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'focus:ring-indigo-500 focus:border-indigo-500 block w-full shadow-sm sm:text-sm rounded-md'

    def get_variable_values(self):
        """Extract variable values from the form data"""
        variable_values = {}

        # Process regular fields
        variable_values['title'] = self.cleaned_data.get('title', '')
        variable_values['document_type'] = self.cleaned_data.get('document_type', '')

        # Process customer data if provided
        customer = self.cleaned_data.get('customer')
        if customer:
            variable_values['customer'] = customer

        # Process project data if provided
        project = self.cleaned_data.get('project')
        if project:
            variable_values['project'] = project

        # Process template variable fields (var_*)
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith('var_'):
                variable_name = field_name[4:]  # Remove 'var_' prefix
                variable_values[variable_name] = value

        return variable_values


class DocumentApprovalWorkflowForm(forms.ModelForm):
    """Form for setting up document approval workflow"""

    class Meta:
        model = DocumentApprovalWorkflow
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        document = kwargs.pop('document', None)
        super().__init__(*args, **kwargs)

        if document:
            self.instance.document = document


class DocumentApprovalStepForm(forms.ModelForm):
    """Form for adding approval steps to a workflow"""

    class Meta:
        model = DocumentApprovalStep
        fields = ['approver', 'order', 'department_required', 'position_required']
        widgets = {
            'approver': forms.Select(attrs={'class': 'form-control select2'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'department_required': forms.Select(attrs={'class': 'form-control'}),
            'position_required': forms.Select(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        workflow = kwargs.pop('workflow', None)
        super().__init__(*args, **kwargs)

        if workflow:
            self.instance.workflow = workflow

            # Filter approvers based on department/position if specified
            if self.instance.department_required or self.instance.position_required:
                queryset = Employee.objects.filter(is_active=True)

                if self.instance.department_required:
                    queryset = queryset.filter(department=self.instance.department_required)

                if self.instance.position_required:
                    queryset = queryset.filter(position=self.instance.position_required)

                self.fields['approver'].queryset = queryset
            else:
                self.fields['approver'].queryset = Employee.objects.filter(is_active=True)

        # Set order to next available if not specified
        if workflow and not self.instance.order:
            next_order = workflow.steps.count() + 1
            self.fields['order'].initial = next_order


class ApprovalResponseForm(forms.Form):
    """Form for responding to an approval request"""

    RESPONSE_CHOICES = (
        ('approve', 'Approve'),
        ('reject', 'Reject')
    )

    response = forms.ChoiceField(
        choices=RESPONSE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional comments about your decision'
        })
    )

    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Required when rejecting a document'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        response = cleaned_data.get('response')
        rejection_reason = cleaned_data.get('rejection_reason')

        if response == 'reject' and not rejection_reason:
            self.add_error('rejection_reason', 'Please provide a reason for rejection')

        return cleaned_data
