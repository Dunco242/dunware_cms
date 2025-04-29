# urls.py
from django.urls import path
from . import views

app_name = 'downloads'

urlpatterns = [
    path('download/', views.DownloadView.as_view(), name='download'),
]
