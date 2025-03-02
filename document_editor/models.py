from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import Employee, Customer

class Document(models.Model):
    """
    Document model for storing document content and metadata
    """
    DOCUMENT_TYPES = [
        ('text', 'Text Document'),
        ('rich', 'Rich Text Document'),
        ('markdown', 'Markdown Document'),
        ('contract', 'Contract'),
        ('proposal', 'Proposal'),
        ('other', 'Other')
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('published', 'Published'),
        ('archived', 'Archived')
    ]

    # Basic Information
    title = models.CharField(max_length=255)
    content = models.JSONField(default=dict, help_text="Slate.js compatible document content")
    plain_text = models.TextField(blank=True, help_text="Plain text version for search indexing")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, default='text')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Relationships
    author = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_documents'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_documents'
    )

    # Version Control
    version = models.PositiveIntegerField(default=1)
    is_latest_version = models.BooleanField(default=True)
    parent_document = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions'
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags")

    # Document Settings
    is_template = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['document_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_template']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.pk and self.parent_document:
            # If this is a new version of an existing document
            # Mark previous version as not latest
            self.parent_document.is_latest_version = False
            self.parent_document.save(update_fields=['is_latest_version'])

            # Set version number
            self.version = self.parent_document.version + 1

        super().save(*args, **kwargs)

    def create_new_version(self, content, user):
        """Create a new version of this document"""
        new_version = Document.objects.create(
            title=self.title,
            content=content,
            document_type=self.document_type,
            status='draft',
            author=user,
            customer=self.customer,
            parent_document=self,
            version=self.version + 1,
            tags=self.tags,
            is_template=self.is_template,
            is_public=self.is_public,
        )
        self.is_latest_version = False
        self.save(update_fields=['is_latest_version'])
        return new_version

    def get_all_versions(self):
        """Get all versions of this document"""
        if self.parent_document:
            # If this is a child version, get the original parent
            root = self.parent_document
            while root.parent_document:
                root = root.parent_document
            return root.versions.all().order_by('-version')
        else:
            # If this is the original document
            return self.versions.all().order_by('-version')

    def extract_plain_text(self):
        """Extract plain text from Slate.js content for search indexing"""
        # Implement this method based on your specific Slate.js structure
        # For now, we'll use a placeholder
        if self.content:
            # This is a simplified example - you'll need to adapt based on your Slate structure
            try:
                # For a basic slate document with text nodes
                text = []
                for node in self.content.get('children', []):
                    if isinstance(node, dict) and 'text' in node:
                        text.append(node['text'])
                    elif isinstance(node, dict) and 'children' in node:
                        for child in node['children']:
                            if isinstance(child, dict) and 'text' in child:
                                text.append(child['text'])
                return ' '.join(text)
            except Exception:
                return ""
        return ""


class DocumentCollaborator(models.Model):
    """Model to track document collaborators and their permissions"""

    PERMISSION_CHOICES = [
        ('view', 'View Only'),
        ('comment', 'Can Comment'),
        ('edit', 'Can Edit'),
        ('manage', 'Can Manage')
    ]

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
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='added_collaborators'
    )

    class Meta:
        unique_together = ['document', 'employee']
        ordering = ['document', 'employee__user__first_name']

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.get_permission_display()}"


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
    content = models.TextField()

    # For selecting specific text in the document
    selection_start = models.JSONField(null=True, blank=True)
    selection_end = models.JSONField(null=True, blank=True)
    selected_text = models.TextField(blank=True)

    # For threading comments
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.get_full_name()} on {self.document.title}"

    def resolve(self, user):
        """Mark comment as resolved"""
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save()


class DocumentTemplate(models.Model):
    """Model for document templates that can be reused"""

    TEMPLATE_CATEGORIES = [
        ('contract', 'Contract'),
        ('proposal', 'Proposal'),
        ('letter', 'Letter'),
        ('report', 'Report'),
        ('other', 'Other')
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content = models.JSONField(default=dict)
    category = models.CharField(max_length=20, choices=TEMPLATE_CATEGORIES)

    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Template settings
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def create_document(self, title, author, customer=None):
        """Create a new document from this template"""
        return Document.objects.create(
            title=title,
            content=self.content,
            document_type=self.category,
            status='draft',
            author=author,
            customer=customer,
            is_template=False
        )
