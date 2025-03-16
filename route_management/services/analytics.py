import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Sum, F, Q, ExpressionWrapper, FloatField
from django.db.models.functions import Coalesce

from ..models import Route, RouteStop, ServiceRequest, ServiceCompletion, CustomerFeedback

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for calculating analytics and generating reports"""

    @classmethod
    def calculate_daily_metrics(cls, date):
        """
        Calculate metrics for a specific date

        Args:
            date: The date to calculate metrics for

        Returns:
            dict: Dictionary of calculated metrics
        """
        # Calculate route metrics
        total_routes = Route.objects.filter(date=date).count()
        completed_routes = Route.objects.filter(date=date, status='completed').count()
        cancelled_routes = Route.objects.filter(date=date, status='cancelled').count()

        # Service request metrics
        completed_service_requests = ServiceRequest.objects.filter(
            route_stops__route__date=date,
            status='completed'
        ).distinct().count()

        cancelled_service_requests = ServiceRequest.objects.filter(
            route_stops__route__date=date,
            status='cancelled'
        ).distinct().count()

        total_service_requests = ServiceRequest.objects.filter(
            route_stops__route__date=date
        ).distinct().count()

        # Efficiency metrics
        routes_with_stops = Route.objects.filter(
            date=date,
            stops__isnull=False
        ).annotate(
            stop_count=Count('stops')
        )

        avg_stops_per_route = routes_with_stops.aggregate(
            avg=Coalesce(Avg('stop_count'), 0)
        )['avg']

        # Service duration
        completed_stops = RouteStop.objects.filter(
            route__date=date,
            status='completed',
            actual_arrival_time__isnull=False,
            actual_departure_time__isnull=False
        ).annotate(
            duration_minutes=ExpressionWrapper(
                (F('actual_departure_time') - F('actual_arrival_time')) / timedelta(minutes=1),
                output_field=FloatField()
            )
        )

        avg_service_duration_minutes = completed_stops.aggregate(
            avg=Coalesce(Avg('duration_minutes'), 0)
        )['avg']

        # Travel time
        routes_with_metrics = Route.objects.filter(
            date=date,
            estimated_drive_time_minutes__isnull=False
        )

        avg_travel_time_minutes = routes_with_metrics.aggregate(
            avg=Coalesce(Avg('estimated_drive_time_minutes'), 0)
        )['avg']

        avg_miles_per_route = routes_with_metrics.aggregate(
            avg=Coalesce(Avg('estimated_total_miles'), 0)
        )['avg']

        # Customer metrics
        feedbacks = CustomerFeedback.objects.filter(
            service_request__route_stops__route__date=date
        )

        avg_customer_rating = feedbacks.aggregate(
            avg=Coalesce(Avg('overall_rating'), 0)
        )['avg']

        # Return all metrics
        return {
            'total_routes': total_routes,
            'completed_routes': completed_routes,
            'cancelled_routes': cancelled_routes,
            'total_service_requests': total_service_requests,
            'completed_service_requests': completed_service_requests,
            'cancelled_service_requests': cancelled_service_requests,
            'avg_stops_per_route': round(avg_stops_per_route, 2),
            'avg_service_duration_minutes': round(avg_service_duration_minutes, 2),
            'avg_travel_time_minutes': round(avg_travel_time_minutes, 2),
            'avg_miles_per_route': round(avg_miles_per_route, 2),
            'avg_customer_rating': round(avg_customer_rating, 2) if avg_customer_rating else 0
        }

    @classmethod
    def generate_technician_performance_report(cls, start_date, end_date):
        """
        Generate performance report for technicians

        Args:
            start_date: Start date for the report
            end_date: End date for the report

        Returns:
            list: List of technician performance dictionaries
        """
        # Get all routes in date range
        routes = Route.objects.filter(
            date__range=[start_date, end_date],
            status__in=['completed', 'in_progress']
        ).select_related('technician')

        # Group by technician
        technician_metrics = {}

        for route in routes:
            technician_id = route.technician_id
            technician_name = route.technician.get_full_name()

            if technician_id not in technician_metrics:
                technician_metrics[technician_id] = {
                    'technician_id': technician_id,
                    'technician_name': technician_name,
                    'total_routes': 0,
                    'completed_routes': 0,
                    'total_stops': 0,
                    'completed_stops': 0,
                    'total_miles': 0,
                    'total_drive_time_minutes': 0,
                    'avg_stops_per_route': 0,
                    'avg_service_duration_minutes': 0,
                    'avg_customer_rating': 0,
                    'customer_rating_count': 0
                }

            # Count routes
            technician_metrics[technician_id]['total_routes'] += 1
            if route.status == 'completed':
                technician_metrics[technician_id]['completed_routes'] += 1

            # Add miles and drive time
            if route.estimated_total_miles:
                technician_metrics[technician_id]['total_miles'] += float(route.estimated_total_miles)

            if route.estimated_drive_time_minutes:
                technician_metrics[technician_id]['total_drive_time_minutes'] += route.estimated_drive_time_minutes

            # Get stops for this route
            stops = RouteStop.objects.filter(route=route)
            total_stops = stops.count()
            completed_stops = stops.filter(status='completed').count()

            technician_metrics[technician_id]['total_stops'] += total_stops
            technician_metrics[technician_id]['completed_stops'] += completed_stops

            # Get service durations
            completed_stops_with_duration = stops.filter(
                status='completed',
                actual_arrival_time__isnull=False,
                actual_departure_time__isnull=False
            ).annotate(
                duration_minutes=ExpressionWrapper(
                    (F('actual_departure_time') - F('actual_arrival_time')) / timedelta(minutes=1),
                    output_field=FloatField()
                )
            )

            for stop in completed_stops_with_duration:
                if hasattr(stop, 'duration_minutes') and stop.duration_minutes:
                    technician_metrics[technician_id]['avg_service_duration_minutes'] += stop.duration_minutes

            # Get customer ratings
            feedbacks = CustomerFeedback.objects.filter(
                service_request__route_stops__route=route
            )

            rating_sum = 0
            rating_count = 0

            for feedback in feedbacks:
                if feedback.overall_rating:
                    rating_sum += feedback.overall_rating
                    rating_count += 1

                if feedback.technician_rating:
                    rating_sum += feedback.technician_rating
                    rating_count += 1

            if rating_count > 0:
                technician_metrics[technician_id]['avg_customer_rating'] += rating_sum
                technician_metrics[technician_id]['customer_rating_count'] += rating_count

        # Calculate averages
        results = []

        for technician_id, metrics in technician_metrics.items():
            # Calculate derived metrics
            if metrics['total_routes'] > 0:
                metrics['avg_stops_per_route'] = round(metrics['total_stops'] / metrics['total_routes'], 2)

            service_durations_count = metrics['completed_stops']
            if service_durations_count > 0:
                metrics['avg_service_duration_minutes'] = round(metrics['avg_service_duration_minutes'] / service_durations_count, 2)

            if metrics['customer_rating_count'] > 0:
                metrics['avg_customer_rating'] = round(metrics['avg_customer_rating'] / metrics['customer_rating_count'], 2)

            # Round total miles
            metrics['total_miles'] = round(metrics['total_miles'], 2)

            # Calculate completion percentages
            if metrics['total_routes'] > 0:
                metrics['route_completion_rate'] = round(metrics['completed_routes'] / metrics['total_routes'] * 100, 2)
            else:
                metrics['route_completion_rate'] = 0

            if metrics['total_stops'] > 0:
                metrics['stop_completion_rate'] = round(metrics['completed_stops'] / metrics['total_stops'] * 100, 2)
            else:
                metrics['stop_completion_rate'] = 0

            results.append(metrics)

        # Sort by completed stops (descending)
        results.sort(key=lambda x: x['completed_stops'], reverse=True)

        return results

    @classmethod
    def generate_service_area_report(cls, start_date, end_date):
        """
        Generate performance report by service area

        Args:
            start_date: Start date for the report
            end_date: End date for the report

        Returns:
            list: List of service area performance dictionaries
        """
        # Get all service requests in date range that have been assigned to a route
        requests = ServiceRequest.objects.filter(
            route_stops__route__date__range=[start_date, end_date]
        ).select_related(
            'service_location',
            'service_location__service_area'
        ).distinct()

        # Group by service area
        area_metrics = {}

        for request in requests:
            service_location = request.service_location

            # Skip if no service area
            if not service_location or not service_location.service_area:
                continue

            service_area = service_location.service_area
            area_id = service_area.id
            area_name = service_area.name

            if area_id not in area_metrics:
                area_metrics[area_id] = {
                    'area_id': area_id,
                    'area_name': area_name,
                    'total_requests': 0,
                    'completed_requests': 0,
                    'total_customers': set(),
                    'avg_service_duration_minutes': 0,
                    'service_duration_count': 0,
                    'avg_travel_time_minutes': 0,
                    'travel_time_count': 0,
                    'avg_customer_rating': 0,
                    'customer_rating_count': 0
                }

            # Count requests
            area_metrics[area_id]['total_requests'] += 1
            if request.status == 'completed':
                area_metrics[area_id]['completed_requests'] += 1

            # Count unique customers
            area_metrics[area_id]['total_customers'].add(request.customer_id)

            # Get route stops for this request
            stops = RouteStop.objects.filter(service_request=request)

            # Get service durations
            completed_stops = stops.filter(
                status='completed',
                actual_arrival_time__isnull=False,
                actual_departure_time__isnull=False
            ).annotate(
                duration_minutes=ExpressionWrapper(
                    (F('actual_departure_time') - F('actual_arrival_time')) / timedelta(minutes=1),
                    output_field=FloatField()
                )
            )

            for stop in completed_stops:
                if hasattr(stop, 'duration_minutes') and stop.duration_minutes:
                    area_metrics[area_id]['avg_service_duration_minutes'] += stop.duration_minutes
                    area_metrics[area_id]['service_duration_count'] += 1

            # Get travel times (from previous stop)
            for stop in stops:
                if stop.drive_time_from_previous_minutes:
                    area_metrics[area_id]['avg_travel_time_minutes'] += stop.drive_time_from_previous_minutes
                    area_metrics[area_id]['travel_time_count'] += 1

            # Get customer ratings
            feedback = CustomerFeedback.objects.filter(service_request=request).first()
            if feedback and feedback.overall_rating:
                area_metrics[area_id]['avg_customer_rating'] += feedback.overall_rating
                area_metrics[area_id]['customer_rating_count'] += 1

        # Calculate averages
        results = []

        for area_id, metrics in area_metrics.items():
            # Convert set to count for total customers
            metrics['total_customers'] = len(metrics['total_customers'])

            # Calculate derived metrics
            if metrics['service_duration_count'] > 0:
                metrics['avg_service_duration_minutes'] = round(metrics['avg_service_duration_minutes'] / metrics['service_duration_count'], 2)
            else:
                metrics['avg_service_duration_minutes'] = 0

            if metrics['travel_time_count'] > 0:
                metrics['avg_travel_time_minutes'] = round(metrics['avg_travel_time_minutes'] / metrics['travel_time_count'], 2)
            else:
                metrics['avg_travel_time_minutes'] = 0

            if metrics['customer_rating_count'] > 0:
                metrics['avg_customer_rating'] = round(metrics['avg_customer_rating'] / metrics['customer_rating_count'], 2)
            else:
                metrics['avg_customer_rating'] = 0

            # Calculate completion percentages
            if metrics['total_requests'] > 0:
                metrics['completion_rate'] = round(metrics['completed_requests'] / metrics['total_requests'] * 100, 2)
            else:
                metrics['completion_rate'] = 0

            # Clean up temporary counts
            del metrics['service_duration_count']
            del metrics['travel_time_count']

            results.append(metrics)

        # Sort by total requests (descending)
        results.sort(key=lambda x: x['total_requests'], reverse=True)

        return results
