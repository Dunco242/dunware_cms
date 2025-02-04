# core/sms.py
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class EmailToSMS:
    # SMS Gateway email addresses for different carriers
    CARRIERS = {
        'att':     '@txt.att.net',
        'tmobile': '@tmomail.net',
        'verizon': '@vtext.com',
        'sprint':  '@messaging.sprintpcs.com',
        'boost':   '@sms.myboostmobile.com',
        'cricket': '@sms.cricketwireless.net',
        'metro':   '@mymetropcs.com',
        'virgin':  '@vmobl.com',
    }

    @classmethod
    def send_sms(cls, phone_number, carrier, message):
        """
        Send SMS via email gateway
        :param phone_number: Phone number without any formatting (e.g., '1234567890')
        :param carrier: Carrier code from CARRIERS dict
        :param message: Message text
        :return: (success, message)
        """
        if carrier not in cls.CARRIERS:
            return False, f"Invalid carrier. Choose from: {', '.join(cls.CARRIERS.keys())}"

        try:
            # Construct the email address for SMS gateway
            sms_email = f"{phone_number}{cls.CARRIERS[carrier]}"

            # Send email
            send_mail(
                subject='',  # Subject is often ignored by carriers
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[sms_email],
                fail_silently=False,
            )

            logger.info(f"SMS sent to {phone_number} via {carrier}")
            return True, "Message sent successfully"

        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
            return False, str(e)
