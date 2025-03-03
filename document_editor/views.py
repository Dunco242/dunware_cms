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
from django.db import transaction
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.models import Employee, Customer
from core.mixins import EmployeeRequiredMixin

from .models import (
    Document, DocumentCollaborator, DocumentComment, DocumentTemplate, DocumentVersion
)
from .forms import (
    DocumentForm, DocumentTemplateForm, DocumentCollaboratorForm, DocumentCommentForm
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
        if document.parent_document or document.versions.exists():
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
    model = Document
    template_name = 'document_editor/document_editor.html'
    context_object_name = 'document'

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_object()
        employee = self.request.user.employee_profile

        if document.author == employee:
            context['can_edit'] = True
            context['can_comment'] = True
        else:
            try:
                collaborator = DocumentCollaborator.objects.get(
                    document=document,
                    employee=employee
                )
                context['can_edit'] = collaborator.permission in ['edit', 'manage']
                context['can_comment'] = collaborator.permission in ['comment', 'edit', 'manage']
            except DocumentCollaborator.DoesNotExist:
                context['can_edit'] = False
                context['can_comment'] = False

        context['comments'] = DocumentComment.objects.filter(
            document=document
        ).order_by('created_at')

        context['document_content'] = json.dumps(
            document.content or
            {
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
            },
            separators=(',', ':')
        )

        return context


class DocumentEditorView(LoginRequiredMixin, EmployeeRequiredMixin, DetailView):
    model = Document
    template_name = 'document_editor/document_editor.html'
    context_object_name = 'document'

    def get_queryset(self):
        employee = self.request.user.employee_profile
        return Document.objects.filter(
            Q(author=employee) |
            Q(collaborators__employee=employee)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_object()
        employee = self.request.user.employee_profile

        # Explicitly set can_edit as a string 'True' or 'False'
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

        context['comments'] = DocumentComment.objects.filter(
            document=document
        ).order_by('created_at')

        context['document_content'] = json.dumps(
            document.content or
            {
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
            },
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

logger = logging.getLogger(__name__)

@login_required
@require_POST
def simple_save_document(request, pk):
    """Simplified document save view to isolate the issue."""
    try:
        # Get the document
        document = get_object_or_404(Document, id=pk)

        # Extract content from form data
        content_str = request.POST.get('content', '')

        # Just save the content as a string for now, no processing
        document.content = {
            "children": [
                {
                    "type": "paragraph",
                    "children": [
                        {
                            "text": "Updated content via simple save"
                        }
                    ]
                }
            ]
        }

        # Save the document
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Document saved with hardcoded content'
        })

    except Exception as e:
        # Return detailed error information
        import traceback
        error_details = {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        return JsonResponse(error_details, status=500)

# The WebSocket notification helper function (placed in channels.py)
def notify_document_saved(document, user):
    """
    Send a WebSocket notification to all users viewing the document
    that the document has been saved.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"document_{document.id}",
        {
            "type": "document_saved",
            "document_id": document.id,
            "user_id": user.id,
            "user_name": user.get_full_name() or user.username,
            "updated_at": document.updated_at.isoformat()
        }
    )

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
            'version': document.version,
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
def add_document_comment(request, pk):
    """AJAX endpoint to add a comment to a document"""
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
                if collaborator.permission not in ['comment', 'edit', 'manage']:
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to comment on this document.'
                    }, status=403)
            except DocumentCollaborator.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to comment on this document.'
                }, status=403)

        # Get the comment data
        data = json.loads(request.body)
        content = data.get('content')
        parent_id = data.get('parent_id')
        selection_start = data.get('selection_start')
        selection_end = data.get('selection_end')
        selected_text = data.get('selected_text', '')

        if not content:
            return JsonResponse({
                'success': False,
                'error': 'Comment content is required.'
            }, status=400)

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
            parent_comment = get_object_or_404(DocumentComment, pk=parent_id)
            comment.parent_comment = parent_comment

        comment.save()

        return JsonResponse({
            'success': True,
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'author': {
                    'id': comment.author.id,
                    'name': comment.author.get_full_name()
                },
                'created_at': comment.created_at.isoformat(),
                'is_resolved': comment.is_resolved,
                'parent_id': parent_id,
                'selection_start': selection_start,
                'selection_end': selection_end,
                'selected_text': selected_text
            }
        })

    except Exception as e:
        logger.error(f"Error adding comment: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
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
        except Exception as e:
            print(f"DEBUG: JSON parsing error: {str(e)}")

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
        # Return the error details to the client for debugging
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
