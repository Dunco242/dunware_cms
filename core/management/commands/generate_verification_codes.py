# management/commands/generate_verification_codes.py
from django.core.management.base import BaseCommand
from downloads.models import VerificationCode
import uuid

class Command(BaseCommand):
    help = 'Generates 20 verification codes'

    def handle(self, *args, **kwargs):
        codes = [
            'A7B2C9D4E1F6',
            'X8Y3Z1W5Q2R7',
            'P4K9M2N6J8H3',
            'T1R5Y7U3I9O2',
            'F6G2H8J4K1L9',
            'Q3W9E2R5T7Y1',
            'Z4X8C1V6B2N7',
            'M9L3K7J2H5G4',
            'I2O8U4Y1T6R9',
            'N5B7V3C9X1Z2',
            'H4J8K2L6M9N1',
            'R7T3Y9U5I2O8',
            'W1Q6E4Z8X3C9',
            'Y2U7I3O9P4T6',
            'C8V4B9N2M7K1',
            'L6H2J8K4M9N3',
            'O5I9U3Y7T1R2',
            'X4Z8C6V2B7N9',
            'K7M3N9J5H2G4',
            'T9R2Y6U4I8O1'
        ]

        for code in codes:
            VerificationCode.objects.get_or_create(code=code)

        self.stdout.write(self.style.SUCCESS('Successfully generated 20 verification codes'))
