# views.py
from django.views.generic import View
from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse
from django.conf import settings
from .models import VerificationCode
import os
from django.contrib import messages
import datetime

class DownloadView(View):
    template_name = 'downloads/download.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        verification_code = request.POST.get('verification_code')

        try:
            code = VerificationCode.objects.get(code=verification_code, is_used=False)

            # Mark code as used
            code.is_used = True
            code.used_at = datetime.datetime.now()
            code.save()

            # Path to your file (update with your actual file path)
            file_path = os.path.join(settings.MEDIA_ROOT, 'downloads', 'Setup_Dunware_CMS.exe')

            if os.path.exists(file_path):
                return FileResponse(
                    open(file_path, 'rb'),
                    as_attachment=True,
                    filename='Setup_Dunware_CMS.exe'
                )
            else:
                messages.error(request, 'File not found. Please contact support.')
                return render(request, self.template_name)

        except VerificationCode.DoesNotExist:
            messages.error(request, 'Invalid or already used verification code.')
            return render(request, self.template_name)
