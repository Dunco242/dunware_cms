# dunware_crm/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from core.views import DashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', login_required(DashboardView.as_view()), name='dashboard'),
    path('account/', include('allauth.urls')),
    path('', include('core.urls')),
    path('customer-projects/', include('customer_projects.urls', namespace="customer_projects")),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
