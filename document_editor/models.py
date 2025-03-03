from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Max
import json

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
