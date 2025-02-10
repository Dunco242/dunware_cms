# middleware.py
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from .models import IPAccess, PrivacyPolicyAcceptance

class IPTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Execute the view and get the response
        response = self.get_response(request)

        # Now we can safely access request.user after auth middleware has run
        try:
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')

            # Create access record
            IPAccess.objects.create(
                ip_address=ip,
                user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                path=request.path,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                method=request.method,
                is_ajax=request.headers.get('x-requested-with') == 'XMLHttpRequest',
                is_secure=request.is_secure(),
            )
        except Exception as e:
            # Log the error but don't break the request
            # Consider using proper logging instead of print
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in IPTrackingMiddleware: {str(e)}")

        return response


class PrivacyPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Paths that don't require policy acceptance
            exempt_paths = [
                '/privacy-policy/',
                '/accept-privacy-policy/',
                '/logout/',
                '/admin/',
            ]

            # Check if current path is exempt
            if not any(request.path.startswith(path) for path in exempt_paths):
                # Check if user has accepted current policy
                current_version = "1.0.0"  # Consider making this configurable
                if not PrivacyPolicyAcceptance.objects.filter(
                    user=request.user,
                    policy_version=current_version
                ).exists():
                    messages.warning(
                        request,
                        'Please accept our Privacy Policy to continue.'
                    )
                    return redirect('privacy_policy')

        return self.get_response(request)
