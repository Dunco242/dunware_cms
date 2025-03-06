from django.urls import path
from . import views

urlpatterns = [
    path('join/<uuid:meeting_id>/', views.join_meeting_room, name='join_meeting_room'),
    path('link/<uuid:meeting_id>/', views.create_meeting_link, name='create_meeting_link'),
    path('end/<uuid:meeting_id>/', views.end_meeting, name='end_meeting'),
    path('create/', views.create_video_meeting, name='create_video_meeting'),
]
