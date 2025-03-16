import logging
import math
import requests
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.db.models import F

from ..models import Route, RouteStop, DistanceMatrixCache, OptimizationSettings, RouteLog

logger = logging.getLogger(__name__)

class RouteOptimizationService:
    """Service for optimizing routes"""

    @classmethod
    def optimize_route(cls, route):
        """
        Optimize the ordering of stops in a route

        Args:
            route (Route): The route to optimize

        Returns:
            bool: True if optimization was successful, False otherwise
        """
        if not isinstance(route, Route):
            raise ValueError("route must be a Route instance")

        # Get the stops for this route
        stops = RouteStop.objects.filter(route=route).select_related(
            'service_request', 'service_request__service_location'
        )

        if not stops.exists():
            logger.warning(f"No stops to optimize for route {route.route_id}")
            return False

        # Get optimization settings
        settings = OptimizationSettings.objects.filter(is_default=True).first()
        if not settings:
            settings = OptimizationSettings.objects.create(
                name="Default Settings",
                is_default=True
            )

        # Build list of locations
        locations = []
        stop_data = {}

        # Start location
        if route.start_latitude and route.start_longitude:
            locations.append({
                'lat': float(route.start_latitude),
                'lng': float(route.start_longitude),
                'id': 'start'
            })

        # Stop locations
        for stop in stops:
            location = stop.service_request.service_location
            if location.latitude and location.longitude:
                loc_id = f"stop_{stop.id}"
                locations.append({
                    'lat': float(location.latitude),
                    'lng': float(location.longitude),
                    'id': loc_id
                })
                stop_data[loc_id] = stop

        # End location (if different from start)
        if route.end_latitude and route.end_longitude:
            if route.start_latitude != route.end_latitude or route.start_longitude != route.end_longitude:
                locations.append({
                    'lat': float(route.end_latitude),
                    'lng': float(route.end_longitude),
                    'id': 'end'
                })

        # If we have at least 3 locations (start, one stop, end), optimize
        if len(locations) < 3:
            logger.warning(f"Not enough geocoded locations for route {route.route_id}")
            return False

        try:
            # Build distance matrix
            distance_matrix = cls._build_distance_matrix(locations)

            # Call optimization algorithm
            if settings.prioritize == 'distance':
                optimized_order = cls._optimize_tsp(distance_matrix, 'distance')
            else:
                optimized_order = cls._optimize_tsp(distance_matrix, 'time')

            # Update stop order
            return cls._update_stop_order(route, optimized_order, stop_data)

        except Exception as e:
            logger.exception(f"Error optimizing route {route.route_id}: {str(e)}")

            # Create error log
            RouteLog.objects.create(
                route=route,
                log_type='issue',
                message=f"Optimization error: {str(e)}"
            )

            return False

    @classmethod
    def _build_distance_matrix(cls, locations):
        """
        Build a distance matrix between all locations

        Args:
            locations (list): List of location dictionaries with lat, lng, and id

        Returns:
            dict: Distance matrix with structure {origin_id: {destination_id: {'distance': meters, 'duration': seconds}}}
        """
        matrix = {}

        # Check if we have Google Maps API key
        use_api = hasattr(settings, 'GOOGLE_MAPS_API_KEY') and settings.GOOGLE_MAPS_API_KEY

        for origin in locations:
            origin_id = origin['id']
            matrix[origin_id] = {}

            for destination in locations:
                destination_id = destination['id']

                # Skip same location
                if origin_id == destination_id:
                    matrix[origin_id][destination_id] = {
                        'distance': 0,
                        'duration': 0
                    }
                    continue

                # Check cache first
                if use_api:
                    cache_entry = DistanceMatrixCache.objects.filter(
                        origin_latitude=origin['lat'],
                        origin_longitude=origin['lng'],
                        destination_latitude=destination['lat'],
                        destination_longitude=destination['lng'],
                        travel_mode='driving'
                    ).first()

                    if cache_entry:
                        matrix[origin_id][destination_id] = {
                            'distance': cache_entry.distance_meters,
                            'duration': cache_entry.duration_seconds
                        }
                        continue

                # If no API or not in cache, use straight-line calculation
                if not use_api:
                    distance, duration = cls._calculate_straight_line(
                        origin['lat'], origin['lng'],
                        destination['lat'], destination['lng']
                    )

                    matrix[origin_id][destination_id] = {
                        'distance': distance,
                        'duration': duration
                    }
                else:
                    # Use Google Distance Matrix API
                    try:
                        api_key = settings.GOOGLE_MAPS_API_KEY
                        endpoint = "https://maps.googleapis.com/maps/api/distancematrix/json"

                        response = requests.get(
                            endpoint,
                            params={
                                'origins': f"{origin['lat']},{origin['lng']}",
                                'destinations': f"{destination['lat']},{destination['lng']}",
                                'mode': 'driving',
                                'key': api_key
                            },
                            timeout=10
                        )

                        data = response.json()

                        if data['status'] == 'OK' and data['rows'][0]['elements'][0]['status'] == 'OK':
                            element = data['rows'][0]['elements'][0]
                            distance = element['distance']['value']  # meters
                            duration = element['duration']['value']  # seconds

                            # Cache the result
                            DistanceMatrixCache.objects.create(
                                origin_latitude=origin['lat'],
                                origin_longitude=origin['lng'],
                                destination_latitude=destination['lat'],
                                destination_longitude=destination['lng'],
                                travel_mode='driving',
                                distance_meters=distance,
                                duration_seconds=duration
                            )

                            matrix[origin_id][destination_id] = {
                                'distance': distance,
                                'duration': duration
                            }
                        else:
                            # Fallback to straight-line calculation
                            distance, duration = cls._calculate_straight_line(
                                origin['lat'], origin['lng'],
                                destination['lat'], destination['lng']
                            )

                            matrix[origin_id][destination_id] = {
                                'distance': distance,
                                'duration': duration
                            }

                    except Exception:
                        # Fallback to straight-line calculation
                        distance, duration = cls._calculate_straight_line(
                            origin['lat'], origin['lng'],
                            destination['lat'], destination['lng']
                        )

                        matrix[origin_id][destination_id] = {
                            'distance': distance,
                            'duration': duration
                        }

        return matrix

    @classmethod
    def _calculate_straight_line(cls, lat1, lon1, lat2, lon2):
        """
        Calculate straight-line distance and estimated duration between coordinates

        Args:
            lat1, lon1: Origin coordinates
            lat2, lon2: Destination coordinates

        Returns:
            tuple: (distance_meters, duration_seconds)
        """
        # Earth radius in meters
        R = 6371000

        # Convert to radians
        lat1_rad = math.radians(float(lat1))
        lon1_rad = math.radians(float(lon1))
        lat2_rad = math.radians(float(lat2))
        lon2_rad = math.radians(float(lon2))

        # Haversine formula
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c  # meters

        # Estimate duration (assume average speed of 50 km/h)
        # 50 km/h = 13.89 m/s
        duration = distance / 13.89  # seconds

        return int(distance), int(duration)

    @classmethod
    def _optimize_tsp(cls, distance_matrix, optimize_for='distance'):
        """
        Solve the traveling salesman problem to find the optimal route order

        Args:
            distance_matrix (dict): Distance matrix between locations
            optimize_for (str): 'distance' or 'time' to optimize for

        Returns:
            list: Optimized order of location IDs
        """
        # Get all locations except start and end
        all_locations = set(distance_matrix.keys())
        start_location = 'start' if 'start' in all_locations else None
        end_location = 'end' if 'end' in all_locations else start_location

        # Remove start and end from locations to visit
        locations_to_visit = all_locations.copy()
        if start_location:
            locations_to_visit.remove(start_location)
        if end_location and end_location != start_location:
            locations_to_visit.remove(end_location)

        # Convert to list for ordering
        locations_to_visit = list(locations_to_visit)

        # If very few locations, just try all permutations
        if len(locations_to_visit) <= 5:
            return cls._optimize_brute_force(
                distance_matrix,
                locations_to_visit,
                start_location,
                end_location,
                optimize_for
            )

        # For more locations, use a nearest neighbor heuristic
        return cls._optimize_nearest_neighbor(
            distance_matrix,
            locations_to_visit,
            start_location,
            end_location,
            optimize_for
        )

    @classmethod
    def _optimize_brute_force(cls, distance_matrix, locations_to_visit, start_location, end_location, optimize_for):
        """
        Optimization using brute force approach (trying all permutations)

        Args:
            distance_matrix (dict): Distance matrix between locations
            locations_to_visit (list): Locations to be visited
            start_location (str): Starting location ID
            end_location (str): Ending location ID
            optimize_for (str): 'distance' or 'time' to optimize for

        Returns:
            list: Optimized order of location IDs
        """
        import itertools

        best_distance = float('inf')
        best_route = None

        # Try all permutations
        for perm in itertools.permutations(locations_to_visit):
            route = []
            if start_location:
                route.append(start_location)
            route.extend(perm)
            if end_location and end_location != start_location:
                route.append(end_location)

            # Calculate total distance/time
            total = 0
            for i in range(len(route) - 1):
                current = route[i]
                next_loc = route[i + 1]
                value = distance_matrix[current][next_loc]['distance'] if optimize_for == 'distance' else distance_matrix[current][next_loc]['duration']
                total += value

            if total < best_distance:
                best_distance = total
                best_route = route

        return best_route

    @classmethod
    def _optimize_nearest_neighbor(cls, distance_matrix, locations_to_visit, start_location, end_location, optimize_for):
        """
        Optimization using nearest neighbor heuristic

        Args:
            distance_matrix (dict): Distance matrix between locations
            locations_to_visit (list): Locations to be visited
            start_location (str): Starting location ID
            end_location (str): Ending location ID
            optimize_for (str): 'distance' or 'time' to optimize for

        Returns:
            list: Optimized order of location IDs
        """
        # Start with an empty route
        route = []
        if start_location:
            route.append(start_location)

        # Make a copy of locations to visit
        unvisited = locations_to_visit.copy()

        # Start from the starting location
        current_location = start_location if start_location else unvisited.pop(0)

        # Keep adding nearest unvisited location
        while unvisited:
            # Find nearest unvisited location
            nearest = None
            nearest_value = float('inf')

            for loc in unvisited:
                value = distance_matrix[current_location][loc]['distance'] if optimize_for == 'distance' else distance_matrix[current_location][loc]['duration']
                if value < nearest_value:
                    nearest = loc
                    nearest_value = value

            # Add nearest to route and remove from unvisited
            route.append(nearest)
            unvisited.remove(nearest)
            current_location = nearest

        # Add end location if different from start
        if end_location and end_location != start_location:
            route.append(end_location)

        return route

    @classmethod
    def _update_stop_order(cls, route, optimized_order, stop_data):
        """
        Update the stop order based on optimization results

        Args:
            route (Route): The route to update
            optimized_order (list): Optimized order of location IDs
            stop_data (dict): Dictionary mapping location IDs to RouteStop objects

        Returns:
            bool: True if update was successful, False otherwise
        """
        # Filter out start and end locations
        stop_order = [loc_id for loc_id in optimized_order if loc_id.startswith('stop_')]

        # Update stop numbers
        for i, loc_id in enumerate(stop_order, 1):
            stop = stop_data[loc_id]
            stop.stop_number = i
            stop.save(update_fields=['stop_number'])

        # Mark route as optimized
        route.is_optimized = True
        route.optimization_timestamp = timezone.now()
        route.save(update_fields=['is_optimized', 'optimization_timestamp'])

        # Create log entry
        RouteLog.objects.create(
            route=route,
            log_type='system',
            message=f"Route optimized for {len(stop_order)} stops"
        )

        # Update route metrics
        cls.calculate_route_metrics(route)

        return True

    @classmethod
    def calculate_route_metrics(cls, route):
        """
        Calculate metrics for a route (total distance, time, etc.)

        Args:
            route (Route): The route to calculate metrics for

        Returns:
            dict: Dictionary of calculated metrics
        """
        stops = RouteStop.objects.filter(route=route).order_by('stop_number').select_related(
            'service_request', 'service_request__service_location'
        )

        if not stops.exists():
            return {
                'total_miles': 0,
                'drive_time_minutes': 0,
                'total_duration_minutes': 0
            }

        # Build list of locations
        locations = []

        # Start location
        if route.start_latitude and route.start_longitude:
            locations.append({
                'lat': float(route.start_latitude),
                'lng': float(route.start_longitude),
                'id': 'start',
                'duration': 0  # No service time at start
            })

        # Stop locations
        for stop in stops:
            location = stop.service_request.service_location
            if location.latitude and location.longitude:
                locations.append({
                    'lat': float(location.latitude),
                    'lng': float(location.longitude),
                    'id': f"stop_{stop.id}",
                    'duration': stop.estimated_duration_minutes or stop.service_request.estimated_duration_minutes or 60
                })

        # End location (if different from start)
        if route.end_latitude and route.end_longitude:
            if not route.start_latitude or not route.start_longitude or route.start_latitude != route.end_latitude or route.start_longitude != route.end_longitude:
                locations.append({
                    'lat': float(route.end_latitude),
                    'lng': float(route.end_longitude),
                    'id': 'end',
                    'duration': 0  # No service time at end
                })

        # If less than 2 locations, we can't calculate metrics
        if len(locations) < 2:
            return {
                'total_miles': 0,
                'drive_time_minutes': 0,
                'total_duration_minutes': 0
            }

        # Calculate metrics
        total_distance = 0
        total_drive_time = 0
        total_duration = 0

        # Calculate distance and time between each location
        for i in range(len(locations) - 1):
            origin = locations[i]
            destination = locations[i + 1]

            distance, drive_time = cls._calculate_straight_line(
                origin['lat'], origin['lng'],
                destination['lat'], destination['lng']
            )

            total_distance += distance
            total_drive_time += drive_time
            total_duration += drive_time + (destination['duration'] * 60)  # Add service time in seconds

        # Convert to miles and minutes
        total_miles = total_distance / 1609.34  # Convert meters to miles
        drive_time_minutes = total_drive_time / 60  # Convert seconds to minutes
        total_duration_minutes = total_duration / 60  # Convert seconds to minutes

        # Update route
        route.estimated_total_miles = round(total_miles, 2)
        route.estimated_drive_time_minutes = round(drive_time_minutes)
        route.save(update_fields=['estimated_total_miles', 'estimated_drive_time_minutes'])

        return {
            'total_miles': round(total_miles, 2),
            'drive_time_minutes': round(drive_time_minutes),
            'total_duration_minutes': round(total_duration_minutes)
        }
