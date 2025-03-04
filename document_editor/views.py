from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
    TemplateView, FormView
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
import json
from django import forms
import logging
import re
import traceback

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.models import Employee, Customer
from core.mixins import EmployeeRequiredMixin

from .models import (
    Document, DocumentCollaborator, DocumentComment, DocumentTemplate, DocumentVersion, DocumentTemplateVariable, DocumentApprovalWorkflow, DocumentApprovalStep,
    DocumentApprovalRequest, process_template_variables
)
from .forms import (
    DocumentForm, DocumentTemplateForm, DocumentCollaboratorForm, DocumentCommentForm, DocumentTemplateVariableForm, DocumentTemplateFormWithVariables, ApplyTemplateForm,
    DocumentApprovalWorkflowForm, DocumentApprovalStepForm, ApprovalResponseForm, preview_with_variables
)

logger = logging.getLogger(__name__)

# Document List Views

class DocumentListView(LoginRequiredMixin, EmployeeRequiredMixin, ListView):
    """View for listing user's documents"""
    model = Document
    template_name = 'document_editor/document_list.html'
    context_object_name = 'documents'
    paginate_by = 12

    def get_queryset(self):
        """Get documents the user has access to"""
        employee = self.request.user.employee_profile

        # Include documents created by user or shared with them
        queryset = Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee)
        ).distinct()

        # Filter by status if provided
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Filter by document type if provided
        doc_type = self.request.GET.get('type')
        if doc_type:
            queryset = queryset.filter(document_type=doc_type)

        # Filter by customer if provided
        customer_id = self.request.GET.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        # Search by title if provided
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(plain_text__icontains=search) |
                Q(tags__icontains=search)
            )

        # Filter by template status if provided
        is_template = self.request.GET.get('is_template')
        if is_template is not None:
            is_template_bool = is_template.lower() == 'true'
            queryset = queryset.filter(is_template=is_template_bool)

        # Only get latest versions by default, unless viewing history
        show_all_versions = self.request.GET.get('all_versions') == 'true'
        if not show_all_versions:
            queryset = queryset.filter(is_latest_version=True)

        return queryset.select_related('author', 'customer')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_profile

        # Add document stats
        context['document_count'] = Document.objects.filter(
            author=employee,
            is_latest_version=True
        ).count()

        context['draft_count'] = Document.objects.filter(
            author=employee,
            status='draft',
            is_latest_version=True
        ).count()

        context['published_count'] = Document.objects.filter(
            author=employee,
            status='published',
            is_latest_version=True
        ).count()

        context['shared_count'] = Document.objects.filter(
            collaborators__employee=employee
        ).distinct().count()

        # Add filter options
        context['document_types'] = dict(Document.DOCUMENT_TYPES)
        context['status_choices'] = dict(Document.STATUS_CHOICES)
        context['customers'] = Customer.objects.all()

        # Add current filters
        context['current_filters'] = {
            'status': self.request.GET.get('status', ''),
            'type': self.request.GET.get('type', ''),
            'customer': self.request.GET.get('customer', ''),
            'search': self.request.GET.get('search', ''),
            'is_template': self.request.GET.get('is_template', '')
        }

        return context


class DocumentTemplateListView(LoginRequiredMixin, EmployeeRequiredMixin, ListView):
    """View for listing available document templates"""
    model = DocumentTemplate
    template_name = 'document_editor/template_list.html'
    context_object_name = 'templates'
    paginate_by = 12

    def get_queryset(self):
        """Get templates the user has access to"""
        employee = self.request.user.employee_profile

        # Users can see public templates or ones they created
        queryset = DocumentTemplate.objects.filter(
            Q(is_public=True) | Q(created_by=employee)
        )

        # Filter by category if provided
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)

        # Search by name or description
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset.select_related('created_by')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add template categories for filtering
        context['categories'] = dict(DocumentTemplate.TEMPLATE_CATEGORIES)

        # Add current filters
        context['current_filters'] = {
            'category': self.request.GET.get('category', ''),
            'search': self.request.GET.get('search', '')
        }

        return context


# Document Detail and Editor Views

class DocumentDetailView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    """View for document details (metadata, sharing options)"""
    model = Document
    template_name = 'document_editor/document_detail.html'
    context_object_name = 'document'

    def get_queryset(self):
        """Ensure user has access to the document"""
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_object()
        employee = self.request.user.employee_profile

        # Check user permission level
        if document.author == employee:
            context['permission'] = 'manage'
        else:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
                context['permission'] = collaborator.permission
            except DocumentCollaborator.DoesNotExist:
                context['permission'] = None

        # Add collaborators
        context['collaborators'] = document.collaborators.all()

        # Add document versions
        if hasattr(document, 'parent_document') and document.parent_document:
            context['versions'] = document.get_all_versions()
        elif hasattr(document, 'document_versions') and document.document_versions.exists():
            context['versions'] = document.get_all_versions()

        # Add comments if user can view them
        if context['permission'] in ['manage', 'edit', 'comment', 'view']:
            context['comments'] = DocumentComment.objects.filter(
                document=document,
                parent_comment=None
            ).order_by('-created_at')

            # Also count unresolved comments
            context['unresolved_count'] = DocumentComment.objects.filter(
                document=document,
                is_resolved=False
            ).count()

        return context


class DocumentEditorView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    """View for document editor interface"""
    model = Document
    template_name = 'document_editor/document_editor.html'
    context_object_name = 'document'

    def get_queryset(self):
        """Ensure user has access to the document"""
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_object()
        employee = self.request.user.employee_profile

        # Determine permission levels and convert to string format for template
        if document.author == employee:
            context['can_edit'] = 'True'
            context['can_comment'] = 'True'
        else:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
                context['can_edit'] = 'True' if collaborator.permission in ['edit', 'manage'] else 'False'
                context['can_comment'] = 'True' if collaborator.permission in ['comment', 'edit', 'manage'] else 'False'
            except DocumentCollaborator.DoesNotExist:
                context['can_edit'] = 'False'
                context['can_comment'] = 'False'

        # Load comments
        context['comments'] = DocumentComment.objects.filter(
            document=document
        ).order_by('created_at')

        # Prepare document content or default empty structure
        default_content = {
            "children": [
                {
                    "type": "paragraph",
                    "children": [
                        {
                            "text": ""
                        }
                    ]
                }
            ]
        }

        context['document_content'] = json.dumps(
            document.content or default_content,
            separators=(',', ':')
        )

        return context


class UpdateDocumentView(LoginRequiredMixin, EmployeeRequiredMixin, UpdateView):
    """View to update document metadata (not content)"""
    model = Document
    form_class = DocumentForm
    template_name = 'document_editor/document_form.html'

    def get_queryset(self):
        """Ensure user has permission to edit the document"""
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee, collaborators__permission__in=['edit', 'manage'])
        ).distinct()

    def form_valid(self, form):
        """Process the form if valid"""
        response = super().form_valid(form)
        messages.success(self.request, f"Document '{form.instance.title}' updated successfully.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['document'] = self.object  # This ensures 'document' is in the context
        return context

class DeleteDocumentView(LoginRequiredMixin, EmployeeRequiredMixin, DeleteView):
    """View to delete a document"""
    model = Document
    template_name = 'document_editor/document_confirm_delete.html'
    success_url = reverse_lazy('document_editor:document_list')

    def get_queryset(self):
        """Ensure user has permission to delete the document"""
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee, collaborators__permission='manage')
        ).distinct()

    def delete(self, request, *args, **kwargs):
        document = self.get_object()
        messages.success(request, f"Document '{document.title}' deleted successfully.")
        return super().delete(request, *args, **kwargs)


# AJAX Endpoints for the Editor

@login_required
@require_POST
def save_document_content(request, document_id):
    """Save document content and optionally create a version."""
    try:
        # Get the document
        document = get_object_or_404(Document, id=document_id)

        # Verify user permissions
        if not hasattr(request.user, 'employee_profile'):
            return JsonResponse({
                'success': False,
                'error': 'No employee profile found'
            }, status=403)

        employee = request.user.employee_profile
        if document.author != employee:
            try:
                collaborator = document.collaborators.get(employee=employee)
                if collaborator.permission not in ['comment', 'edit', 'manage']:
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to comment on this document'
                    }, status=403)
            except Exception:  # Use a broader exception to match the save_document_content approach
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to comment on this document'
                }, status=403)

        # Extract content from request.POST
        content_str = request.POST.get('content')
        create_version = request.POST.get('create_version') == 'true'

        if not content_str or content_str.isspace():
            return JsonResponse({
                'success': False,
                'error': 'No content provided'
            }, status=400)

        # Parse the JSON content
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON content: {str(e)}'
            }, status=400)

        # Extract plain text using a direct approach
        plain_text = ""

        def extract_all_text(obj):
            nonlocal plain_text
            if isinstance(obj, dict):
                # Get text from this node if it exists
                if 'text' in obj and obj['text']:
                    plain_text += obj['text'] + " "

                # Process all fields that could contain nested content
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        extract_all_text(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_all_text(item)

        extract_all_text(content)

        # Clean up the plain text
        plain_text = plain_text.strip()

        # Normalize whitespace
        import re
        plain_text = re.sub(r'\s+', ' ', plain_text)

        # Log extracted plain text for debugging
        print(f"Extracted plain_text ({len(plain_text)} chars): {plain_text[:100]}...")

        # Update document content and plain_text
        document.content = content
        document.plain_text = plain_text
        document.updated_by = employee
        document.updated_at = timezone.now()

        # Create version if requested
        if create_version:
            # Get the next version number
            try:
                latest_version = DocumentVersion.objects.filter(document=document).order_by('-version_number').first()
                version = (latest_version.version_number + 1) if latest_version else 1
            except Exception:
                # Fallback to document version if available
                version = document.version + 1 if hasattr(document, 'version') else 1

            # Create the version
            DocumentVersion.objects.create(
                document=document,
                version_number=version,
                content=content,
                created_by=employee
            )

            # Update document version if applicable
            if hasattr(document, 'version'):
                document.version = version

        # Save the document using a direct update to ensure both fields are updated
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE document_editor_document
                SET content = %s, plain_text = %s, updated_at = %s, updated_by_id = %s
                WHERE id = %s
                """,
                [
                    json.dumps(content),
                    plain_text,
                    timezone.now(),
                    employee.id,
                    document.id
                ]
            )

        # Refresh from database to ensure we have the latest values
        document.refresh_from_db()

        # Log after save for debugging
        print(f"After save - Document ID: {document.id}")
        print(f"After save - Plain text length: {len(document.plain_text)}")
        print(f"After save - Plain text preview: {document.plain_text[:100]}")

        # Try to notify other users via WebSocket
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"document_{document.id}",
                {
                    "type": "document_saved",
                    "document_id": document.id,
                    "user_id": request.user.id,
                    "user_name": request.user.get_full_name() if hasattr(request.user, 'get_full_name') else request.user.username,
                    "updated_at": document.updated_at.isoformat()
                }
            )
        except Exception as e:
            print(f"WebSocket notification error: {str(e)}")
            # Don't fail the save if notification fails

        return JsonResponse({
            'success': True,
            'updated_at': document.updated_at.isoformat(),
            'plain_text_length': len(document.plain_text),
            'version': version if create_version else document.version
        })

    except Exception as e:
        import traceback
        print(f"Error saving document: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# The WebSocket notification helper function
def notify_document_saved(document, user):
    """
    Send a WebSocket notification to all users viewing the document
    that the document has been saved.
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"document_{document.id}",
            {
                "type": "document_saved",
                "document_id": document.id,
                "user_id": user.id,
                "user_name": user.get_full_name() if hasattr(user, 'get_full_name') else user.username,
                "updated_at": document.updated_at.isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Error in notify_document_saved: {str(e)}")


@login_required
@require_POST
def add_collaborator(request, pk):
    """AJAX endpoint to add a collaborator to a document"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check if user has permission to add collaborators (must be author or manager)
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee,
                    permission='manage'
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to add collaborators to this document.'
                }, status=403)

        # Get the collaborator data
        data = json.loads(request.body)
        collaborator_id = data.get('employee_id')
        permission = data.get('permission', 'view')

        if not collaborator_id:
            return JsonResponse({
                'success': False,
                'error': 'Collaborator ID is required.'
            }, status=400)

        # Validate permission
        if permission not in dict(DocumentCollaborator.PERMISSION_CHOICES):
            return JsonResponse({
                'success': False,
                'error': 'Invalid permission level.'
            }, status=400)

        # Get the collaborator
        try:
            collaborator_employee = Employee.objects.get(id=collaborator_id)
        except Employee.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employee not found.'
            }, status=404)

        # Don't allow adding the document owner as a collaborator
        if collaborator_employee == document.author:
            return JsonResponse({
                'success': False,
                'error': 'Cannot add document owner as a collaborator.'
            }, status=400)

        # Create or update the collaborator
        collaborator, created = DocumentCollaborator.objects.update_or_create(
            document=document,
            employee=collaborator_employee,
            defaults={
                'permission': permission,
                'added_by': employee
            }
        )

        return JsonResponse({
            'success': True,
            'collaborator': {
                'id': collaborator.id,
                'employee': {
                    'id': collaborator_employee.id,
                    'name': collaborator_employee.get_full_name()
                },
                'permission': collaborator.permission,
                'permission_display': collaborator.get_permission_display(),
                'added_at': collaborator.added_at.isoformat(),
                'added_by': employee.get_full_name()
            },
            'created': created
        })

    except Exception as e:
        logger.error(f"Error adding collaborator: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def remove_collaborator(request, pk, collaborator_id):
    """AJAX endpoint to remove a collaborator from a document"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check if user has permission to remove collaborators
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee,
                    permission='manage'
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to remove collaborators from this document.'
                }, status=403)

        # Get the collaborator to remove
        try:
            collaborator = DocumentCollaborator.objects.get(id=collaborator_id, document=document)
        except DocumentCollaborator.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Collaborator not found.'
            }, status=404)

        # Delete the collaborator
        collaborator.delete()

        return JsonResponse({
            'success': True,
            'message': 'Collaborator removed successfully.'
        })

    except Exception as e:
        logger.error(f"Error removing collaborator: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def update_collaborator_permission(request, pk, collaborator_id):
    """AJAX endpoint to update a collaborator's permission level"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check if user has permission to update collaborators
        if document.author != employee:
            try:
                user_collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee,
                    permission='manage'
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to update collaborator permissions.'
                }, status=403)

        # Get the collaborator to update
        try:
            collaborator = DocumentCollaborator.objects.get(id=collaborator_id, document=document)
        except DocumentCollaborator.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Collaborator not found.'
            }, status=404)

        # Get the new permission level
        data = json.loads(request.body)
        permission = data.get('permission')

        if not permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission level is required.'
            }, status=400)

        # Validate permission
        if permission not in dict(DocumentCollaborator.PERMISSION_CHOICES):
            return JsonResponse({
                'success': False,
                'error': 'Invalid permission level.'
            }, status=400)

        # Update the collaborator
        collaborator.permission = permission
        collaborator.save()

        return JsonResponse({
            'success': True,
            'collaborator': {
                'id': collaborator.id,
                'permission': collaborator.permission,
                'permission_display': collaborator.get_permission_display()
            }
        })

    except Exception as e:
        logger.error(f"Error updating collaborator permission: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Document Template Views

class CreateDocumentTemplateView(LoginRequiredMixin, EmployeeRequiredMixin, CreateView):
    """View to create a new document template"""
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = 'document_editor/template_form.html'
    success_url = reverse_lazy('document_editor:template_list')

    def form_valid(self, form):
        """Process the form if valid"""
        form.instance.created_by = self.request.user.employee_profile

        # Create initial empty Slate.js document structure if not provided
        if not form.instance.content:
            form.instance.content = {
                "children": [
                    {
                        "children": [
                            {
                                "text": ""
                            }
                        ],
                        "type": "paragraph"
                    }
                ]
            }

        response = super().form_valid(form)
        messages.success(self.request, f"Template '{form.instance.name}' created successfully.")
        return response


class UpdateDocumentTemplateView(LoginRequiredMixin, EmployeeRequiredMixin, UpdateView):
    """View to update a document template"""
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = 'document_editor/template_form.html'
    success_url = reverse_lazy('document_editor:template_list')

    def get_queryset(self):
        """Ensure user has permission to edit the template"""
        employee = self.request.user.employee_profile
        return DocumentTemplate.objects.filter(
            Q(created_by=employee) |
            Q(is_public=True, created_by__isnull=True)  # Allow editing orphaned public templates
        )

    def form_valid(self, form):
        """Process the form if valid"""
        response = super().form_valid(form)
        messages.success(self.request, f"Template '{form.instance.name}' updated successfully.")
        return response


class DeleteDocumentTemplateView(LoginRequiredMixin, EmployeeRequiredMixin, DeleteView):
    """View to delete a document template"""
    model = DocumentTemplate
    template_name = 'document_editor/template_confirm_delete.html'
    success_url = reverse_lazy('document_editor:template_list')

    def get_queryset(self):
        """Ensure user has permission to delete the template"""
        employee = self.request.user.employee_profile
        return DocumentTemplate.objects.filter(created_by=employee)

    def delete(self, request, *args, **kwargs):
        template = self.get_object()
        messages.success(request, f"Template '{template.name}' deleted successfully.")
        return super().delete(request, *args, **kwargs)


@login_required
def save_as_template(request, pk):
    """Save an existing document as a template"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check permissions
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee,
                    permission__in=['edit', 'manage']
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to create a template from this document.'
                }, status=403)

        # Get the template data
        if request.method == 'POST':
            data = json.loads(request.body)
            name = data.get('name')
            description = data.get('description', '')
            category = data.get('category')
            is_public = data.get('is_public', True)

            if not name:
                return JsonResponse({
                    'success': False,
                    'error': 'Template name is required.'
                }, status=400)

            if not category or category not in dict(DocumentTemplate.TEMPLATE_CATEGORIES):
                return JsonResponse({
                    'success': False,
                    'error': 'Valid template category is required.'
                }, status=400)

            # Create the template
            template = DocumentTemplate.objects.create(
                name=name,
                description=description,
                content=document.content,
                category=category,
                created_by=employee,
                is_public=is_public
            )

            return JsonResponse({
                'success': True,
                'template': {
                    'id': template.id,
                    'name': template.name,
                    'category': template.category,
                    'category_display': template.get_category_display()
                }
            })

        # If GET request, return the form
        return render(request, 'document_editor/save_as_template.html', {
            'document': document,
            'categories': DocumentTemplate.TEMPLATE_CATEGORIES
        })

    except Exception as e:
        logger.error(f"Error saving document as template: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        messages.error(request, f"Error saving document as template: {str(e)}")
        return redirect('document_editor:edit_document', pk=pk)


@login_required
@require_POST
def update_document_status(request, pk):
    """AJAX endpoint to update document status"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check permissions
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee,
                    permission__in=['edit', 'manage']
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to update this document status.'
                }, status=403)

        # Get the new status
        data = json.loads(request.body)
        status = data.get('status')

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required.'
            }, status=400)

        # Validate status
        if status not in dict(Document.STATUS_CHOICES):
            return JsonResponse({
                'success': False,
                'error': 'Invalid status.'
            }, status=400)

        # Update the document
        document.status = status
        document.save()

        return JsonResponse({
            'success': True,
            'status': document.status,
            'status_display': document.get_status_display()
        })

    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def export_document(request, pk, format='html'):
    """Export a document in various formats (HTML, PDF, etc.)"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check permissions
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to export this document.'
                }, status=403)

        # Prepare for export
        if format == 'html':
            # Convert Slate.js content to HTML
            # This is a simplified example - you'll need a more robust conversion
            try:
                html_content = '<div class="document-content">'

                # Simple conversion of Slate.js nodes to HTML
                for node in document.content.get('children', []):
                    node_type = node.get('type', 'paragraph')

                    if node_type == 'paragraph':
                        html_content += '<p>'
                        for child in node.get('children', []):
                            text = child.get('text', '')
                            if child.get('bold'):
                                text = f'<strong>{text}</strong>'
                            if child.get('italic'):
                                text = f'<em>{text}</em>'
                            if child.get('underline'):
                                text = f'<u>{text}</u>'
                            html_content += text
                        html_content += '</p>'
                    elif node_type == 'heading-one':
                        html_content += '<h1>'
                        for child in node.get('children', []):
                            html_content += child.get('text', '')
                        html_content += '</h1>'
                    elif node_type == 'heading-two':
                        html_content += '<h2>'
                        for child in node.get('children', []):
                            html_content += child.get('text', '')
                        html_content += '</h2>'
                    elif node_type == 'block-quote':
                        html_content += '<blockquote>'
                        for child in node.get('children', []):
                            html_content += child.get('text', '')
                        html_content += '</blockquote>'
                    elif node_type == 'bulleted-list':
                        html_content += '<ul>'
                        for list_item in node.get('children', []):
                            html_content += '<li>'
                            for child in list_item.get('children', []):
                                html_content += child.get('text', '')
                            html_content += '</li>'
                        html_content += '</ul>'
                    elif node_type == 'numbered-list':
                        html_content += '<ol>'
                        for list_item in node.get('children', []):
                            html_content += '<li>'
                            for child in list_item.get('children', []):
                                html_content += child.get('text', '')
                            html_content += '</li>'
                        html_content += '</ol>'

                html_content += '</div>'

                # Create a complete HTML document
                full_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>{document.title}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        h1 {{ color: #333; }}
                        .document-info {{ color: #666; margin-bottom: 20px; }}
                        .document-content {{ line-height: 1.6; }}
                    </style>
                </head>
                <body>
                    <h1>{document.title}</h1>
                    <div class="document-info">
                        <p>Author: {document.author.get_full_name()}</p>
                        <p>Created: {document.created_at.strftime('%Y-%m-%d')}</p>
                        <p>Last Updated: {document.updated_at.strftime('%Y-%m-%d')}</p>
                    </div>
                    {html_content}
                </body>
                </html>
                """

                # Create the response
                response = HttpResponse(full_html, content_type='text/html')
                response['Content-Disposition'] = f'attachment; filename="{document.title}.html"'
                return response

            except Exception as e:
                logger.error(f"Error converting document to HTML: {str(e)}")
                messages.error(request, f"Error exporting document: {str(e)}")
                return redirect('document_editor:edit_document', pk=pk)

        elif format == 'pdf':
            # In a production application, you would use a library like WeasyPrint
            # to convert HTML to PDF
            messages.error(request, "PDF export not yet implemented")
            return redirect('document_editor:edit_document', pk=pk)

        else:
            messages.error(request, f"Unsupported export format: {format}")
            return redirect('document_editor:edit_document', pk=pk)

    except Exception as e:
        logger.error(f"Error exporting document: {str(e)}")
        messages.error(request, f"Error exporting document: {str(e)}")
        return redirect('document_editor:edit_document', pk=pk)


@login_required
@require_http_methods(["GET"])
def get_document_content(request, pk):
    """AJAX endpoint to get document content"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=pk)
        employee = request.user.employee_profile

        # Check permissions
        if document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to view this document.'
                }, status=403)

        # Return the document content
        return JsonResponse({
            'success': True,
            'content': document.content,
            'version': document.version if hasattr(document, 'version') else 1,
            'updated_at': document.updated_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Error getting document content: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def add_document_comment(request, document_id):
    """AJAX endpoint to add a comment to a document"""
    try:
        # Get the document
        document = get_object_or_404(Document, pk=document_id)
        employee = request.user.employee_profile

        # Debug logging
        print(f"Adding comment to document {document_id}")
        print(f"Current user: {request.user.username}, employee ID: {employee.id if employee else 'None'}")
        print(f"Document author ID: {document.author.id if document.author else 'None'}")

        is_author = document.author == employee
        print(f"Is user the author? {is_author}")

        # Check permissions
        if not is_author:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
                print(f"Found collaborator record, permission: {collaborator.permission}")

                if collaborator.permission not in ['comment', 'edit', 'manage']:
                    print(f"Permission denied: {collaborator.permission} not in ['comment', 'edit', 'manage']")
                    return JsonResponse({
                        'success': False,
                        'error': f"Permission denied: You have '{collaborator.permission}' permission but need 'comment', 'edit', or 'manage'"
                    }, status=403)
            except DocumentCollaborator.DoesNotExist:
                print("No collaborator record found")
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to comment on this document - no collaborator record found.'
                }, status=403)

        # Parse the form data
        try:
            # First try to get from POST data (for FormData submissions)
            content = request.POST.get('content')
            parent_id = request.POST.get('parent_id')
            selection_start = request.POST.get('selection_start')
            selection_end = request.POST.get('selection_end')
            selected_text = request.POST.get('selected_text', '')

            # If content is not in POST, try JSON body
            if not content:
                data = json.loads(request.body)
                content = data.get('content')
                parent_id = data.get('parent_id')
                selection_start = data.get('selection_start')
                selection_end = data.get('selection_end')
                selected_text = data.get('selected_text', '')

            # Log what we received
            print(f"Received comment content: {content[:50]}...")
            print(f"Parent ID: {parent_id}")
            print(f"Has selection data: {bool(selection_start)}")
        except json.JSONDecodeError:
            # If both approaches fail, log the error
            print(f"Could not parse request body: {request.body[:100]}")
            print(f"POST data: {dict(request.POST)}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid request format.'
            }, status=400)

        if not content:
            return JsonResponse({
                'success': False,
                'error': 'Comment content is required.'
            }, status=400)

        # Process selection data if it's a string (from FormData)
        if selection_start and isinstance(selection_start, str):
            try:
                selection_start = json.loads(selection_start)
            except json.JSONDecodeError:
                print(f"Could not parse selection_start: {selection_start}")
                selection_start = None

        if selection_end and isinstance(selection_end, str):
            try:
                selection_end = json.loads(selection_end)
            except json.JSONDecodeError:
                print(f"Could not parse selection_end: {selection_end}")
                selection_end = None

        # Create the comment
        comment = DocumentComment(
            document=document,
            author=employee,
            content=content,
            selection_start=selection_start,
            selection_end=selection_end,
            selected_text=selected_text
        )

        # Add parent comment if replying
        if parent_id:
            try:
                parent_comment = get_object_or_404(DocumentComment, pk=parent_id)
                comment.parent_comment = parent_comment
            except:
                print(f"Could not find parent comment with ID: {parent_id}")
                # Continue without parent if not found

        comment.save()
        print(f"Comment saved with ID: {comment.id}")

        # Prepare author data safely
        author_data = {
            'id': employee.id,
            'name': employee.get_full_name() if hasattr(employee, 'get_full_name') else str(employee)
        }

        return JsonResponse({
            'success': True,
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'author': author_data,
                'created_at': comment.created_at.isoformat(),
                'is_resolved': comment.is_resolved,
                'parent_id': parent_id,
                'selection_start': selection_start,
                'selection_end': selection_end,
                'selected_text': selected_text
            }
        })

    except Exception as e:
        # Log the full exception with traceback
        import traceback
        print(f"Error adding comment: {str(e)}")
        print(traceback.format_exc())

        # Return a more detailed error message
        return JsonResponse({
            'success': False,
            'error': f"Server error: {str(e)}"
        }, status=500)


@login_required
@require_POST
def resolve_document_comment(request, comment_id):
    """AJAX endpoint to resolve a document comment"""
    try:
        # Get the comment
        comment = get_object_or_404(DocumentComment, pk=comment_id)
        employee = request.user.employee_profile

        # Check permissions (author of comment or document, or manager)
        if comment.author != employee and comment.document.author != employee:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=comment.document,
                    employee=employee,
                    permission__in=['edit', 'manage']
                )
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to resolve this comment.'
                }, status=403)

        # Resolve the comment
        comment.resolve(employee)

        return JsonResponse({
            'success': True,
            'comment_id': comment.id,
            'resolved_by': employee.get_full_name(),
            'resolved_at': comment.resolved_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Error resolving comment: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class DocumentCreateView(LoginRequiredMixin, EmployeeRequiredMixin, CreateView):
    """View to create a new document"""
    model = Document
    form_class = DocumentForm
    template_name = 'document_editor/document_form.html'

    def get_initial(self):
        """Set initial values for the form"""
        initial = super().get_initial()

        # Set default document type if provided in query params
        doc_type = self.request.GET.get('type')
        if doc_type and doc_type in dict(Document.DOCUMENT_TYPES):
            initial['document_type'] = doc_type

        # Set customer if provided in query params
        customer_id = self.request.GET.get('customer')
        if customer_id:
            try:
                customer = Customer.objects.get(id=customer_id)
                initial['customer'] = customer
            except Customer.DoesNotExist:
                pass

        # Set template status if creating template
        is_template = self.request.GET.get('template') == 'true'
        if is_template:
            initial['is_template'] = True

        return initial

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        context['is_new'] = True
        context['title'] = 'Create New Document'

        # Check if creating from template
        template_id = self.request.GET.get('from_template')
        if template_id:
            try:
                template = DocumentTemplate.objects.get(id=template_id)
                context['from_template'] = template
            except DocumentTemplate.DoesNotExist:
                pass

        return context

    def form_valid(self, form):
        """Process the form if valid"""
        # Set the author to the current user
        form.instance.author = self.request.user.employee_profile

        # If creating from template, use template content
        template_id = self.request.GET.get('from_template')
        if template_id:
            try:
                template = DocumentTemplate.objects.get(id=template_id)
                form.instance.content = template.content
            except DocumentTemplate.DoesNotExist:
                # Create empty document content if no template
                form.instance.content = {
                    "children": [
                        {
                            "type": "paragraph",
                            "children": [
                                {
                                    "text": ""
                                }
                            ]
                        }
                    ]
                }
        else:
            # Create empty document content if not from template
            form.instance.content = {
                "children": [
                    {
                        "type": "paragraph",
                        "children": [
                            {
                                "text": ""
                            }
                        ]
                    }
                ]
            }

        # Extract plain text from content for search
        form.instance.plain_text = ""  # Will be updated by save method

        # Set version and latest version flags
        form.instance.version = 1
        form.instance.is_latest_version = True

        response = super().form_valid(form)
        messages.success(self.request, f"Document '{form.instance.title}' created successfully.")
        return response

    def get_success_url(self):
        """Redirect to document editor after creation"""
        return reverse('document_editor:edit_document', kwargs={'pk': self.object.pk})


@login_required
@require_POST
def debug_save_document(request, pk):
    """Debug view that logs everything and helps identify the issue."""
    try:
        # Log request information
        print(f"DEBUG: Received request for document {pk}")
        print(f"DEBUG: POST data keys: {list(request.POST.keys())}")

        # Get the document
        from .models import Document
        document = Document.objects.get(id=pk)
        print(f"DEBUG: Found document: {document.title}")

        # Try to extract content
        content_str = request.POST.get('content', '')
        print(f"DEBUG: Content length: {len(content_str)}")
        print(f"DEBUG: Content preview: {content_str[:100]}")

        # Try parsing JSON
        try:
            content = json.loads(content_str)
            print(f"DEBUG: Successfully parsed JSON")
            print(f"DEBUG: Content type: {type(content)}")
            print(f"DEBUG: Content has children: {'children' in content}")

            # Try to extract plain text
            if isinstance(content, dict) and 'children' in content:
                text_parts = []

                def extract_text(node):
                    if isinstance(node, dict):
                        if 'text' in node:
                            text_parts.append(node['text'])
                        elif 'children' in node and isinstance(node['children'], list):
                            for child in node['children']:
                                extract_text(child)

                for node in content['children']:
                    extract_text(node)

                plain_text = ' '.join(text_parts)
                print(f"DEBUG: Extracted plain text ({len(plain_text)} chars): {plain_text[:100]}")

                # Update document for testing
                document.content = content
                document.plain_text = plain_text
                document.save()
                print("DEBUG: Document updated with new content and plain_text")

        except Exception as e:
            print(f"DEBUG: JSON parsing or text extraction error: {str(e)}")
            print(traceback.format_exc())

        # Try accessing user
        try:
            print(f"DEBUG: User: {request.user.username}")
            if hasattr(request.user, 'employee_profile'):
                print(f"DEBUG: User has employee profile")
                employee = request.user.employee_profile
                print(f"DEBUG: Employee name: {getattr(employee, 'get_full_name', lambda: 'N/A')()}")
            else:
                print(f"DEBUG: User has no employee profile")
        except Exception as e:
            print(f"DEBUG: Error accessing user data: {str(e)}")

        # Return success response for testing
        return JsonResponse({
            'success': True,
            'message': 'Debug complete'
        })

    except Exception as e:
        print(f"DEBUG CRITICAL ERROR: {str(e)}")
        print(traceback.format_exc())
        # Return the error details to the client for debugging
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Template Variable Views
class TemplateVariableListView(LoginRequiredMixin, ListView):
    """View for listing template variables"""
    model = DocumentTemplateVariable
    template_name = 'document_editor/template_variable_list.html'
    context_object_name = 'variables'

    def get_queryset(self):
        template_id = self.kwargs.get('template_id')
        if not template_id:
            raise Http404("Template not found")

        self.template = get_object_or_404(DocumentTemplate, pk=template_id)
        return DocumentTemplateVariable.objects.filter(template=self.template)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template'] = self.template
        return context


class TemplateVariableCreateView(LoginRequiredMixin, CreateView):
    """View for creating a new template variable"""
    model = DocumentTemplateVariable
    form_class = DocumentTemplateVariableForm
    template_name = 'document_editor/template_variable_form.html'

    def get_template(self):
        template_id = self.kwargs.get('template_id')
        return get_object_or_404(DocumentTemplate, pk=template_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['template'] = self.get_template()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template'] = self.get_template()
        context['title'] = 'Add Variable'
        return context

    def get_success_url(self):
        template = self.get_template()
        return reverse('document_editor:template_variable_list', kwargs={'template_id': template.id})

    def form_valid(self, form):
        messages.success(self.request, 'Variable added successfully.')
        return super().form_valid(form)


class TemplateVariableUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating a template variable"""
    model = DocumentTemplateVariable
    form_class = DocumentTemplateVariableForm
    template_name = 'document_editor/template_variable_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template'] = self.object.template
        context['title'] = 'Edit Variable'
        return context

    def get_success_url(self):
        return reverse('document_editor:template_variable_list',
                      kwargs={'template_id': self.object.template.id})

    def form_valid(self, form):
        messages.success(self.request, 'Variable updated successfully.')
        return super().form_valid(form)


class TemplateVariableDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting a template variable"""
    model = DocumentTemplateVariable
    template_name = 'document_editor/template_variable_confirm_delete.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template'] = self.object.template
        return context

    def get_success_url(self):
        return reverse('document_editor:template_variable_list',
                      kwargs={'template_id': self.object.template.id})

    def delete(self, request, *args, **kwargs):
        template_id = self.get_object().template.id
        messages.success(request, 'Variable deleted successfully.')
        return super().delete(request, *args, **kwargs)


# Template with Variables Views
class DocumentTemplateDetailView(LoginRequiredMixin, DetailView):
    """Enhanced view for document template details including variables"""
    model = DocumentTemplate
    template_name = 'document_editor/template_detail.html'
    context_object_name = 'template'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['variables'] = self.object.variables.all()
        return context


class ApplyTemplateView(LoginRequiredMixin, FormView):
    """View for applying a template with variables to create a document"""
    form_class = ApplyTemplateForm
    template_name = 'document_editor/apply_template_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        template_id = self.kwargs.get('template_id')
        if template_id:
            kwargs['template_id'] = template_id
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template_id = self.kwargs.get('template_id')
        if template_id:
            template = get_object_or_404(DocumentTemplate, pk=template_id)
            context['template'] = template
            context['title'] = f'Create Document from {template.name}'
        else:
            context['title'] = 'Create Document from Template'
        return context

    def form_valid(self, form):
        with transaction.atomic():
            template = form.cleaned_data['template']

            # Create new document
            document = Document(
                title=form.cleaned_data['title'],
                document_type=form.cleaned_data['document_type'],
                author=self.request.user.employee_profile,
                customer=form.cleaned_data.get('customer'),
                content=template.content,  # Start with template content
                status='draft',
                is_template=False,
                version=1,
                is_latest_version=True
            )

            # Process template variables
            variable_values = form.get_variable_values()
            if template.content and variable_values:
                document.content = process_template_variables(document, variable_values)

            document.save()

            # Extract plain text for search
            document.plain_text = document.extract_plain_text()
            document.save(update_fields=['plain_text'])

            messages.success(self.request, f'Document "{document.title}" created successfully from template.')
            return redirect('document_editor:edit_document', pk=document.pk)

        return super().form_valid(form)


# Document Approval Workflow Views
class DocumentApprovalWorkflowCreateView(LoginRequiredMixin, CreateView):
    """View for creating a document approval workflow"""
    model = DocumentApprovalWorkflow
    form_class = DocumentApprovalWorkflowForm
    template_name = 'document_editor/approval_workflow_form.html'

    def get_document(self):
        document_id = self.kwargs.get('document_id')
        return get_object_or_404(Document, pk=document_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['document'] = self.get_document()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_document()
        context['document'] = document
        context['title'] = f'Create Approval Workflow for "{document.title}"'
        return context

    def form_valid(self, form):
        with transaction.atomic():
            workflow = form.save()
            messages.success(self.request, 'Approval workflow created successfully. Add approval steps to continue.')
            return redirect('document_editor:approval_step_create', workflow_id=workflow.id)


class DocumentApprovalStepCreateView(LoginRequiredMixin, CreateView):
    """View for adding steps to an approval workflow"""
    model = DocumentApprovalStep
    form_class = DocumentApprovalStepForm
    template_name = 'document_editor/approval_step_form.html'

    def get_workflow(self):
        workflow_id = self.kwargs.get('workflow_id')
        return get_object_or_404(DocumentApprovalWorkflow, pk=workflow_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workflow'] = self.get_workflow()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workflow = self.get_workflow()
        context['workflow'] = workflow
        context['document'] = workflow.document
        context['existing_steps'] = workflow.steps.all().order_by('order')
        context['title'] = 'Add Approval Step'
        return context

    def form_valid(self, form):
        step = form.save()
        workflow = self.get_workflow()

        # Reorder steps if necessary
        if step.order <= workflow.steps.count():
            # Shift higher steps up
            with transaction.atomic():
                workflow.steps.filter(
                    order__gte=step.order
                ).exclude(
                    id=step.id
                ).update(
                    order=models.F('order') + 1
                )

        messages.success(self.request, 'Approval step added successfully.')

        # Redirect based on "add another" parameter
        if 'add_another' in self.request.POST:
            return redirect('document_editor:approval_step_create', workflow_id=workflow.id)

        return redirect('document_editor:approval_workflow_detail', pk=workflow.id)


class DocumentApprovalWorkflowDetailView(LoginRequiredMixin, DetailView):
    """View for reviewing the approval workflow details"""
    model = DocumentApprovalWorkflow
    template_name = 'document_editor/approval_workflow_detail.html'
    context_object_name = 'workflow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['document'] = self.object.document
        context['steps'] = self.object.steps.all().order_by('order')
        context['requests'] = self.object.requests.all().order_by('-request_date')
        return context


class DocumentApprovalStepUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating an approval step"""
    model = DocumentApprovalStep
    form_class = DocumentApprovalStepForm
    template_name = 'document_editor/approval_step_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['workflow'] = self.object.workflow
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow'] = self.object.workflow
        context['document'] = self.object.workflow.document
        context['title'] = 'Edit Approval Step'
        return context

    def form_valid(self, form):
        old_order = self.object.order
        new_order = form.cleaned_data['order']
        step = form.save(commit=False)

        # Handle order changes
        if old_order != new_order:
            with transaction.atomic():
                if new_order > old_order:
                    # Moving down - shift steps in between up
                    self.object.workflow.steps.filter(
                        order__gt=old_order,
                        order__lte=new_order
                    ).update(
                        order=models.F('order') - 1
                    )
                else:
                    # Moving up - shift steps in between down
                    self.object.workflow.steps.filter(
                        order__lt=old_order,
                        order__gte=new_order
                    ).update(
                        order=models.F('order') + 1
                    )

        step.save()
        messages.success(self.request, 'Approval step updated successfully.')
        return redirect('document_editor:approval_workflow_detail', pk=self.object.workflow.id)


class DocumentApprovalStepDeleteView(LoginRequiredMixin, DeleteView):
    """View for deleting an approval step"""
    model = DocumentApprovalStep
    template_name = 'document_editor/approval_step_confirm_delete.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow'] = self.object.workflow
        context['document'] = self.object.workflow.document
        return context

    def delete(self, request, *args, **kwargs):
        workflow_id = self.get_object().workflow.id
        with transaction.atomic():
            # Get the order before deleting
            step = self.get_object()
            order = step.order

            # Delete the step
            response = super().delete(request, *args, **kwargs)

            # Reorder remaining steps
            DocumentApprovalStep.objects.filter(
                workflow_id=workflow_id,
                order__gt=order
            ).update(
                order=models.F('order') - 1
            )

            messages.success(request, 'Approval step deleted successfully.')
            return response

    def get_success_url(self):
        return reverse('document_editor:approval_workflow_detail',
                      kwargs={'pk': self.object.workflow.id})


class StartApprovalWorkflowView(LoginRequiredMixin, FormView):
    """View to start the approval workflow"""
    template_name = 'document_editor/start_approval_workflow.html'
    form_class = forms.Form  # Empty form, just for confirmation

    def get_workflow(self):
        workflow_id = self.kwargs.get('workflow_id')
        workflow = get_object_or_404(DocumentApprovalWorkflow, pk=workflow_id)

        # Ensure user has permission (document author or admin)
        if workflow.document.author != self.request.user.employee_profile:
            raise PermissionDenied("You don't have permission to start this workflow")

        return workflow

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workflow = self.get_workflow()
        context['workflow'] = workflow
        context['document'] = workflow.document
        context['steps'] = workflow.steps.all().order_by('order')
        return context

    def form_valid(self, form):
        workflow = self.get_workflow()

        # Check if steps exist
        if workflow.steps.count() == 0:
            messages.error(self.request, 'Cannot start workflow without approval steps.')
            return redirect('document_editor:approval_workflow_detail', pk=workflow.id)

        # Start the workflow
        if workflow.start_workflow():
            # Update document status
            document = workflow.document
            document.status = 'review'
            document.save()

            messages.success(self.request, 'Approval workflow started successfully.')
            return redirect('document_editor:document_detail', pk=document.id)
        else:
            messages.error(self.request, 'Failed to start workflow.')
            return redirect('document_editor:approval_workflow_detail', pk=workflow.id)


class ApprovalRequestResponseView(LoginRequiredMixin, FormView):
    """View to respond to an approval request"""
    template_name = 'document_editor/approval_response_form.html'
    form_class = ApprovalResponseForm

    def get_approval_request(self):
        request_id = self.kwargs.get('request_id')
        approval_request = get_object_or_404(DocumentApprovalRequest, pk=request_id)

        # Ensure user is the assigned approver
        if approval_request.approver != self.request.user.employee_profile:
            raise PermissionDenied("You are not authorized to respond to this request")

        # Ensure request is still pending
        if approval_request.status != 'pending':
            messages.error(self.request, 'This approval request has already been processed.')
            return None

        return approval_request

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        approval_request = self.get_approval_request()

        if not approval_request:
            return context

        context['approval_request'] = approval_request
        context['document'] = approval_request.workflow.document
        context['workflow'] = approval_request.workflow
        return context

    def form_valid(self, form):
        approval_request = self.get_approval_request()

        if not approval_request:
            return redirect('document_editor:dashboard')

        response = form.cleaned_data['response']
        comments = form.cleaned_data['comments']
        workflow = approval_request.workflow

        if response == 'approve':
            # Approve the current step
            if workflow.approve_current_step(comments):
                messages.success(self.request, 'Document approved successfully.')
            else:
                messages.error(self.request, 'Error processing approval.')
        else:
            # Reject the document
            rejection_reason = form.cleaned_data['rejection_reason']
            if workflow.reject(rejection_reason):
                messages.success(self.request, 'Document has been rejected.')
            else:
                messages.error(self.request, 'Error processing rejection.')

        return redirect('document_editor:document_detail', pk=workflow.document.id)


@login_required
def preview_document_with_variables(request, template_id):
    """AJAX endpoint to preview a document with variables filled in"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        template = get_object_or_404(DocumentTemplate, pk=template_id)
        data = json.loads(request.body)
        variable_values = data.get('variables', {})

        # Process the template with variables
        preview_content = preview_with_variables(template, variable_values)

        return JsonResponse({
            'success': True,
            'content': preview_content
        })
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def cancel_approval_workflow(request, workflow_id):
    """View to cancel an approval workflow"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    workflow = get_object_or_404(DocumentApprovalWorkflow, pk=workflow_id)

    # Check permissions - only document author can cancel
    if workflow.document.author != request.user.employee_profile:
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to cancel this workflow'
        }, status=403)

    try:
        workflow.cancel()

        # Update document status
        document = workflow.document
        document.status = 'draft'
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Approval workflow cancelled successfully'
        })
    except Exception as e:
        logger.error(f"Error cancelling workflow: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class DocumentApprovalDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard view for document approvals"""
    template_name = 'document_editor/approval_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_profile

        # Get pending approval requests for this user
        context['pending_approvals'] = DocumentApprovalRequest.objects.filter(
            approver=employee,
            status='pending'
        ).select_related(
            'workflow__document',
            'step'
        ).order_by('request_date')

        # Get documents submitted for approval by this user
        context['submitted_documents'] = Document.objects.filter(
            author=employee,
            approval_workflow__isnull=False
        ).exclude(
            approval_workflow__status__in=['draft', 'canceled']
        ).select_related(
            'approval_workflow'
        ).order_by('-approval_workflow__updated_at')

        # Get recently approved/rejected documents for this user
        context['completed_approvals'] = DocumentApprovalRequest.objects.filter(
            approver=employee,
            status__in=['approved', 'rejected']
        ).select_related(
            'workflow__document'
        ).order_by('-response_date')[:10]

        return context
