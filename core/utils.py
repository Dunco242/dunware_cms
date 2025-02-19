# utils.py
import os
from django.conf import settings
from django.template.loader import render_to_string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def get_privacy_policy_content():
    # Option 1: From a template
    return render_to_string('legal/privacy_policy_content.html')

    # Option 2: From a markdown file
    markdown_path = os.path.join(settings.BASE_DIR, 'legal_docs', 'privacy_policy.md')
    with open(markdown_path, 'r') as file:
        return file.read()


def send_email_message(email_message):
    """Send an email using the configured SMTP settings"""
    email_account = email_message.account

    msg = MIMEMultipart()
    msg['From'] = email_account.email_address
    msg['To'] = ', '.join(email_message.to_emails)
    msg['Subject'] = email_message.subject

    msg.attach(MIMEText(email_message.body_text, 'plain'))

    try:
        server = smtplib.SMTP(email_account.smtp_server, email_account.smtp_port)
        server.starttls()
        server.login(email_account.username, email_account.password)
        server.sendmail(email_account.email_address, email_message.to_emails, msg.as_string())
        server.quit()
    except Exception as e:
        raise Exception(f"SMTP Error: {str(e)}")
