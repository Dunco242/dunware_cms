# utils.py
import os
from django.conf import settings
from django.template.loader import render_to_string

def get_privacy_policy_content():
    # Option 1: From a template
    return render_to_string('legal/privacy_policy_content.html')

    # Option 2: From a markdown file
    markdown_path = os.path.join(settings.BASE_DIR, 'legal_docs', 'privacy_policy.md')
    with open(markdown_path, 'r') as file:
        return file.read()
