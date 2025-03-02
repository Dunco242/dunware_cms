from django.urls import path
from . import views

app_name = 'document_editor'

urlpatterns = [
    # Document list views
    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('templates/', views.DocumentTemplateListView.as_view(), name='template_list'),

    # Document CRUD views
    path('documents/create/', views.CreateDocumentView.as_view(), name='create_document'),
    path('documents/<int:pk>/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('documents/<int:pk>/edit/', views.DocumentEditorView.as_view(), name='edit_document'),
    path('documents/<int:pk>/update/', views.UpdateDocumentView.as_view(), name='update_document'),
    path('documents/<int:pk>/delete/', views.DeleteDocumentView.as_view(), name='delete_document'),

    # Document template CRUD views
    path('templates/create/', views.CreateDocumentTemplateView.as_view(), name='create_template'),
    path('templates/<int:pk>/update/', views.UpdateDocumentTemplateView.as_view(), name='update_template'),
    path('templates/<int:pk>/delete/', views.DeleteDocumentTemplateView.as_view(), name='delete_template'),

    # Document content AJAX endpoints
    path('documents/<int:pk>/save-content/', views.save_document_content, name='save_document_content'),
    path('documents/<int:pk>/get-content/', views.get_document_content, name='get_document_content'),

    # Document status endpoints
    path('documents/<int:pk>/update-status/', views.update_document_status, name='update_document_status'),

    # Document export endpoints
    path('documents/<int:pk>/export/<str:format>/', views.export_document, name='export_document'),

    # Document template conversion
    path('documents/<int:pk>/save-as-template/', views.save_as_template, name='save_as_template'),

    # Collaborator management
    path('documents/<int:pk>/add-collaborator/', views.add_collaborator, name='add_collaborator'),
    path('documents/<int:pk>/remove-collaborator/<int:collaborator_id>/',
         views.remove_collaborator, name='remove_collaborator'),
    path('documents/<int:pk>/update-collaborator/<int:collaborator_id>/',
         views.update_collaborator_permission, name='update_collaborator_permission'),

    # Comments management
    path('documents/<int:pk>/add-comment/', views.add_document_comment, name='add_document_comment'),
    path('comments/<int:comment_id>/resolve/', views.resolve_document_comment, name='resolve_document_comment'),
]
