from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import pickle
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


def get_google_calendar_service(request):
    """
    Gets a Google Calendar service object for the current user.
    If the user hasn't authenticated, returns a URL to redirect to for auth.
    """
    # Define scopes and credentials file
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    credentials_file = settings.GOOGLE_CALENDAR_CREDENTIALS_FILE

    # Check if we have valid credentials for this user
    user_token_file = f'token_{request.user.id}.pickle'
    token_path = os.path.join(os.path.dirname(__file__), user_token_file)

    creds = None
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Need to authenticate - store the request path in session for redirect
            request.session['calendar_redirect'] = request.get_full_path()

            # Create OAuth flow
            flow = Flow.from_client_secrets_file(
                credentials_file,
                scopes=SCOPES,
                redirect_uri=request.build_absolute_uri('/calendar/google/callback/')
            )

            # Generate authorization URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )

            # Return the auth URL for redirect
            return auth_url

        # Save updated credentials
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    # Build and return the service
    service = build('calendar', 'v3', credentials=creds)
    return service
