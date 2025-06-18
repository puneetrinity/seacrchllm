# app/services/analytics_service.py - Analytics Service
"""
Comprehensive analytics service for tracking search performance,
user behavior, system metrics, and business intelligence.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
import json
from dataclasses import dataclass, field
from collections import defaultdict, Counter

# Pydantic models
from pydantic import BaseModel, Field

# Database and cache
from app.database.connection import DatabaseManager
from app.cache.redis_manager import RedisManager

# Performance monitoring
from prometheus_client import Counter as PrometheusCounter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Metrics
ANALYTICS_EVENTS = PrometheusCounter('analytics_events_total', 'Total analytics events', ['event_type'])
ANALYTICS_QUERY_DURATION = Histogram('analytics_query_duration_seconds', 'Analytics query duration')
ANALYTICS_CACHE_HITS = PrometheusCounter('analytics_cache_hits_total', 'Analytics cache hits')

class EventType(str, Enum):
    """Types of analytics events"""
    SEARCH_REQUEST = "search_request"
    SEARCH_COMPLETION = "search_completion"
    USER_SESSION = "user_session"
    API_CALL = "api_call"
    ERROR_EVENT = "error_event"
    PERFORMANCE_METRIC = "performance_metric"
    USER_FEEDBACK = "user_feedback"
    WORKFLOW_EXECUTION = "workflow_execution"
    CACHE_EVENT = "cache_event"
    SYSTEM_METRIC = "system_metric"

class TimeRange(str, Enum):
    """Time range options for analytics queries"""
    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"
    YEAR = "365d"

class MetricType(str, Enum):
    """Types of metrics"""
    COUNT = "count"
    AVERAGE = "average"
    SUM = "sum"
    PERCENTAGE = "percentage"
    RATE = "rate"
    HISTOGRAM = "histogram"

@dataclass
class AnalyticsEvent:
    """Analytics event data structure"""
    event_id: str
    event_type: EventType
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class AnalyticsQuery(BaseModel):
    """Analytics query parameters"""
    metric_type: MetricType
    event_types: List[EventType] = Field(default_factory=list)
    time_range: TimeRange = TimeRange.DAY
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    group_by: List[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=10000)

class MetricResult(BaseModel):
    """Analytics metric result"""
    metric_name: str
    metric_type: MetricType
    value: Union[float, int, Dict[str, Any]]
    time_range: str
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DashboardData(BaseModel):
    """Dashboard data structure"""
    title: str
    metrics: List[MetricResult]
    charts: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime
    refresh_interval: int = 300  # seconds

class EventCollector:
    """Collects and buffers analytics events"""
    
    def __init__(self, redis_manager: RedisManager, batch_size: int = 100):
        self.redis_manager = redis_manager
        self.batch_size = batch_size
        self.event_buffer: List[AnalyticsEvent] = []
        self.buffer_lock = asyncio.Lock()
        self.namespace = "analytics_events"
    
    async def track_event(self, event: AnalyticsEvent):
        """Track a single analytics event"""
        async with self.buffer_lock:
            self.event_buffer.append(event)
            
            # Flush buffer if it reaches batch size
            if len(self.event_buffer) >= self.batch_size:
                await self._flush_buffer()
        
        # Record metric
        ANALYTICS_EVENTS.labels(event_type=event.event_type.value).inc()
    
    async def track_search_request(self, query: str, user_id: Optional[str] = None,
                                 session_id: Optional[str] = None, **properties):
        """Track search request event"""
        event = AnalyticsEvent(
            event_id=f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query) % 10000}",
            event_type=EventType.SEARCH_REQUEST,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            properties={
                'query': query,
                'query_length': len(query),
                **properties
            }
        )
        await self.track_event(event)
    
    async def track_search_completion(self, query: str, duration: float,
                                    confidence: float, result_count: int,
                                    user_id: Optional[str] = None,
                                    session_id: Optional[str] = None,
                                    **properties):
        """Track search completion event"""
        event = AnalyticsEvent(
            event_id=f"completion_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query) % 10000}",
            event_type=EventType.SEARCH_COMPLETION,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            properties={
                'query': query,
                'duration_seconds': duration,
                'confidence_score': confidence,
                'result_count': result_count,
                **properties
            }
        )
        await self.track_event(event)
    
    async def track_user_feedback(self, query: str, rating: int,
                                feedback: Optional[str] = None,
                                user_id: Optional[str] = None,
                                session_id: Optional[str] = None):
        """Track user feedback event"""
        event = AnalyticsEvent(
            event_id=f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(query) % 10000}",
            event_type=EventType.USER_FEEDBACK,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            properties={
                'query': query,
                'rating': rating,
                'feedback': feedback
            }
        )
        await self.track_event(event)
    
    async def track_api_call(self, endpoint: str, method: str, status_code: int,
                           duration: float, user_id: Optional[str] = None,
                           **properties):
        """Track API call event"""
        event = AnalyticsEvent(
            event_id=f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(endpoint) % 10000}",
            event_type=EventType.API_CALL,
            timestamp=datetime.now(),
            user_id=user_id,
            properties={
                'endpoint': endpoint,
                'method': method,
                'status_code': status_code,
                'duration_seconds': duration,
                **properties
            }
        )
        await self.track_event(event)
    
    async def _flush_buffer(self):
        """Flush event buffer to storage"""
        if not self.event_buffer:
            return
        
        try:
            # Convert events to dictionaries
            events_data = []
            for event in self.event_buffer:
                event_dict = {
                    'event_id': event.event_id,
                    'event_type': event.event_type.value,
                    'timestamp': event.timestamp.isoformat(),
                    'user_id': event.user_id,
                    'session_id': event.session_id,
                    'properties': event.properties,
                    'metadata': event.metadata
                }
                events_data.append(event_dict)
            
            # Store in Redis as a list
            await self.redis_manager.set(
                f"events_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                events_data,
                ttl=86400,  # 24 hours
                namespace=self.namespace
            )
            
            logger.info(f"Flushed {len(self.event_buffer)} events to storage")
            self.event_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush event buffer: {e}")

class MetricsCalculator:
    """Calculates various analytics metrics"""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
    
    async def calculate_search_metrics(self, time_range: TimeRange) -> Dict[str, Any]:
        """Calculate search-related metrics"""
        start_time, end_time = self._get_time_range(time_range)
        
        # Get events from cache/database
        events = await self._get_events(
            event_types=[EventType.SEARCH_REQUEST, EventType.SEARCH_COMPLETION],
            start_time=start_time,
            end_time=end_time
        )
        
        # Calculate metrics
        metrics = {
            'total_searches': 0,
            'completed_searches': 0,
            'average_response_time': 0.0,
            'average_confidence': 0.0,
            'success_rate': 0.0,
            'query_types': Counter(),
            'hourly_distribution': defaultdict(int)
        }
        
        completion_times = []
        confidence_scores = []
        
        for event in events:
            if event['event_type'] == EventType.SEARCH_REQUEST.value:
                metrics['total_searches'] += 1
                
                # Track query types if available
                query_type = event.get('properties', {}).get('query_type')
                if query_type:
                    metrics['query_types'][query_type] += 1
                
                # Track hourly distribution
                hour = datetime.fromisoformat(event['timestamp']).hour
                metrics['hourly_distribution'][hour] += 1
            
            elif event['event_type'] == EventType.SEARCH_COMPLETION.value:
                metrics['completed_searches'] += 1
                
                duration = event.get('properties', {}).get('duration_seconds', 0)
                if duration:
                    completion_times.append(duration)
                
                confidence = event.get('properties', {}).get('confidence_score', 0)
                if confidence:
                    confidence_scores.append(confidence)
        
        # Calculate averages
        if completion_times:
            metrics['average_response_time'] = sum(completion_times) / len(completion_times)
        
        if confidence_scores:
            metrics['average_confidence'] = sum(confidence_scores) / len(confidence_scores)
        
        # Calculate success rate
        if metrics['total_searches'] > 0:
            metrics['success_rate'] = metrics['completed_searches'] / metrics['total_searches']
        
        return metrics
    
    async def calculate_user_metrics(self, time_range: TimeRange,
                                   user_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculate user behavior metrics"""
        start_time, end_time = self._get_time_range(time_range)
        
        events = await self._get_events(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id
        )
        
        metrics = {
            'unique_users': set(),
            'total_sessions': set(),
            'searches_per_user': defaultdict(int),
            'session_durations': [],
            'user_retention': {},
            'popular_queries': Counter()
        }
        
        for event in events:
            user_id = event.get('user_id')
            session_id = event.get('session_id')
            
            if user_id:
                metrics['unique_users'].add(user_id)
                
                if event['event_type'] == EventType.SEARCH_REQUEST.value:
                    metrics['searches_per_user'][user_id] += 1
                    
                    query = event.get('properties', {}).get('query', '')
                    if query:
                        metrics['popular_queries'][query] += 1
            
            if session_id:
                metrics['total_sessions'].add(session_id)
        
        # Convert sets to counts
        metrics['unique_users'] = len(metrics['unique_users'])
        metrics['total_sessions'] = len(metrics['total_sessions'])
        
        return metrics
    
    async def calculate_performance_metrics(self, time_range: TimeRange) -> Dict[str, Any]:
        """Calculate system performance metrics"""
        start_time, end_time = self._get_time_range(time_range)
        
        events = await self._get_events(
            event_types=[EventType.API_CALL, EventType.PERFORMANCE_METRIC],
            start_time=start_time,
            end_time=end_time
        )
        
        metrics = {
            'api_response_times': [],
            'error_rates': defaultdict(int),
            'endpoint_usage': Counter(),
            'status_code_distribution': Counter(),
            'system_load': []
        }
        
        for event in events:
            if event['event_type'] == EventType.API_CALL.value:
                props = event.get('properties', {})
                
                duration = props.get('duration_seconds')
                if duration:
                    metrics['api_response_times'].append(duration)
                
                endpoint = props.get('endpoint')
                if endpoint:
                    metrics['endpoint_usage'][endpoint] += 1
                
                status_code = props.get('status_code')
                if status_code:
                    metrics['status_code_distribution'][status_code] += 1
                    
                    if status_code >= 400:
                        metrics['error_rates'][endpoint] += 1
        
        # Calculate averages
        if metrics['api_response_times']:
            metrics['average_response_time'] = (
                sum(metrics['api_response_times']) / len(metrics['api_response_times'])
            )
            metrics['p95_response_time'] = self._calculate_percentile(
                metrics['api_response_times'], 95
            )
        
        return metrics
    
    def _get_time_range(self, time_range: TimeRange) -> Tuple[datetime, datetime]:
        """Convert time range enum to datetime range"""
        end_time = datetime.now()
        
        if time_range == TimeRange.HOUR:
            start_time = end_time - timedelta(hours=1)
        elif time_range == TimeRange.DAY:
            start_time = end_time - timedelta(days=1)
        elif time_range == TimeRange.WEEK:
            start_time = end_time - timedelta(weeks=1)
        elif time_range == TimeRange.MONTH:
            start_time = end_time - timedelta(days=30)
        elif time_range == TimeRange.QUARTER:
            start_time = end_time - timedelta(days=90)
        elif time_range == TimeRange.YEAR:
            start_time = end_time - timedelta(days=365)
        else:
            start_time = end_time - timedelta(days=1)
        
        return start_time, end_time
    
    async def _get_events(self, event_types: Optional[List[EventType]] = None,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get events from storage with filters"""
        # This is a simplified implementation
        # In practice, you'd query the database or search through Redis
        
        # For now, return mock data
        events = []
        
        # This would be replaced with actual database/cache queries
        logger.info(f"Getting events: types={event_types}, time_range={start_time} to {end_time}")
        
        return events
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile of values"""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]

class AnalyticsService:
    """Main analytics service"""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.event_collector = EventCollector(redis_manager)
        self.metrics_calculator = MetricsCalculator(db_manager, redis_manager)
        
        # Cache for dashboard data
        self.dashboard_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def track_event(self, event: AnalyticsEvent):
        """Track analytics event"""
        await self.event_collector.track_event(event)
    
    async def track_search_request(self, query: str, user_id: Optional[str] = None,
                                 session_id: Optional[str] = None, **properties):
        """Track search request"""
        await self.event_collector.track_search_request(
            query, user_id, session_id, **properties
        )
    
    async def track_search_completion(self, query: str, duration: float,
                                    confidence: float, result_count: int,
                                    user_id: Optional[str] = None,
                                    session_id: Optional[str] = None,
                                    **properties):
        """Track search completion"""
        await self.event_collector.track_search_completion(
            query, duration, confidence, result_count,
            user_id, session_id, **properties
        )
    
    async def track_user_feedback(self, query: str, rating: int,
                                feedback: Optional[str] = None,
                                user_id: Optional[str] = None,
                                session_id: Optional[str] = None):
        """Track user feedback"""
        await self.event_collector.track_user_feedback(
            query, rating, feedback, user_id, session_id
        )
    
    async def track_api_call(self, endpoint: str, method: str, status_code: int,
                           duration: float, user_id: Optional[str] = None,
                           **properties):
        """Track API call"""
        await self.event_collector.track_api_call(
            endpoint, method, status_code, duration, user_id, **properties
        )
    
    async def get_search_analytics(self, time_range: TimeRange = TimeRange.DAY) -> Dict[str, Any]:
        """Get search analytics dashboard"""
        cache_key = f"search_analytics_{time_range.value}"
        
        # Check cache first
        cached_data = self.dashboard_cache.get(cache_key)
        if cached_data and (datetime.now() - cached_data['timestamp']).seconds < self.cache_ttl:
            ANALYTICS_CACHE_HITS.inc()
            return cached_data['data']
        
        # Calculate metrics
        metrics = await self.metrics_calculator.calculate_search_metrics(time_range)
        
        # Create dashboard data
        dashboard = {
            'overview': {
                'total_searches': metrics['total_searches'],
                'completed_searches': metrics['completed_searches'],
                'success_rate': metrics['success_rate'],
                'average_response_time': metrics['average_response_time'],
                'average_confidence': metrics['average_confidence']
            },
            'trends': {
                'hourly_distribution': dict(metrics['hourly_distribution']),
                'query_types': dict(metrics['query_types'])
            },
            'time_range': time_range.value,
            'last_updated': datetime.now().isoformat()
        }
        
        # Cache the result
        self.dashboard_cache[cache_key] = {
            'data': dashboard,
            'timestamp': datetime.now()
        }
        
        return dashboard
    
    async def get_user_analytics(self, time_range: TimeRange = TimeRange.DAY,
                               user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get user behavior analytics"""
        metrics = await self.metrics_calculator.calculate_user_metrics(time_range, user_id)
        
        return {
            'user_metrics': {
                'unique_users': metrics['unique_users'],
                'total_sessions': metrics['total_sessions'],
                'average_searches_per_user': (
                    sum(metrics['searches_per_user'].values()) / 
                    max(1, metrics['unique_users'])
                )
            },
            'engagement': {
                'popular_queries': dict(metrics['popular_queries'].most_common(10)),
                'user_distribution': dict(metrics['searches_per_user'])
            },
            'time_range': time_range.value,
            'last_updated': datetime.now().isoformat()
        }
    
    async def get_performance_analytics(self, time_range: TimeRange = TimeRange.DAY) -> Dict[str, Any]:
        """Get system performance analytics"""
        metrics = await self.metrics_calculator.calculate_performance_metrics(time_range)
        
        return {
            'performance_metrics': {
                'average_response_time': metrics.get('average_response_time', 0),
                'p95_response_time': metrics.get('p95_response_time', 0),
                'total_requests': len(metrics.get('api_response_times', [])),
                'error_rate': self._calculate_error_rate(metrics)
            },
            'endpoint_stats': {
                'usage_distribution': dict(metrics['endpoint_usage']),
                'status_codes': dict(metrics['status_code_distribution']),
                'error_breakdown': dict(metrics['error_rates'])
            },
            'time_range': time_range.value,
            'last_updated': datetime.now().isoformat()
        }
    
    def _calculate_error_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall error rate"""
        total_requests = sum(metrics['status_code_distribution'].values())
        error_requests = sum(
            count for status, count in metrics['status_code_distribution'].items()
            if status >= 400
        )
        
        return error_requests / max(1, total_requests)
    
    async def generate_report(self, report_type: str = "comprehensive",
                            time_range: TimeRange = TimeRange.DAY) -> Dict[str, Any]:
        """Generate comprehensive analytics report"""
        report = {
            'report_type': report_type,
            'time_range': time_range.value,
            'generated_at': datetime.now().isoformat(),
            'sections': {}
        }
        
        if report_type in ["comprehensive", "search"]:
            report['sections']['search_analytics'] = await self.get_search_analytics(time_range)
        
        if report_type in ["comprehensive", "users"]:
            report['sections']['user_analytics'] = await self.get_user_analytics(time_range)
        
        if report_type in ["comprehensive", "performance"]:
            report['sections']['performance_analytics'] = await self.get_performance_analytics(time_range)
        
        return report
    
    async def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time system metrics"""
        return {
            'active_searches': len(getattr(self, 'active_searches', {})),
            'events_in_buffer': len(self.event_collector.event_buffer),
            'cache_hit_rate': 0.85,  # This would be calculated from actual metrics
            'system_load': 0.65,    # This would come from system monitoring
            'timestamp': datetime.now().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on analytics service"""
        health_status = {
            'healthy': True,
            'timestamp': datetime.now().isoformat(),
            'components': {},
            'metrics': {}
        }
        
        try:
            # Check database connection
            db_health = await self.db_manager.health_check()
            health_status['components']['database'] = {
                'healthy': db_health.get('healthy', False)
            }
            
            # Check Redis connection
            redis_health = await self.redis_manager.health_check()
            health_status['components']['redis'] = {
                'healthy': redis_health.get('healthy', False)
            }
            
            # Check event collector
            health_status['components']['event_collector'] = {
                'healthy': True,
                'buffer_size': len(self.event_collector.event_buffer)
            }
            
            # Add metrics
            health_status['metrics'] = await self.get_real_time_metrics()
            
            # Overall health
            component_health = [
                comp.get('healthy', False) 
                for comp in health_status['components'].values()
            ]
            health_status['healthy'] = all(component_health)
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['error'] = str(e)
            logger.error(f"Analytics service health check failed: {e}")
        
        return health_status

# Export main classes and functions
__all__ = [
    'AnalyticsService',
    'EventCollector',
    'MetricsCalculator',
    'AnalyticsEvent',
    'AnalyticsQuery',
    'MetricResult',
    'DashboardData',
    'EventType',
    'TimeRange',
    'MetricType'
]
