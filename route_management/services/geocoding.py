import logging
import requests
from django.conf import settings
from ..models import GeocodeCache, ServiceLocation

logger = logging.getLogger(__name__)

class GeocodingService:
    """Service for geocoding addresses using Google Maps API"""

    @classmethod
    def geocode_location(cls, location):
        """
        Geocode a service location

        Args:
            location (ServiceLocation): The location to geocode

        Returns:
            bool: True if geocoding was successful, False otherwise
        """
        if not isinstance(location, ServiceLocation):
            raise ValueError("location must be a ServiceLocation instance")

        # Get address for geocoding
        address = location.get_geocoding_address()

        # Check cache first
        cached = GeocodeCache.objects.filter(address=address).first()
        if cached:
            logger.info(f"Using cached geocode for {address}")
            location.latitude = cached.latitude
            location.longitude = cached.longitude
            location.save(update_fields=['latitude', 'longitude'])
            return True

        # If no API key, fail gracefully
        if not hasattr(settings, 'GOOGLE_MAPS_API_KEY') or not settings.GOOGLE_MAPS_API_KEY:
            logger.error("No Google Maps API key found in settings")
            return False

        # Call Google Maps Geocoding API
        api_key = settings.GOOGLE_MAPS_API_KEY
        endpoint = "https://maps.googleapis.com/maps/api/geocode/json"

        try:
            response = requests.get(
                endpoint,
                params={
                    'address': address,
                    'key': api_key
                },
                timeout=10
            )

            # Parse response
            data = response.json()

            if data['status'] != 'OK':
                logger.error(f"Geocoding error for {address}: {data['status']}")
                return False

            # Get first result
            result = data['results'][0]
            location_data = result['geometry']['location']

            # Update the location
            location.latitude = location_data['lat']
            location.longitude = location_data['lng']
            location.save(update_fields=['latitude', 'longitude'])

            # Cache the result
            cache_entry = GeocodeCache(
                address=address,
                formatted_address=result['formatted_address'],
                latitude=location_data['lat'],
                longitude=location_data['lng'],
                geocode_quality=result['geometry']['location_type']
            )

            # Add address components if available
            for component in result.get('address_components', []):
                types = component['types']

                if 'country' in types:
                    cache_entry.country = component['long_name']
                elif 'administrative_area_level_1' in types:
                    cache_entry.administrative_area_1 = component['long_name']
                elif 'administrative_area_level_2' in types:
                    cache_entry.administrative_area_2 = component['long_name']
                elif 'locality' in types:
                    cache_entry.locality = component['long_name']
                elif 'postal_code' in types:
                    cache_entry.postal_code = component['long_name']

            cache_entry.save()

            logger.info(f"Successfully geocoded {address}")
            return True

        except Exception as e:
            logger.exception(f"Error geocoding {address}: {str(e)}")
            return False

    @classmethod
    def bulk_geocode_locations(cls, limit=50):
        """
        Bulk geocode service locations that don't have coordinates

        Args:
            limit (int): Maximum number of locations to geocode

        Returns:
            tuple: (success_count, error_count, remaining_count)
        """
        # Get locations that need geocoding
        locations = ServiceLocation.objects.filter(
            latitude__isnull=True,
            longitude__isnull=True
        )[:limit]

        success_count = 0
        error_count = 0

        for location in locations:
            try:
                if cls.geocode_location(location):
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1

        # Count remaining locations
        remaining_count = ServiceLocation.objects.filter(
            latitude__isnull=True,
            longitude__isnull=True
        ).count()

        return success_count, error_count, remaining_count
