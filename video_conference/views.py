# video_meetings/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
import random
import time

from core.models import Meeting, Customer, Employee, Lead

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
    # Get the meeting
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Check if meeting is active/valid
    now = timezone.now()
    if meeting.status == 'cancelled':
        return render(request, 'video/meeting_cancelled.html', {'meeting': meeting})

    if now > meeting.end_time:
        return render(request, 'video/meeting_ended.html', {'meeting': meeting})

    # Check for passcode if required
    if hasattr(meeting, 'zoom_meeting_password') and meeting.zoom_meeting_password and request.method == 'GET':
        return render(request, 'video/meeting_passcode.html', {'meeting': meeting})

    if hasattr(meeting, 'zoom_meeting_password') and meeting.zoom_meeting_password and request.method == 'POST':
        entered_passcode = request.POST.get('passcode', '')
        if entered_passcode != meeting.zoom_meeting_password:
            return render(request, 'video/meeting_passcode.html', {
                'meeting': meeting,
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
            is_host = (meeting.organizer == employee)
        except Employee.DoesNotExist:
            display_name = request.user.get_full_name() or request.user.username
    else:
        # For unauthenticated users (guests)
        display_name = request.POST.get('display_name', f"Guest-{uid}")

    # Get customer name if applicable
    if meeting.customers.exists():
        customer = meeting.customers.first()
        customer_name = customer.company_name

    # Format meeting date for display
    meeting_date = meeting.start_time.strftime("%A, %B %d, %Y")

    # Generate Agora token
    channel_name = f"meeting_{meeting.id}"
    token = generate_agora_token(channel_name, uid)

    context = {
        'app_id': settings.AGORA_APP_ID,
        'channel_name': channel_name,
        'token': token,
        'uid': uid,
        'display_name': display_name,
        'customer_name': customer_name,
        'is_host': is_host,
        'meeting': meeting,
        'meeting_title': meeting.title,
        'meeting_date': meeting_date,
        'passcode': meeting.zoom_meeting_password if is_host else None,
        'leave_url': request.build_absolute_uri('/') if not is_host else request.build_absolute_uri('/meetings/')
    }

    # Mark meeting as in_progress if it wasn't already
    if meeting.status == 'scheduled':
        meeting.status = 'in_progress'
        meeting.save(update_fields=['status'])

    return render(request, 'video/meeting_room.html', context)

@login_required
def create_meeting_link(request, meeting_id):
    """Generate a shareable meeting link for a specific meeting"""
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Check if user has permission
    if meeting.organizer.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'You do not have permission to share this meeting'}, status=403)

    # Generate meeting URL
    meeting_url = request.build_absolute_uri(f'/meetings/join/{meeting.id}/')

    return JsonResponse({
        'meeting_url': meeting_url,
        'passcode': meeting.zoom_meeting_password
    })

@login_required
@require_POST
def end_meeting(request, meeting_id):
    """End a meeting for all participants"""
    meeting = get_object_or_404(Meeting, id=meeting_id)

    # Check if user has permission
    if meeting.organizer.user != request.user and not request.user.is_superuser:
        return JsonResponse({'error': 'You do not have permission to end this meeting'}, status=403)

    # Update meeting status
    meeting.status = 'completed'
    meeting.save(update_fields=['status'])

    return JsonResponse({'success': True})

@login_required
def create_video_meeting(request):
    """
    View for creating a new video meeting
    """
    from core.models import Customer

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
            # Get the employee profile
            employee = request.user.employee_profile

            # Create a new meeting with a small time offset (future)
            now = timezone.now() + timezone.timedelta(seconds=5)
            end_time = now + timezone.timedelta(minutes=duration)

            meeting = Meeting(
                title=title,
                description=description,
                start_time=now,
                end_time=end_time,
                meeting_type='zoom',  # Using 'zoom' as type since we're using 'zoom_meeting_id' field
                status='scheduled',
                organizer=employee
            )

            # Save without validation
            meeting.save(validate=False)

            # Add customer if selected
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id)
                    meeting.customers.add(customer)
                except Customer.DoesNotExist:
                    pass

            # Generate unique meeting ID for Agora
            meeting.zoom_meeting_id = f"agora_{meeting.id}"
            meeting.save(update_fields=['zoom_meeting_id'])

            # Redirect to join the meeting
            return redirect('video_meetings:join_meeting_room', meeting_id=meeting.id)

        except Exception as e:
            # Handle any errors
            return render(request, 'video/create_video_meeting.html', {
                'customers': customers,
                'error': f'Error creating meeting: {str(e)}'
            })

    # Display the form
    return render(request, 'video/create_video_meeting.html', {
        'customers': customers
    })
