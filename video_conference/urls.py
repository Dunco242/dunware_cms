# video_conference/urls.py
from django.urls import path
from . import views

app_name = 'video_meetings'

urlpatterns = [
    # Meeting creation and joining
    path('create/', views.create_video_meeting, name='create_video_meeting'),
    path('join/', views.join_meeting_form, name='join_meeting_form'),
    path('join/<uuid:meeting_id>/', views.join_meeting_room, name='join_meeting_room'),

    # Meeting management APIs
    path('link/<uuid:meeting_id>/', views.create_meeting_link, name='create_meeting_link'),
    path('end/<uuid:meeting_id>/', views.end_meeting, name='end_meeting'),
]
