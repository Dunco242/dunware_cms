# core/utils/zoom.py

import json
import time
import jwt
from datetime import datetime
from django.conf import settings
import requests

class ZoomAPI:
    def __init__(self):
        self.api_key = settings.ZOOM_API_KEY
        self.api_secret = settings.ZOOM_API_SECRET
        self.base_url = 'https://api.zoom.us/v2'

    def generate_jwt_token(self):
        token = jwt.encode(
            {
                'iss': self.api_key,
                'exp': time.time() + 5000
            },
            self.api_secret,
            algorithm='HS256'
        )
        return token

    def get_headers(self):
        return {
            'Authorization': f'Bearer {self.generate_jwt_token()}',
            'Content-Type': 'application/json'
        }

    def create_meeting(self, topic, start_time, duration, agenda=None):
        endpoint = f"{self.base_url}/users/me/meetings"

        meeting_data = {
            'topic': topic,
            'type': 2,  # Scheduled meeting
            'start_time': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'duration': duration,  # Duration in minutes
            'timezone': 'UTC',
            'settings': {
                'host_video': True,
                'participant_video': True,
                'join_before_host': True,
                'mute_upon_entry': True,
                'watermark': False,
                'audio': 'both',
                'auto_recording': 'none'
            }
        }

        if agenda:
            meeting_data['agenda'] = agenda

        response = requests.post(
            endpoint,
            headers=self.get_headers(),
            json=meeting_data
        )
        response.raise_for_status()
        return response.json()

    def update_meeting(self, meeting_id, topic, start_time, duration, agenda=None):
        endpoint = f"{self.base_url}/meetings/{meeting_id}"

        meeting_data = {
            'topic': topic,
            'start_time': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'duration': duration,
        }

        if agenda:
            meeting_data['agenda'] = agenda

        response = requests.patch(
            endpoint,
            headers=self.get_headers(),
            json=meeting_data
        )
        response.raise_for_status()
        return response.json()

    def delete_meeting(self, meeting_id):
        endpoint = f"{self.base_url}/meetings/{meeting_id}"

        response = requests.delete(
            endpoint,
            headers=self.get_headers()
        )
        response.raise_for_status()
        return True

    def get_meeting(self, meeting_id):
        endpoint = f"{self.base_url}/meetings/{meeting_id}"

        response = requests.get(
            endpoint,
            headers=self.get_headers()
        )
        response.raise_for_status()
        return response.json()

# Utility functions for the views
def create_zoom_meeting(meeting):
    zoom = ZoomAPI()
    duration = int((meeting.end_time - meeting.start_time).total_seconds() / 60)

    zoom_meeting = zoom.create_meeting(
        topic=meeting.title,
        start_time=meeting.start_time,
        duration=duration,
        agenda=meeting.description
    )

    return {
        'id': zoom_meeting['id'],
        'join_url': zoom_meeting['join_url'],
        'start_url': zoom_meeting['start_url'],
        'password': zoom_meeting.get('password', '')
    }

def update_zoom_meeting(meeting):
    zoom = ZoomAPI()
    duration = int((meeting.end_time - meeting.start_time).total_seconds() / 60)

    return zoom.update_meeting(
        meeting_id=meeting.zoom_meeting_id,
        topic=meeting.title,
        start_time=meeting.start_time,
        duration=duration,
        agenda=meeting.description
    )

def delete_zoom_meeting(meeting_id):
    zoom = ZoomAPI()
    return zoom.delete_meeting(meeting_id)
