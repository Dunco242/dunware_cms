# zoom_integration/utils.py

import jwt
import time
import requests
from datetime import datetime
from django.conf import settings

class ZoomAPI:
    def __init__(self):
        self.api_key = settings.ZOOM_API_KEY
        self.api_secret = settings.ZOOM_API_SECRET
        self.base_url = 'https://api.zoom.us/v2'

    def generate_token(self):
        """Generate JWT token for Zoom API"""
        token = jwt.encode(
            {
                'iss': self.api_key,
                'exp': time.time() + 5000
            },
            self.api_secret,
            algorithm='HS256'
        )
        return token

    def create_meeting(self, topic, start_time, duration, user_id="me"):
        """Create a Zoom meeting"""
        headers = {
            'Authorization': f'Bearer {self.generate_token()}',
            'Content-Type': 'application/json'
        }

        data = {
            'topic': topic,
            'type': 2,  # Scheduled meeting
            'start_time': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'duration': duration,
            'timezone': 'UTC',
            'settings': {
                'host_video': True,
                'participant_video': True,
                'join_before_host': True,
                'waiting_room': False,
                'auto_recording': 'none'
            }
        }

        response = requests.post(
            f'{self.base_url}/users/{user_id}/meetings',
            headers=headers,
            json=data
        )
        response.raise_for_status()
        return response.json()

    def update_meeting(self, meeting_id, topic, start_time, duration):
        """Update a Zoom meeting"""
        headers = {
            'Authorization': f'Bearer {self.generate_token()}',
            'Content-Type': 'application/json'
        }

        data = {
            'topic': topic,
            'start_time': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'duration': duration
        }

        response = requests.patch(
            f'{self.base_url}/meetings/{meeting_id}',
            headers=headers,
            json=data
        )
        response.raise_for_status()
        return response.json()

    def delete_meeting(self, meeting_id):
        """Delete a Zoom meeting"""
        headers = {
            'Authorization': f'Bearer {self.generate_token()}'
        }

        response = requests.delete(
            f'{self.base_url}/meetings/{meeting_id}',
            headers=headers
        )
        response.raise_for_status()
        return True

    def get_meeting(self, meeting_id):
        """Get Zoom meeting details"""
        headers = {
            'Authorization': f'Bearer {self.generate_token()}'
        }

        response = requests.get(
            f'{self.base_url}/meetings/{meeting_id}',
            headers=headers
        )
        response.raise_for_status()
        return response.json()
