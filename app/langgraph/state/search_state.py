# app/langgraph/state/search_state.py
from typing import TypedDict, List, Dict, Optional, Any, Literal
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

class QueryType(str, Enum):
    SIMPLE_FACTUAL = "simple_factual"
    COMPLEX_RESEARCH = "complex_research"
    REAL_TIME_NEWS = "real_time_news"
    COMPARISON = "comparison"
    PROCEDURAL = "procedural"
    OPINION_BASED = "opinion_based"

class ProcessingStage(str, Enum):
    INITIALIZED = "initialized"
    CLASSIFIED = "classified"
    CACHED_CHECK = "cached_check"
    QUERY_ENHANCED = "query_enhanced"
    SEARCH_EXECUTED = "search_executed"
    CONTENT_FETCHED = "content_fetched"
    ANALYSIS_COMPLETED = "analysis_completed"
    VALIDATED = "validated"
    FORMATTED = "formatted"

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    source_engine: str
    relevance_score: float
    timestamp: datetime
    metadata: Dict[str, Any] = {}

class ContentData(BaseModel):
    url: str
    title: str
    content: str
    word_count: int
    language: str
    extracted_entities: List[str] = []
    summary: Optional[str] = None
    sentiment_score: Optional[float] = None

class AnalysisResult(BaseModel):
    summary: str
    key_facts: List[str]
    confidence_score: float
    sentiment: Dict[str, float]
    entities: List[str]
    topics: List[str]
    source_credibility: Dict[str, float]

class SearchState(TypedDict):
    # Core query data
    query: str
    query_id: str
    user_id: Optional[str]
    session_id: Optional[str]
    
    # Classification & routing
    query_type: Optional[QueryType]
    query_intent: Optional[str]
    query_complexity: float
    
    # Enhanced queries
    original_query: str
    enhanced_queries: List[str]
    semantic_variants: List[str]
    
    # Search results
    search_results: List[SearchResult]
    search_metadata: Dict[str, Any]
    
    # Content data
    content_data: List[ContentData]
    content_metadata: Dict[str, Any]
    
    # Analysis results
    analysis_result: Optional[AnalysisResult]
    fact_check_results: Dict[str, Any]
    
    # Processing metadata
    processing_stage: ProcessingStage
    processing_path: List[str]
    agent_outputs: Dict[str, Any]
    
    # Performance & quality
    confidence_score: float
    quality_metrics: Dict[str, float]
    processing_times: Dict[str, float]
    
    # Caching & optimization
    cache_hit: bool
    cache_key: Optional[str]
    
    # Cost tracking
    api_costs: Dict[str, float]
    total_cost: float
    
    # Error handling
    errors: List[Dict[str, Any]]
    retry_count: int
    
    # Response data
    final_response: Optional[Dict[str, Any]]
    
    # Debugging & monitoring
    debug_info: Dict[str, Any]
    trace_id: str
