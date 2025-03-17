import logging
import requests
from django.conf import settings
from ..models import GeocodeCache, ServiceLocation

logger = logging.getLogger(__name__)

class GeocodingService:
    """Service for geocoding addresses using Here Maps API"""

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
        if not hasattr(settings, 'HERE_MAPS_API_KEY') or not settings.HERE_MAPS_API_KEY:
            logger.error("No Here Maps API key found in settings")
            return False

        # Here Maps Geocoding API endpoint
        endpoint = "https://geocode.search.hereapi.com/v1/geocode"

        try:
            response = requests.get(
                endpoint,
                params={
                    'apiKey': settings.HERE_MAPS_API_KEY,
                    'q': address
                },
                timeout=10
            )

            # Parse response
            data = response.json()

            # Check if results exist
            if not data.get('items'):
                logger.error(f"No geocoding results for {address}")
                return False

            # Get first result
            result = data['items'][0]
            location_data = result.get('position', {})
            address_data = result.get('address', {})

            # Update the location
            location.latitude = location_data.get('lat')
            location.longitude = location_data.get('lng')
            location.save(update_fields=['latitude', 'longitude'])

            # Create cache entry
            cache_entry = GeocodeCache(
                address=address,
                formatted_address=address_data.get('label', ''),
                latitude=location_data.get('lat'),
                longitude=location_data.get('lng'),
                geocode_quality=result.get('resultType', '')
            )

            # Extract address components
            cache_entry.country = address_data.get('countryName', '')
            cache_entry.administrative_area_1 = address_data.get('state', '')
            cache_entry.administrative_area_2 = address_data.get('county', '')
            cache_entry.locality = address_data.get('city', '')
            cache_entry.postal_code = address_data.get('postalCode', '')

            cache_entry.save()

            logger.info(f"Successfully geocoded {address}")
            return True

        except requests.RequestException as e:
            logger.exception(f"Request error geocoding {address}: {str(e)}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error geocoding {address}: {str(e)}")
            return False

    @classmethod
    def calculate_route(cls, waypoints):
        """
        Calculate route between multiple waypoints using Here Maps Routing API

        Args:
            waypoints (list): List of coordinate tuples [(lat1, lon1), (lat2, lon2), ...]

        Returns:
            dict: Route details including distance, duration, and polyline
                  or None if calculation fails
        """
        # Validate input
        if not waypoints or len(waypoints) < 2:
            logger.error("Insufficient waypoints for route calculation")
            return None

        # Validate API key
        if not hasattr(settings, 'HERE_MAPS_API_KEY') or not settings.HERE_MAPS_API_KEY:
            logger.error("No Here Maps API key found in settings")
            return None

        # Here Maps Routing API endpoint
        endpoint = "https://router.hereapi.com/v8/routes"

        try:
            # Prepare waypoints for API
            routing_waypoints = [
                {
                    "lat": point[0],
                    "lng": point[1]
                } for point in waypoints
            ]

            # Request payload
            payload = {
                "origin": routing_waypoints[0],
                "destination": routing_waypoints[-1],
                "waypoints": routing_waypoints[1:-1] if len(routing_waypoints) > 2 else [],
                "transportMode": "car",
                "return": "polyline,summary,actions"
            }

            # Make API request
            response = requests.post(
                endpoint,
                params={"apiKey": settings.HERE_MAPS_API_KEY},
                json=payload,
                timeout=15
            )

            # Parse response
            data = response.json()

            # Extract route information
            if not data.get('routes'):
                logger.error("No routes found in Here Maps response")
                return None

            route = data['routes'][0]
            summary = route.get('summary', {})

            return {
                "total_distance": summary.get('length'),  # meters
                "total_duration": summary.get('duration'),  # seconds
                "polyline": route.get('sections', [{}])[0].get('polyline'),
                "raw_response": data
            }

        except requests.RequestException as e:
            logger.exception(f"Request error calculating route: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error calculating route: {str(e)}")
            return None

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
