from django.views.generic import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from .models import VerificationCode
import datetime


class DownloadView(View):
    template_name = 'downloads/download.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        verification_code = request.POST.get('verification_code')

        if not verification_code:
            messages.error(request, 'Please enter a verification code.')
            return render(request, self.template_name)

        try:
            code = VerificationCode.objects.get(code=verification_code, is_used=False)

            # Get audit information
            ip_address = self.get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "Unknown")

            # Mark the verification code as used and store audit trail
            code.is_used = True
            code.used_at = datetime.datetime.now()
            code.download_ip = ip_address
            code.download_user_agent = user_agent
            code.save()

            # Redirect to GitHub release asset for download
            github_download_url = "https://github.com/your-username/your-repo/releases/download/v1.0.0/Setup_Dunware_CMS.exe"
            return redirect(github_download_url)

        except VerificationCode.DoesNotExist:
            messages.error(request, 'The verification code is invalid or has already been used.')
            return render(request, self.template_name)

    def get_client_ip(self, request):
        """Utility to get client IP, accounting for proxy headers."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
