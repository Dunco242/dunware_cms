from django.core.management.base import BaseCommand
from your_app.models import LegalDocument

class Command(BaseCommand):
    help = 'Update the current privacy policy'

    def handle(self, *args, **kwargs):
        # Your privacy policy content
        privacy_policy_content = """
        # Privacy Policy

        Last Updated: [Current Date]

        [Full privacy policy content here]
        """

        # Create a new legal document
        LegalDocument.objects.create(
            type='privacy_policy',
            version='1.1.0',  # Increment version
            content=privacy_policy_content,
            is_current=True
        )

        self.stdout.write(self.style.SUCCESS('Successfully updated privacy policy'))
