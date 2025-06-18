# app/services/search_service.py - Search Service
"""
Comprehensive search service that orchestrates LangGraph workflows,
manages search requests, and provides high-level search functionality.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from enum import Enum
import json
import hashlib

# Pydantic models
from pydantic import BaseModel, Field, validator

# Core application imports
from app.langgraph.workflows.workflow_manager import (
    WorkflowManager, WorkflowType, OptimizationLevel
)
from app.langgraph.state.search_state import SearchState, ProcessingStage
from app.core.logging import get_performance_logger, LogExecutionTime

# Cache and database
from app.cache.redis_manager import RedisManager
from app.database.connection import DatabaseManager

# Performance monitoring
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)
performance_logger = get_performance_logger()

# Metrics
SEARCH_REQUESTS = Counter('search_requests_total', 'Total search requests', ['query_type', 'user_tier'])
SEARCH_DURATION = Histogram('search_duration_seconds', 'Search request duration')
SEARCH_QUALITY_SCORE = Histogram('search_quality_score', 'Search quality scores')
CACHE_HIT_RATE = Gauge('search_cache_hit_rate', 'Search cache hit rate')
ACTIVE_SEARCHES = Gauge('active_searches', 'Currently active search requests')

class QueryType(str, Enum):
    """Types of search queries"""
    FACTUAL = "factual"
    RESEARCH = "research"
    COMPARISON = "comparison"
    DEFINITION = "definition"
    HOW_TO = "how_to"
    NEWS = "news"
    ACADEMIC = "academic"
    CREATIVE = "creative"
    CODE = "code"
    UNKNOWN = "unknown"

class SearchComplexity(str, Enum):
    """Search complexity levels"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"

class SearchRequest(BaseModel):
    """Search request model"""
    query: str = Field(..., min_length=1, max_length=1000)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=50)
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    enable_streaming: bool = False
    include_sources: bool = True
    include_analytics: bool = False
    custom_parameters: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError('Query cannot be empty')
        return v.strip()

class SearchResult(BaseModel):
    """Search result model"""
    query: str
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    query_type: QueryType
    complexity: SearchComplexity
    processing_time_ms: int
    workflow_path: List[str] = Field(default_factory=list)
    quality_metrics: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    request_id: str
    timestamp: datetime

class SearchResponse(BaseModel):
    """Complete search response"""
    result: SearchResult
    cached: bool = False
    cache_key: Optional[str] = None
    usage_metrics: Dict[str, Any] = Field(default_factory=dict)
    cost_breakdown: Dict[str, float] = Field(default_factory=dict)
    debug_info: Optional[Dict[str, Any]] = None

class QueryClassifier:
    """Classifies queries to determine appropriate processing strategy"""
    
    # Keywords for different query types
    TYPE_KEYWORDS = {
        QueryType.FACTUAL: ['what is', 'who is', 'when did', 'where is', 'fact', 'information'],
        QueryType.RESEARCH: ['research', 'analyze', 'study', 'investigate', 'comprehensive'],
        QueryType.COMPARISON: ['vs', 'versus', 'compare', 'difference', 'better', 'best'],
        QueryType.DEFINITION: ['define', 'definition', 'meaning', 'what does', 'explain'],
        QueryType.HOW_TO: ['how to', 'how do', 'tutorial', 'guide', 'steps', 'instructions'],
        QueryType.NEWS: ['news', 'latest', 'recent', 'breaking', 'current events'],
        QueryType.ACADEMIC: ['academic', 'scholarly', 'journal', 'peer reviewed', 'citation'],
        QueryType.CREATIVE: ['creative', 'ideas', 'brainstorm', 'inspiration', 'examples'],
        QueryType.CODE: ['code', 'programming', 'function', 'algorithm', 'debug', 'syntax']
    }
    
    @classmethod
    def classify_query(cls, query: str) -> QueryType:
        """Classify query type based on content analysis"""
        query_lower = query.lower()
        
        # Count matches for each type
        type_scores = {}
        for query_type, keywords in cls.TYPE_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                type_scores[query_type] = score
        
        # Return type with highest score
        if type_scores:
            return max(type_scores.items(), key=lambda x: x[1])[0]
        
        return QueryType.UNKNOWN
    
    @classmethod
    def assess_complexity(cls, query: str) -> SearchComplexity:
        """Assess query complexity"""
        query_lower = query.lower()
        
        # Simple complexity indicators
        simple_indicators = ['what is', 'who is', 'when', 'where']
        if any(indicator in query_lower for indicator in simple_indicators):
            return SearchComplexity.SIMPLE
        
        # Complex indicators
        complex_indicators = ['analyze', 'comprehensive', 'research', 'compare multiple', 'detailed analysis']
        if any(indicator in query_lower for indicator in complex_indicators):
            return SearchComplexity.COMPLEX
        
        # Expert indicators
        expert_indicators = ['academic research', 'peer reviewed', 'methodology', 'statistical analysis']
        if any(indicator in query_lower for indicator in expert_indicators):
            return SearchComplexity.EXPERT
        
        # Default to moderate
        return SearchComplexity.MODERATE

class SearchCache:
    """Search result caching with intelligent cache key generation"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.cache_namespace = "search_results"
        self.default_ttl = 3600  # 1 hour
    
    def generate_cache_key(self, request: SearchRequest) -> str:
        """Generate cache key for search request"""
        # Create deterministic key from request parameters
        key_data = {
            'query': request.query.lower().strip(),
            'max_results': request.max_results,
            'optimization_level': request.optimization_level.value,
            'custom_parameters': sorted(request.custom_parameters.items())
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def get_cached_result(self, request: SearchRequest) -> Optional[SearchResult]:
        """Get cached search result"""
        cache_key = self.generate_cache_key(request)
        
        try:
            cached_data = await self.redis_manager.get(
                cache_key, 
                namespace=self.cache_namespace
            )
            
            if cached_data:
                # Update cache hit metrics
                CACHE_HIT_RATE.set(1.0)
                return SearchResult(**cached_data)
                
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        
        # Update cache miss metrics
        CACHE_HIT_RATE.set(0.0)
        return None
    
    async def cache_result(self, request: SearchRequest, result: SearchResult, 
                          ttl: Optional[int] = None) -> bool:
        """Cache search result"""
        cache_key = self.generate_cache_key(request)
        ttl = ttl or self.default_ttl
        
        try:
            await self.redis_manager.set(
                cache_key,
                result.dict(),
                ttl=ttl,
                namespace=self.cache_namespace
            )
            return True
            
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")
            return False
    
    async def invalidate_cache(self, query_pattern: str) -> int:
        """Invalidate cached results matching pattern"""
        try:
            return await self.redis_manager.clear_namespace(self.cache_namespace)
        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            return 0

class SearchService:
    """Main search service orchestrating all search functionality"""
    
    def __init__(self, workflow: WorkflowManager, 
                 db_manager: DatabaseManager,
                 redis_manager: RedisManager):
        self.workflow_manager = workflow
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.cache = SearchCache(redis_manager)
        self.classifier = QueryClassifier()
        
        # Performance tracking
        self.active_searches: Dict[str, datetime] = {}
        self.search_stats = {
            'total_searches': 0,
            'cache_hits': 0,
            'average_response_time': 0.0
        }
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute search request with full pipeline"""
        request_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(request.query) % 10000}"
        
        # Record active search
        self.active_searches[request_id] = datetime.now()
        ACTIVE_SEARCHES.inc()
        
        try:
            with LogExecutionTime(f"search_request", logger, request_id=request_id):
                # Check cache first
                cached_result = await self.cache.get_cached_result(request)
                if cached_result:
                    self.search_stats['cache_hits'] += 1
                    logger.info(f"Cache hit for query: {request.query[:50]}...")
                    
                    return SearchResponse(
                        result=cached_result,
                        cached=True,
                        cache_key=self.cache.generate_cache_key(request)
                    )
                
                # Classify query
                query_type = self.classifier.classify_query(request.query)
                complexity = self.classifier.assess_complexity(request.query)
                
                # Determine workflow type
                workflow_type = self._determine_workflow_type(query_type, complexity)
                
                # Prepare workflow input
                workflow_input = self._prepare_workflow_input(request, query_type, complexity)
                
                # Execute workflow
                start_time = datetime.now()
                workflow_result = await self.workflow_manager.execute_workflow(
                    workflow_type,
                    workflow_input,
                    request.custom_parameters
                )
                
                processing_time = (datetime.now() - start_time).total_seconds()
                
                # Build search result
                result = self._build_search_result(
                    request,
                    workflow_result,
                    query_type,
                    complexity,
                    processing_time,
                    request_id
                )
                
                # Cache result
                await self.cache.cache_result(request, result)
                
                # Record metrics
                self._record_search_metrics(request, result, processing_time)
                
                # Store search record (if needed)
                await self._store_search_record(request, result)
                
                return SearchResponse(
                    result=result,
                    cached=False,
                    usage_metrics=self._calculate_usage_metrics(workflow_result),
                    cost_breakdown=self._calculate_cost_breakdown(workflow_result)
                )
                
        except Exception as e:
            logger.error(f"Search request failed: {e}")
            raise
        
        finally:
            # Clean up active search tracking
            if request_id in self.active_searches:
                del self.active_searches[request_id]
            ACTIVE_SEARCHES.dec()
    
    def _determine_workflow_type(self, query_type: QueryType, 
                                complexity: SearchComplexity) -> WorkflowType:
        """Determine appropriate workflow type based on query characteristics"""
        
        if complexity == SearchComplexity.SIMPLE:
            return WorkflowType.SIMPLE
        
        if query_type in [QueryType.RESEARCH, QueryType.ACADEMIC]:
            return WorkflowType.RESEARCH
        
        if complexity == SearchComplexity.COMPLEX:
            return WorkflowType.ADAPTIVE
        
        if query_type in [QueryType.COMPARISON, QueryType.ANALYSIS]:
            return WorkflowType.ITERATIVE
        
        # Default to adaptive for most cases
        return WorkflowType.ADAPTIVE
    
    def _prepare_workflow_input(self, request: SearchRequest, 
                               query_type: QueryType,
                               complexity: SearchComplexity) -> Dict[str, Any]:
        """Prepare input data for workflow execution"""
        return {
            'query': request.query,
            'user_id': request.user_id,
            'session_id': request.session_id,
            'max_results': request.max_results,
            'query_type': query_type.value,
            'complexity': complexity.value,
            'optimization_level': request.optimization_level.value,
            'include_sources': request.include_sources,
            'enable_streaming': request.enable_streaming,
            'timestamp': datetime.now().isoformat()
        }
    
    def _build_search_result(self, request: SearchRequest,
                           workflow_result: Dict[str, Any],
                           query_type: QueryType,
                           complexity: SearchComplexity,
                           processing_time: float,
                           request_id: str) -> SearchResult:
        """Build structured search result from workflow output"""
        
        # Extract data from workflow result
        answer = workflow_result.get('final_response', {}).get('answer', 'No answer generated')
        sources = workflow_result.get('final_response', {}).get('sources', [])
        confidence = workflow_result.get('confidence_score', 0.5)
        workflow_path = workflow_result.get('processing_path', [])
        quality_metrics = workflow_result.get('quality_metrics', {})
        
        return SearchResult(
            query=request.query,
            answer=answer,
            sources=sources,
            confidence_score=confidence,
            query_type=query_type,
            complexity=complexity,
            processing_time_ms=int(processing_time * 1000),
            workflow_path=workflow_path,
            quality_metrics=quality_metrics,
            metadata={
                'workflow_result': workflow_result,
                'optimization_level': request.optimization_level.value,
                'custom_parameters': request.custom_parameters
            },
            request_id=request_id,
            timestamp=datetime.now()
        )
    
    def _record_search_metrics(self, request: SearchRequest, 
                             result: SearchResult, 
                             processing_time: float):
        """Record search metrics for monitoring"""
        
        # Update counters
        SEARCH_REQUESTS.labels(
            query_type=result.query_type.value,
            user_tier='unknown'  # Would be determined from user data
        ).inc()
        
        # Record timing
        SEARCH_DURATION.observe(processing_time)
        
        # Record quality
        SEARCH_QUALITY_SCORE.observe(result.confidence_score)
        
        # Update internal stats
        self.search_stats['total_searches'] += 1
        
        # Update rolling average response time
        current_avg = self.search_stats['average_response_time']
        total = self.search_stats['total_searches']
        self.search_stats['average_response_time'] = (
            (current_avg * (total - 1) + processing_time) / total
        )
        
        # Log performance metrics
        performance_logger.log_search_performance(
            query=request.query,
            duration=processing_time,
            result_count=len(result.sources),
            confidence=result.confidence_score,
            workflow_path=' -> '.join(result.workflow_path),
            query_type=result.query_type.value,
            complexity=result.complexity.value
        )
    
    async def _store_search_record(self, request: SearchRequest, result: SearchResult):
        """Store search record in database for analytics"""
        try:
            # This would insert into a searches table
            # For now, just log the search
            logger.info(f"Search completed: {result.request_id} - {request.query[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to store search record: {e}")
    
    def _calculate_usage_metrics(self, workflow_result: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate usage metrics from workflow result"""
        return {
            'search_engines_used': len(workflow_result.get('search_results', [])),
            'urls_processed': len(workflow_result.get('content_data', [])),
            'llm_calls': workflow_result.get('agent_outputs', {}).get('total_calls', 0),
            'cache_hits': workflow_result.get('cache_hit', 0),
            'processing_stages': len(workflow_result.get('processing_path', []))
        }
    
    def _calculate_cost_breakdown(self, workflow_result: Dict[str, Any]) -> Dict[str, float]:
        """Calculate cost breakdown from workflow result"""
        return {
            'search_api_cost': workflow_result.get('api_costs', {}).get('search', 0.0),
            'llm_cost': workflow_result.get('api_costs', {}).get('llm', 0.0),
            'content_fetch_cost': workflow_result.get('api_costs', {}).get('content', 0.0),
            'total_cost': workflow_result.get('total_cost', 0.0)
        }
    
    async def get_search_suggestions(self, partial_query: str, 
                                   limit: int = 5) -> List[str]:
        """Get search suggestions based on partial query"""
        # This would typically query a suggestions database or API
        # For now, return some basic suggestions
        suggestions = [
            f"{partial_query} definition",
            f"{partial_query} examples",
            f"how to {partial_query}",
            f"{partial_query} tutorial",
            f"best {partial_query}"
        ]
        
        return suggestions[:limit]
    
    async def get_search_analytics(self, user_id: Optional[str] = None,
                                 time_range: Optional[int] = 24) -> Dict[str, Any]:
        """Get search analytics for user or system"""
        # This would query analytics from database
        # For now, return current stats
        return {
            'total_searches': self.search_stats['total_searches'],
            'cache_hit_rate': (
                self.search_stats['cache_hits'] / 
                max(1, self.search_stats['total_searches'])
            ),
            'average_response_time': self.search_stats['average_response_time'],
            'active_searches': len(self.active_searches),
            'time_range_hours': time_range
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on search service"""
        health_status = {
            'healthy': True,
            'timestamp': datetime.now().isoformat(),
            'components': {},
            'metrics': {}
        }
        
        try:
            # Check workflow manager
            workflow_health = await self.workflow_manager.health_check()
            health_status['components']['workflow_manager'] = {
                'healthy': workflow_health.get('healthy', False)
            }
            
            # Check cache
            cache_health = await self.redis_manager.health_check()
            health_status['components']['cache'] = {
                'healthy': cache_health.get('healthy', False)
            }
            
            # Check database
            db_health = await self.db_manager.health_check()
            health_status['components']['database'] = {
                'healthy': db_health.get('healthy', False)
            }
            
            # Check service stats
            health_status['metrics'] = {
                'total_searches': self.search_stats['total_searches'],
                'active_searches': len(self.active_searches),
                'average_response_time': self.search_stats['average_response_time'],
                'cache_hit_rate': (
                    self.search_stats['cache_hits'] / 
                    max(1, self.search_stats['total_searches'])
                )
            }
            
            # Overall health
            component_health = [
                comp.get('healthy', False) 
                for comp in health_status['components'].values()
            ]
            health_status['healthy'] = all(component_health)
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['error'] = str(e)
            logger.error(f"Search service health check failed: {e}")
        
        return health_status

# Export main classes and functions
__all__ = [
    'SearchService',
    'SearchRequest',
    'SearchResult',
    'SearchResponse',
    'QueryType',
    'SearchComplexity',
    'QueryClassifier',
    'SearchCache'
]
