from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import LegalDocument
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Update the current privacy policy'

    def add_arguments(self, parser):
        parser.add_argument('--version', type=str, help='Version number for the policy')
        parser.add_argument('--file', type=str, help='Path to policy content file')

    def handle(self, *args, **options):
        try:
            # Get version from arguments or auto-increment
            if options['version']:
                new_version = options['version']
            else:
                current_policy = LegalDocument.objects.filter(
                    type='privacy_policy',
                    is_current=True
                ).first()
                if current_policy:
                    last_version = current_policy.version
                    major, minor, patch = map(int, last_version.split('.'))
                    new_version = f"{major}.{minor}.{patch + 1}"
                else:
                    new_version = '1.0.0'

            # Get content from file or default template
            if options['file']:
                with open(options['file'], 'r') as f:
                    privacy_policy_content = f.read()
            else:
                from core.utils import get_privacy_policy_content
                privacy_policy_content = get_privacy_policy_content()

            # Replace placeholder date with current date
            current_date = timezone.now().strftime('%Y-%m-%d')
            privacy_policy_content = privacy_policy_content.replace('[Current Date]', current_date)

            # Validate content
            if not privacy_policy_content or len(privacy_policy_content.strip()) < 100:
                raise ValueError("Privacy policy content appears to be empty or too short")

            # Create new policy
            LegalDocument.objects.create(
                type='privacy_policy',
                version=new_version,
                content=privacy_policy_content,
                is_current=True
            )

            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated privacy policy to version {new_version}')
            )

        except Exception as e:
            logger.error(f"Failed to update privacy policy: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Failed to update privacy policy: {str(e)}')
            )
            raise
