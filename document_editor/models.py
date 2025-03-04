from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Q, Max
import json, re
from core.models import Employee, Customer


from core.models import Employee, Customer


class Document(models.Model):
    """Model for document management"""

    # Document type choices
    DOCUMENT_TYPES = (
        ('contract', 'Contract'),
        ('proposal', 'Proposal'),
        ('report', 'Report'),
        ('letter', 'Letter'),
        ('invoice', 'Invoice'),
        ('memo', 'Memo'),
        ('other', 'Other'),
    )

    # Document status choices
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    )

    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Document content stored as JSON (Slate.js format)
    content = models.JSONField(null=True, blank=True)

    # Plain text extraction for search
    plain_text = models.TextField(blank=True)

    # Metadata
    author = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='authored_documents'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_documents'
    )

    # Tags as comma-separated string
    tags = models.CharField(max_length=255, blank=True)

    # Template and visibility flags
    is_template = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    # Versioning fields
    parent_document = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_versions'  # Changed from 'versions' to avoid conflict
    )
    version = models.IntegerField(default=1)
    is_latest_version = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['author']),
            models.Index(fields=['document_type']),
            models.Index(fields=['status']),
            models.Index(fields=['is_template']),
            models.Index(fields=['is_latest_version']),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version})"

    def extract_plain_text(self):
        """Extract plain text from Slate.js content for search"""
        if not self.content:
            return ""

        text_parts = []

        try:
            # Process nodes recursively
            def extract_text(nodes):
                if not isinstance(nodes, list):
                    return

                for node in nodes:
                    if not isinstance(node, dict):
                        continue

                    if 'text' in node and node['text']:
                        text_parts.append(node['text'])
                    elif 'children' in node and isinstance(node['children'], list):
                        extract_text(node['children'])

            # Start extraction from the root
            children = self.content.get('children', [])
            if not isinstance(children, list):
                return ""

            extract_text(children)

            # Join text parts with space and normalize whitespace
            result = ' '.join(text_parts)
            # Replace multiple spaces with a single space
            import re
            result = re.sub(r'\s+', ' ', result).strip()
            return result
        except Exception as e:
            import traceback
            print(f"Error extracting text: {str(e)}")
            print(traceback.format_exc())
            return f"Error extracting text: {str(e)}"

    def get_all_versions(self):
        """Get all versions of this document"""
        if self.parent_document:
            # This is not the original document
            original = self.parent_document
            while original.parent_document:
                original = original.parent_document

            # Get all versions including the original
            return Document.objects.filter(
                Q(id=original.id) | Q(parent_document=original)
            ).order_by('version')
        else:
            # This is the original document
            return Document.objects.filter(
                Q(id=self.id) | Q(parent_document=self)
            ).order_by('version')

    def can_user_edit(self, user):
        """Check if a user has permission to edit this document"""
        if not hasattr(user, 'employee_profile'):
            return False

        employee = user.employee_profile

        # Document author can always edit
        if self.author == employee:
            return True

        # Check collaborator permissions
        try:
            collaborator = self.collaborators.get(employee=employee)
            return collaborator.permission in ['edit', 'manage']
        except Exception:
            return False


class DocumentVersion(models.Model):
    """Model for storing document versions"""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='version_history'  # Changed from 'versions' to avoid conflict
    )
    version_number = models.PositiveIntegerField()
    content = models.JSONField()
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='created_document_versions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ['document', 'version_number']

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"

    @staticmethod
    def get_next_version_number(document):
        """Get the next version number for a document"""
        max_version = DocumentVersion.objects.filter(
            document=document
        ).aggregate(
            max_version=Max('version_number')
        )['max_version'] or 0

        return max_version + 1


class DocumentCollaborator(models.Model):
    """Model for document collaborators"""

    PERMISSION_CHOICES = (
        ('view', 'View Only'),
        ('comment', 'Can Comment'),
        ('edit', 'Can Edit'),
        ('manage', 'Can Manage'),
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='collaborators'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='document_collaborations'
    )
    permission = models.CharField(
        max_length=10,
        choices=PERMISSION_CHOICES,
        default='view'
    )
    added_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='added_collaborators'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['document', 'employee']
        indexes = [
            models.Index(fields=['document']),
            models.Index(fields=['employee']),
        ]

    def __str__(self):
        return f"{self.employee} - {self.get_permission_display()} - {self.document.title}"


class DocumentComment(models.Model):
    """Model for document comments"""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='document_comments'
    )
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Selection info for contextual comments
    selection_start = models.JSONField(null=True, blank=True)
    selection_end = models.JSONField(null=True, blank=True)
    selected_text = models.TextField(blank=True)

    # Resolution status
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_comments'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document']),
            models.Index(fields=['author']),
            models.Index(fields=['is_resolved']),
        ]

    def __str__(self):
        return f"Comment by {self.author} on {self.document.title}"

    def resolve(self, employee):
        """Mark comment as resolved"""
        self.is_resolved = True
        self.resolved_by = employee
        self.resolved_at = timezone.now()
        self.save()


class DocumentTemplate(models.Model):
    """Model for document templates"""

    TEMPLATE_CATEGORIES = (
        ('contract', 'Contracts'),
        ('proposal', 'Proposals'),
        ('report', 'Reports'),
        ('letter', 'Letters'),
        ('invoice', 'Invoices'),
        ('form', 'Forms'),
        ('other', 'Other'),
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content = models.JSONField(null=True, blank=True)
    category = models.CharField(max_length=20, choices=TEMPLATE_CATEGORIES)
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_public']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return self.name


class DocumentEditSession(models.Model):
    """Model to track document editing sessions for WebSocket connections"""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='edit_sessions'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_sessions'
    )

    start_time = models.DateTimeField(
        default=timezone.now,
        help_text="When the editing session started"
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the editing session ended"
    )

    last_activity = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp of last activity in this session"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this session is currently active"
    )

    client_info = models.CharField(
        max_length=255,
        blank=True,
        help_text="Client information (browser, IP, etc.)"
    )

    class Meta:
        indexes = [
            models.Index(fields=['document', 'is_active']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['last_activity']),
        ]

    def __str__(self):
        return f"Session for {self.document.title} by {self.user.username}"

    def end_session(self):
        """End this editing session"""
        self.is_active = False
        self.end_time = timezone.now()
        self.save()


class DocumentApprovalWorkflow(models.Model):
    """Model for document approval workflows"""

    WORKFLOW_STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
    )

    document = models.OneToOneField(
        'Document',
        on_delete=models.CASCADE,
        related_name='approval_workflow'
    )

    status = models.CharField(
        max_length=20,
        choices=WORKFLOW_STATUS_CHOICES,
        default='draft'
    )

    current_approver = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pending_approvals'
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Approval for {self.document.title} - {self.get_status_display()}"

    def start_workflow(self):
        """Start the approval workflow"""
        # Find the first approver
        first_step = self.steps.filter(order=1).first()
        if first_step:
            self.current_approver = first_step.approver
            self.status = 'pending'
            self.started_at = now()
            self.save()

            # Create approval request
            DocumentApprovalRequest.objects.create(
                workflow=self,
                step=first_step,
                approver=first_step.approver,
                status='pending'
            )
            return True
        return False

    def approve_current_step(self, comments=''):
        """Approve the current step and move to the next if available"""
        # Find and update the current approval request
        current_request = DocumentApprovalRequest.objects.filter(
            workflow=self,
            approver=self.current_approver,
            status='pending'
        ).first()

        if current_request:
            current_request.status = 'approved'
            current_request.response_date = now()
            current_request.comments = comments
            current_request.save()

            # Find the next step
            current_step = current_request.step
            next_step = self.steps.filter(order__gt=current_step.order).order_by('order').first()

            if next_step:
                # Move to next approver
                self.current_approver = next_step.approver
                self.save()

                # Create new approval request
                DocumentApprovalRequest.objects.create(
                    workflow=self,
                    step=next_step,
                    approver=next_step.approver,
                    status='pending'
                )
                return True
            else:
                # No more steps, workflow is complete
                self.status = 'approved'
                self.current_approver = None
                self.completed_at = now()
                self.save()

                # Update document status
                self.document.status = 'approved'
                self.document.save()
                return True

        return False

    def reject(self, reason):
        """Reject the document and end workflow"""
        # Find and update the current approval request
        current_request = DocumentApprovalRequest.objects.filter(
            workflow=self,
            approver=self.current_approver,
            status='pending'
        ).first()

        if current_request:
            current_request.status = 'rejected'
            current_request.response_date = now()
            current_request.comments = reason
            current_request.save()

            # Update workflow status
            self.status = 'rejected'
            self.rejection_reason = reason
            self.completed_at = now()
            self.save()

            # Update document status
            self.document.status = 'review'
            self.document.save()
            return True

        return False

    def cancel(self):
        """Cancel the workflow"""
        # Cancel any pending requests
        DocumentApprovalRequest.objects.filter(
            workflow=self,
            status='pending'
        ).update(status='canceled')

        # Update workflow status
        self.status = 'canceled'
        self.completed_at = now()
        self.current_approver = None
        self.save()
        return True

    @property
    def progress_percentage(self):
        """Calculate workflow progress as a percentage"""
        total_steps = self.steps.count()
        if total_steps == 0:
            return 0

        approved_steps = DocumentApprovalRequest.objects.filter(
            workflow=self,
            status='approved'
        ).count()

        return int((approved_steps / total_steps) * 100)

    @property
    def current_step(self):
        """Get the current step in the workflow"""
        if not self.current_approver:
            return None

        return self.steps.filter(approver=self.current_approver).first()


class DocumentApprovalStep(models.Model):
    """Model for steps in a document approval workflow"""

    workflow = models.ForeignKey(
        DocumentApprovalWorkflow,
        on_delete=models.CASCADE,
        related_name='steps'
    )

    approver = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='approval_steps'
    )

    order = models.PositiveIntegerField(default=1)

    # Optional role-based approval
    department_required = models.CharField(
        max_length=100,
        blank=True,
        choices=Employee.DEPARTMENT_CHOICES
    )

    position_required = models.CharField(
        max_length=100,
        blank=True,
        choices=Employee.POSITION_CHOICES
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['workflow', 'order']
        unique_together = ['workflow', 'order']

    def __str__(self):
        return f"Step {self.order}: {self.approver.get_full_name()}"


class DocumentApprovalRequest(models.Model):
    """Model for tracking approval requests and responses"""

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
    )

    workflow = models.ForeignKey(
        DocumentApprovalWorkflow,
        on_delete=models.CASCADE,
        related_name='requests'
    )

    step = models.ForeignKey(
        DocumentApprovalStep,
        on_delete=models.CASCADE,
        related_name='requests'
    )

    approver = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='approval_requests'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    request_date = models.DateTimeField(auto_now_add=True)
    response_date = models.DateTimeField(null=True, blank=True)

    comments = models.TextField(blank=True)

    class Meta:
        ordering = ['-request_date']

    def __str__(self):
        return f"Request for {self.approver.get_full_name()} - {self.get_status_display()}"


# Add to existing DocumentTemplate model class
class DocumentTemplateVariable(models.Model):
    """Model for defining variables in document templates"""

    VARIABLE_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Yes/No'),
        ('currency', 'Currency'),
        ('customer', 'Customer Field'),
        ('project', 'Project Field'),
        ('employee', 'Employee Field'),
    )

    template = models.ForeignKey(
        'DocumentTemplate',
        on_delete=models.CASCADE,
        related_name='variables'
    )

    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255)
    variable_type = models.CharField(
        max_length=20,
        choices=VARIABLE_TYPES
    )

    # For customer/project/employee field mapping
    field_mapping = models.CharField(
        max_length=100,
        blank=True,
        help_text="Field name in the related model"
    )

    default_value = models.CharField(
        max_length=255,
        blank=True,
        help_text="Default value if no value is provided"
    )

    description = models.TextField(
        blank=True,
        help_text="Description of the variable for users"
    )

    required = models.BooleanField(default=False)

    # Optional format settings
    date_format = models.CharField(
        max_length=50,
        blank=True,
        help_text="Format string for date variables (e.g., '%Y-%m-%d')"
    )

    number_format = models.CharField(
        max_length=50,
        blank=True,
        help_text="Format string for number variables (e.g., '{:.2f}')"
    )

    class Meta:
        ordering = ['name']
        unique_together = ['template', 'name']

    def __str__(self):
        return f"{self.display_name} ({self.name})"

    def get_variable_placeholder(self):
        """Get the placeholder syntax for this variable"""
        return f"{{{{ {self.name} }}}}"

    def format_value(self, value):
        """Format a value based on variable type"""
        if value is None or value == '':
            return self.default_value

        try:
            # Format based on variable type
            if self.variable_type == 'date' and self.date_format:
                from datetime import datetime
                if isinstance(value, str):
                    # Try to parse the string as a date
                    try:
                        value = datetime.strptime(value, '%Y-%m-%d')
                    except ValueError:
                        pass

                if isinstance(value, datetime):
                    return value.strftime(self.date_format)

            elif self.variable_type == 'number' and self.number_format:
                try:
                    num_value = float(value)
                    return self.number_format.format(num_value)
                except (ValueError, TypeError):
                    pass

            elif self.variable_type == 'currency':
                try:
                    num_value = float(value)
                    return f"${num_value:,.2f}"
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            # If formatting fails, return the original value
            pass

        return str(value)


# New function for Document model to process template variables
def process_template_variables(document, variables_dict):
    """
    Process a document's content by replacing template variables with values.

    Args:
        document: The Document instance to process
        variables_dict: Dictionary of variable names and their values

    Returns:
        Updated document content with variables replaced
    """
    if not document.content:
        return document.content

    content = document.content

    # Regular expression to find template variables in the form {{ variable_name }}
    variable_pattern = r'{{[\s]*([a-zA-Z0-9_\.]+)[\s]*}}'

    def replace_variable(match):
        var_name = match.group(1).strip()

        # Check if the variable exists in the provided dictionary
        if var_name in variables_dict:
            return str(variables_dict[var_name])

        # Check if it's a nested attribute access like 'customer.name'
        if '.' in var_name:
            parts = var_name.split('.')
            root_obj = variables_dict.get(parts[0])
            if root_obj:
                try:
                    value = root_obj
                    for part in parts[1:]:
                        if hasattr(value, part):
                            value = getattr(value, part)
                        elif isinstance(value, dict) and part in value:
                            value = value[part]
                        else:
                            return match.group(0)  # Return the original if attribute not found
                    return str(value)
                except Exception:
                    pass

        # If variable not found, return the original placeholder
        return match.group(0)

    # Function to process text nodes in the document content
    def process_node(node):
        if isinstance(node, dict):
            if 'text' in node:
                node['text'] = re.sub(variable_pattern, replace_variable, node['text'])
            elif 'children' in node and isinstance(node['children'], list):
                for child in node['children']:
                    process_node(child)
        elif isinstance(node, list):
            for item in node:
                process_node(item)

    # Process the document content
    process_node(content)

    return content


# New function for DocumentTemplate model to preview with variables
def preview_with_variables(template, variables_dict):
    """
    Generate a preview of a template with variables replaced.

    Args:
        template: The DocumentTemplate instance
        variables_dict: Dictionary of variable names and their values

    Returns:
        Processed content with variables replaced
    """
    if not template.content:
        return template.content

    # Create a deep copy of the content to avoid modifying the original
    import copy
    content = copy.deepcopy(template.content)

    # Process variables
    return process_template_variables({'content': content}, variables_dict)['content']
