# video_conference/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
import random
import time
import re
import traceback

from core.models import Customer, Employee, Lead
from video_conference.models import VideoConference

def generate_agora_token(channel_name, uid):
   """
   Generate a token for Agora RTC
   This is a placeholder - you'd need to implement real token generation
   using the agora_token_builder library
   """
   try:
       from agora_token_builder import RtcTokenBuilder
       app_id = settings.AGORA_APP_ID
       app_certificate = getattr(settings, 'AGORA_APP_CERTIFICATE', None)
       expiration_time = 3600  # 1 hour token
       current_timestamp = int(time.time())
       expired_ts = current_timestamp + expiration_time

       # If certificate is available, use it for proper token generation
       if app_certificate:
           token = RtcTokenBuilder.buildTokenWithUid(
               app_id, app_certificate, channel_name, uid, 1, expired_ts
           )
       else:
           # For development without certificate
           token = f"dev_token_{channel_name}_{uid}_{current_timestamp}"
       return token
   except Exception as e:
       print(f"Error generating token: {str(e)}")
       # For development, return a dummy token
       return f"dummy_token_{channel_name}_{uid}"

def join_meeting_room(request, meeting_id):
   """Handle a user joining a meeting via a unique link"""
   # Get the conference
   conference = get_object_or_404(VideoConference, id=meeting_id)

   # Check if conference is active/valid
   if conference.is_expired():
       return render(request, 'video/meeting_ended.html', {'meeting': conference})

   # Check for passcode if required
   if conference.passcode and request.method == 'GET':
       return render(request, 'video/meeting_passcode.html', {'meeting': conference})

   if conference.passcode and request.method == 'POST':
       entered_passcode = request.POST.get('passcode', '')
       if entered_passcode != conference.passcode:
           return render(request, 'video/meeting_passcode.html', {
               'meeting': conference,
               'error': 'Invalid passcode. Please try again.'
           })

   # Generate a unique ID for the user
   uid = random.randint(1, 2**32 - 1)

   # Get user info
   is_host = False
   display_name = "Guest"
   customer_name = None

   if request.user.is_authenticated:
       try:
           employee = request.user.employee_profile
           display_name = employee.get_full_name() or request.user.username
       except Employee.DoesNotExist:
           display_name = request.user.get_full_name() or request.user.username

       is_host = (conference.host_user == request.user)
   else:
       # For unauthenticated users (guests)
       display_name = request.POST.get('display_name', f"Guest-{uid}")

   # Get customer name if stored in session
   customer_name = request.session.get('meeting_customer_name')

   # Format meeting date for display
   if conference.scheduled_for:
       meeting_date = conference.scheduled_for.strftime("%A, %B %d, %Y")
   else:
       meeting_date = timezone.now().strftime("%A, %B %d, %Y")

   # Generate Agora token
   token = generate_agora_token(conference.channel_name, uid)

   context = {
       'app_id': settings.AGORA_APP_ID,
       'channel_name': conference.channel_name,
       'token': token,
       'uid': uid,
       'display_name': display_name,
       'customer_name': customer_name,
       'is_host': is_host,
       'meeting': conference,
       'meeting_title': f"Meeting with {customer_name}" if customer_name else "Video Meeting",
       'meeting_date': meeting_date,
       'passcode': conference.passcode if is_host else None,
       'leave_url': request.build_absolute_uri('/') if not is_host else request.build_absolute_uri('/meetings/')
   }

   return render(request, 'video/meeting_room.html', context)

@login_required
def create_meeting_link(request, meeting_id):
   """Generate a shareable meeting link for a specific conference"""
   conference = get_object_or_404(VideoConference, id=meeting_id)

   # Check if user has permission
   if conference.host_user != request.user and not request.user.is_superuser:
       return JsonResponse({'error': 'You do not have permission to share this meeting'}, status=403)

   # Generate meeting URL
   meeting_url = request.build_absolute_uri(f'/meetings/join/{conference.id}/')

   return JsonResponse({
       'meeting_url': meeting_url,
       'passcode': conference.passcode
   })

@login_required
@require_POST
def end_meeting(request, meeting_id):
   """End a meeting for all participants"""
   conference = get_object_or_404(VideoConference, id=meeting_id)

   # Check if user has permission
   if conference.host_user != request.user and not request.user.is_superuser:
       return JsonResponse({'error': 'You do not have permission to end this meeting'}, status=403)

   # Update conference status
   conference.is_active = False
   conference.save()

   return JsonResponse({'success': True})

@login_required
def create_video_meeting(request):
   """
   View for creating a new video meeting
   """
   # Get list of customers for the dropdown
   customers = Customer.objects.filter(status='active')

   if request.method == 'POST':
       # Process form submission
       title = request.POST.get('title')
       customer_id = request.POST.get('customer')
       description = request.POST.get('description')
       duration = int(request.POST.get('duration', 30))

       if not title:
           return render(request, 'video/create_video_meeting.html', {
               'customers': customers,
               'error': 'Meeting title is required'
           })

       try:
           # Generate a unique channel name using the title
           channel_name = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
           channel_name = f"{channel_name}_{int(timezone.now().timestamp())}"

           # Create a new video conference
           conference = VideoConference.objects.create(
               channel_name=channel_name,
               host_user=request.user,
               scheduled_for=timezone.now(),  # Schedule for now (immediate meeting)
               is_active=True
           )

           # Store customer information in session if needed
           if customer_id:
               try:
                   customer = Customer.objects.get(id=customer_id)
                   request.session['meeting_customer_id'] = customer_id
                   request.session['meeting_customer_name'] = customer.company_name
               except Customer.DoesNotExist:
                   pass

           # Redirect to join the conference
           return redirect('video_meetings:join_meeting_room', meeting_id=conference.id)

       except Exception as e:
           # Handle any errors
           error_message = f"Error creating meeting: {str(e)}"
           print(error_message)
           print(traceback.format_exc())

           return render(request, 'video/create_video_meeting.html', {
               'customers': customers,
               'error': error_message
           })

   # Display the form
   return render(request, 'video/create_video_meeting.html', {
       'customers': customers
   })
