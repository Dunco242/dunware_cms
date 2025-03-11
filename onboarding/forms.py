from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Customer, Employee
from .models import (
    OnboardingPlan, OnboardingStep, CustomerOnboarding,
    OnboardingStepCompletion, DataImportJob, OnboardingFeedback,
    OnboardingChecklistItem, ChecklistItemCompletion
)


class CustomerOnboardingForm(forms.ModelForm):
    """
    Form for creating a new customer onboarding
    """
    class Meta:
        model = CustomerOnboarding
        fields = ['customer', 'plan', 'assigned_to', 'send_reminders']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'send_reminders': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only include active customers
        self.fields['customer'].queryset = Customer.objects.filter(status='active')

        # Only include active onboarding plans
        self.fields['plan'].queryset = OnboardingPlan.objects.filter(is_active=True)

        # Only include active employees
        self.fields['assigned_to'].queryset = Employee.objects.filter(is_active=True)
        self.fields['assigned_to'].required = False

        # Add helpful label information
        self.fields['send_reminders'].label = "Send automated reminder emails"
        self.fields['send_reminders'].help_text = "Uncheck this to disable automatic reminder emails for this customer."

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')

        # Check if customer already has an active onboarding
        if customer:
            existing = CustomerOnboarding.objects.filter(
                customer=customer,
                status__in=['not_started', 'in_progress', 'paused']
            ).exclude(pk=self.instance.pk if self.instance.pk else None).exists()

            if existing:
                raise ValidationError("This customer already has an active onboarding process.")

        return cleaned_data


class OnboardingStepCompletionForm(forms.ModelForm):
    """
    Form for marking an onboarding step as completed
    """
    class Meta:
        model = OnboardingStepCompletion
        fields = ['notes', 'satisfaction_rating']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'satisfaction_rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make fields optional
        self.fields['notes'].required = False
        self.fields['satisfaction_rating'].required = False
        self.fields['satisfaction_rating'].help_text = "Rate from 1 (poor) to 5 (excellent)"


class DataImportForm(forms.ModelForm):
    """
    Form for importing data from CSV/Excel files
    """
    class Meta:
        model = DataImportJob
        fields = ['import_type', 'source_name', 'source_file', 'notes']
        widgets = {
            'import_type': forms.Select(attrs={'class': 'form-select'}),
            'source_name': forms.TextInput(attrs={'class': 'form-control'}),
            'source_file': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add help text
        self.fields['import_type'].help_text = "What type of data are you importing?"
        self.fields['source_name'].help_text = "Name of the source system or file (e.g., 'Salesforce Export')"
        self.fields['source_file'].help_text = "Upload a CSV or Excel file (.xlsx, .xls, .csv)"
        self.fields['notes'].required = False

    def clean_source_file(self):
        source_file = self.cleaned_data.get('source_file')

        if source_file:
            # Check file extension
            allowed_extensions = ['.csv', '.xlsx', '.xls']
            ext = str(source_file.name).lower().split('.')[-1]

            if f'.{ext}' not in allowed_extensions:
                raise ValidationError(
                    f"Unsupported file type. Please upload a CSV or Excel file ({', '.join(allowed_extensions)})"
                )

            # Check file size (max 10MB)
            if source_file.size > 10 * 1024 * 1024:
                raise ValidationError("File size exceeds 10MB. Please upload a smaller file or contact support.")

        return source_file


class OnboardingFeedbackForm(forms.ModelForm):
    """
    Form for collecting feedback on the onboarding process
    """
    class Meta:
        model = OnboardingFeedback
        fields = [
            'overall_rating', 'ease_of_use_rating', 'support_rating',
            'what_worked_well', 'what_could_improve', 'additional_comments'
        ]
        widgets = {
            'overall_rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'ease_of_use_rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'support_rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'what_worked_well': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'what_could_improve': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'additional_comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
        }

    # Hidden fields for the relationship
    customer_onboarding = forms.ModelChoiceField(
        queryset=CustomerOnboarding.objects.all(),
        widget=forms.HiddenInput(),
        required=True
    )

    step = forms.ModelChoiceField(
        queryset=OnboardingStep.objects.all(),
        widget=forms.HiddenInput(),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add help text for ratings
        self.fields['overall_rating'].help_text = "Rate your overall experience (1-5)"
        self.fields['ease_of_use_rating'].help_text = "How easy was it to complete this step? (1-5)"
        self.fields['support_rating'].help_text = "Rate the support you received (1-5)"
        self.fields['support_rating'].required = False

        # Add placeholders for text fields
        self.fields['what_worked_well'].widget.attrs['placeholder'] = "What aspects of the process worked well for you?"
        self.fields['what_could_improve'].widget.attrs['placeholder'] = "What could we improve about this process?"
        self.fields['additional_comments'].widget.attrs['placeholder'] = "Any other comments you'd like to share?"

        # Make text fields optional
        self.fields['what_worked_well'].required = False
        self.fields['what_could_improve'].required = False
        self.fields['additional_comments'].required = False


class ChecklistItemCompletionForm(forms.ModelForm):
    """
    Form for marking checklist items as completed
    """
    class Meta:
        model = ChecklistItemCompletion
        fields = ['is_completed', 'notes']
        widgets = {
            'is_completed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False


class OnboardingPlanSelectionForm(forms.Form):
    """
    Form for selecting an onboarding plan for a new customer
    """
    plan = forms.ModelChoiceField(
        queryset=OnboardingPlan.objects.filter(is_active=True),
        empty_label=None,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    welcome_call_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={'class': 'form-control datepicker', 'type': 'datetime-local'}
        ),
        help_text="Schedule a welcome call (optional)"
    )

    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text="Any special requirements or notes for this customer's onboarding"
    )

    def clean_welcome_call_date(self):
        welcome_call_date = self.cleaned_data.get('welcome_call_date')

        if welcome_call_date:
            # Ensure date is in the future
            if welcome_call_date < timezone.now():
                raise ValidationError("The welcome call date must be in the future.")

            # Ensure date is within business hours (9AM-5PM)
            if welcome_call_date.hour < 9 or welcome_call_date.hour >= 17:
                raise ValidationError("Please schedule the welcome call during business hours (9AM-5PM).")

        return welcome_call_date
