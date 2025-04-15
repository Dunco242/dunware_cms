from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from core.views import DashboardView
from core import views  # Import your core views
from django.shortcuts import redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required

def anonymous_user_only(user):
    return not user.is_authenticated

urlpatterns = [
    path('admin/', admin.site.urls),
    # Change this line:
    path('', user_passes_test(anonymous_user_only, login_url='/dashboard/')(views.index), name='index'),
    path('dashboard/', login_required(DashboardView.as_view()), name='dashboard'),
    path('account/', include('allauth.urls')),
    path('', include('core.urls')),
    path('customer-projects/', include('customer_projects.urls', namespace="customer_projects")),
    path('documents/', include('document_editor.urls', namespace='document_editor')),
    path('video_meetings/', include('video_conference.urls', namespace='video_meetings')),
    path('onboarding/', include('onboarding.urls', namespace='onboarding')),
    path('route_management/', include('route_management.urls', namespace='route_management')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
