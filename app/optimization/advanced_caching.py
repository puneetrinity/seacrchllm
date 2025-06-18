# app/optimization/advanced_caching.py - Production-Grade Caching System

import asyncio
import hashlib
import json
import pickle
import zlib
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
from contextlib import asynccontextmanager

class CacheLevel(str, Enum):
    MEMORY = "memory"           # In-process memory cache
    REDIS = "redis"            # Redis distributed cache  
    SEMANTIC = "semantic"      # Semantic similarity cache
    PERSISTENT = "persistent"  # Long-term storage cache

class CacheStrategy(str, Enum):
    LRU = "lru"                # Least Recently Used
    LFU = "lfu"                # Least Frequently Used  
    TTL = "ttl"                # Time To Live
    ADAPTIVE = "adaptive"      # Adaptive based on usage patterns
    SEMANTIC = "semantic"      # Semantic similarity matching

@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: datetime
    accessed_at: datetime
    access_count: int
    ttl_seconds: Optional[int]
    metadata: Dict[str, Any]
    compressed: bool = False
    
    def is_expired(self) -> bool:
        if not self.ttl_seconds:
            return False
        return datetime.now() > self.created_at + timedelta(seconds=self.ttl_seconds)
    
    def update_access(self):
        self.accessed_at = datetime.now()
        self.access_count += 1

class AdvancedCacheManager:
    """Production-grade multi-level caching system"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        # Multi-level cache storage
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_url = redis_url
        
        # Cache configuration
        self.config = {
            "memory_max_size": 1000,
            "memory_ttl_default": 300,      # 5 minutes
            "redis_ttl_default": 3600,      # 1 hour
            "semantic_ttl_default": 7200,   # 2 hours
            "compression_threshold": 1024,   # Compress if > 1KB
            "semantic_similarity_threshold": 0.85
        }
        
        # Performance tracking
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "evictions": 0,
            "semantic_matches": 0
        }
        
        # Semantic cache for query similarity
        self.semantic_cache: Dict[str, List[Tuple[str, Any, float]]] = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.redis_client = redis.from_url(self.redis_url)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.redis_client:
            await self.redis_client.close()
    
    async def get(self, key: str, levels: List[CacheLevel] = None) -> Optional[Any]:
        """Get value from multi-level cache"""
        
        if levels is None:
            levels = [CacheLevel.MEMORY, CacheLevel.REDIS, CacheLevel.SEMANTIC]
        
        for level in levels:
            try:
                if level == CacheLevel.MEMORY:
                    result = await self._get_from_memory(key)
                elif level == CacheLevel.REDIS:
                    result = await self._get_from_redis(key)
                elif level == CacheLevel.SEMANTIC:
                    result = await self._get_from_semantic(key)
                else:
                    continue
                
                if result is not None:
                    self.cache_stats["hits"] += 1
                    
                    # Promote to higher cache levels
                    await self._promote_to_higher_levels(key, result, level, levels)
                    
                    return result
                    
            except Exception as e:
                # Log error but continue to next level
                print(f"Cache error at level {level}: {e}")
                continue
        
        self.cache_stats["misses"] += 1
        return None
    
    async def set(self, 
                  key: str, 
                  value: Any, 
                  ttl: Optional[int] = None,
                  levels: List[CacheLevel] = None,
                  metadata: Dict[str, Any] = None) -> bool:
        """Set value in multi-level cache"""
        
        if levels is None:
            levels = [CacheLevel.MEMORY, CacheLevel.REDIS]
        
        success = False
        
        for level in levels:
            try:
                if level == CacheLevel.MEMORY:
                    await self._set_in_memory(key, value, ttl, metadata)
                elif level == CacheLevel.REDIS:
                    await self._set_in_redis(key, value, ttl, metadata)
                elif level == CacheLevel.SEMANTIC:
                    await self._set_in_semantic(key, value, ttl, metadata)
                
                success = True
                
            except Exception as e:
                print(f"Cache write error at level {level}: {e}")
                continue
        
        if success:
            self.cache_stats["writes"] += 1
        
        return success
    
    async def _get_from_memory(self, key: str) -> Optional[Any]:
        """Get from in-memory cache"""
        
        entry = self.memory_cache.get(key)
        if not entry:
            return None
        
        if entry.is_expired():
            del self.memory_cache[key]
            return None
        
        entry.update_access()
        
        if entry.compressed:
            return pickle.loads(zlib.decompress(entry.value))
        return entry.value
    
    async def _set_in_memory(self, key: str, value: Any, ttl: Optional[int], metadata: Dict[str, Any]):
        """Set in in-memory cache with intelligent eviction"""
        
        # Check if we need to evict
        if len(self.memory_cache) >= self.config["memory_max_size"]:
            await self._evict_memory_entries()
        
        # Compress large values
        serialized_value = value
        compressed = False
        
        if isinstance(value, (dict, list)) and len(str(value)) > self.config["compression_threshold"]:
            serialized_value = zlib.compress(pickle.dumps(value))
            compressed = True
        
        entry = CacheEntry(
            key=key,
            value=serialized_value,
            created_at=datetime.now(),
            accessed_at=datetime.now(),
            access_count=1,
            ttl_seconds=ttl or self.config["memory_ttl_default"],
            metadata=metadata or {},
            compressed=compressed
        )
        
        self.memory_cache[key] = entry
    
    async def _get_from_redis(self, key: str) -> Optional[Any]:
        """Get from Redis cache"""
        
        if not self.redis_client:
            return None
        
        try:
            # Get value and metadata
            pipe = self.redis_client.pipeline()
            pipe.get(f"cache:{key}")
            pipe.hgetall(f"meta:{key}")
            
            results = await pipe.execute()
            cached_value, metadata = results
            
            if not cached_value:
                return None
            
            # Deserialize
            data = pickle.loads(cached_value)
            
            # Update access metadata
            await self.redis_client.hincrby(f"meta:{key}", "access_count", 1)
            await self.redis_client.hset(f"meta:{key}", "last_accessed", datetime.now().isoformat())
            
            return data
            
        except Exception as e:
            print(f"Redis get error: {e}")
            return None
    
    async def _set_in_redis(self, key: str, value: Any, ttl: Optional[int], metadata: Dict[str, Any]):
        """Set in Redis cache"""
        
        if not self.redis_client:
            return
        
        try:
            # Serialize value
            serialized = pickle.dumps(value)
            
            # Set value with TTL
            ttl_seconds = ttl or self.config["redis_ttl_default"]
            
            pipe = self.redis_client.pipeline()
            pipe.setex(f"cache:{key}", ttl_seconds, serialized)
            
            # Set metadata
            meta_data = {
                "created_at": datetime.now().isoformat(),
                "ttl": ttl_seconds,
                "access_count": 1,
                **(metadata or {})
            }
            
            pipe.hset(f"meta:{key}", mapping=meta_data)
            pipe.expire(f"meta:{key}", ttl_seconds)
            
            await pipe.execute()
            
        except Exception as e:
            print(f"Redis set error: {e}")
    
    async def _get_from_semantic(self, key: str) -> Optional[Any]:
        """Get from semantic similarity cache"""
        
        # Calculate semantic embedding for the key (simplified)
        key_embedding = self._calculate_embedding(key)
        
        # Search for similar queries
        for cached_key, entries in self.semantic_cache.items():
            for entry_key, entry_value, similarity in entries:
                if similarity > self.config["semantic_similarity_threshold"]:
                    # Check if still valid
                    redis_value = await self._get_from_redis(f"semantic:{entry_key}")
                    if redis_value:
                        self.cache_stats["semantic_matches"] += 1
                        return redis_value
        
        return None
    
    async def _set_in_semantic(self, key: str, value: Any, ttl: Optional[int], metadata: Dict[str, Any]):
        """Set in semantic cache"""
        
        # Calculate embedding
        embedding = self._calculate_embedding(key)
        
        # Store in Redis with semantic prefix
        await self._set_in_redis(f"semantic:{key}", value, ttl or self.config["semantic_ttl_default"], metadata)
        
        # Add to semantic index
        semantic_key = self._get_semantic_cluster(embedding)
        if semantic_key not in self.semantic_cache:
            self.semantic_cache[semantic_key] = []
        
        # Calculate similarity with existing entries
        similarity = 1.0  # Perfect match with itself
        self.semantic_cache[semantic_key].append((key, value, similarity))
        
        # Limit entries per cluster
        if len(self.semantic_cache[semantic_key]) > 10:
            self.semantic_cache[semantic_key] = self.semantic_cache[semantic_key][-10:]
    
    async def _evict_memory_entries(self):
        """Intelligent memory cache eviction"""
        
        # Remove expired entries first
        expired_keys = [
            key for key, entry in self.memory_cache.items() 
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self.memory_cache[key]
            self.cache_stats["evictions"] += 1
        
        # If still over limit, use LFU eviction
        if len(self.memory_cache) >= self.config["memory_max_size"]:
            # Sort by access count (LFU)
            sorted_entries = sorted(
                self.memory_cache.items(),
                key=lambda x: (x[1].access_count, x[1].accessed_at)
            )
            
            # Remove least frequently used entries
            entries_to_remove = len(self.memory_cache) - int(self.config["memory_max_size"] * 0.8)
            
            for key, _ in sorted_entries[:entries_to_remove]:
                del self.memory_cache[key]
                self.cache_stats["evictions"] += 1
    
    async def _promote_to_higher_levels(self, key: str, value: Any, current_level: CacheLevel, available_levels: List[CacheLevel]):
        """Promote cache entry to higher levels"""
        
        level_priority = {
            CacheLevel.MEMORY: 0,
            CacheLevel.REDIS: 1,
            CacheLevel.SEMANTIC: 2,
            CacheLevel.PERSISTENT: 3
        }
        
        current_priority = level_priority[current_level]
        
        for level in available_levels:
            if level_priority[level] < current_priority:
                try:
                    if level == CacheLevel.MEMORY:
                        await self._set_in_memory(key, value, None, {})
                    elif level == CacheLevel.REDIS:
                        await self._set_in_redis(key, value, None, {})
                except Exception as e:
                    print(f"Promotion error to {level}: {e}")
    
    def _calculate_embedding(self, text: str) -> List[float]:
        """Calculate simple embedding for semantic similarity (placeholder)"""
        # In production, use proper embeddings like OpenAI, Sentence Transformers, etc.
        # This is a simplified version for demonstration
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        hash_hex = hash_obj.hexdigest()
        
        # Convert to simple vector (for demo purposes)
        embedding = [ord(c) / 255.0 for c in hash_hex[:16]]
        return embedding
    
    def _get_semantic_cluster(self, embedding: List[float]) -> str:
        """Get semantic cluster key for grouping similar queries"""
        # Simple clustering based on first few dimensions
        cluster_id = f"cluster_{int(embedding[0] * 10)}_{int(embedding[1] * 10)}"
        return cluster_id
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = self.cache_stats["hits"] / max(1, total_requests)
        
        memory_usage = {
            "entry_count": len(self.memory_cache),
            "max_size": self.config["memory_max_size"],
            "utilization": len(self.memory_cache) / self.config["memory_max_size"]
        }
        
        # Redis stats
        redis_stats = {}
        if self.redis_client:
            try:
                redis_info = await self.redis_client.info("memory")
                redis_stats = {
                    "used_memory": redis_info.get("used_memory", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "0B"),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0)
                }
            except Exception:
                redis_stats = {"status": "unavailable"}
        
        return {
            "performance": {
                "hit_rate": hit_rate,
                "total_requests": total_requests,
                **self.cache_stats
            },
            "memory_cache": memory_usage,
            "redis_cache": redis_stats,
            "semantic_cache": {
                "cluster_count": len(self.semantic_cache),
                "total_entries": sum(len(entries) for entries in self.semantic_cache.values())
            }
        }
    
    async def optimize_cache(self):
        """Perform cache optimization"""
        
        # Memory optimization
        await self._evict_memory_entries()
        
        # Redis cleanup
        if self.redis_client:
            try:
                # Remove expired keys
                await self.redis_client.eval("""
                    for i, key in ipairs(redis.call('keys', 'cache:*')) do
                        if redis.call('ttl', key) == -1 then
                            redis.call('del', key)
                            redis.call('del', string.gsub(key, 'cache:', 'meta:'))
                        end
                    end
                """, 0)
            except Exception as e:
                print(f"Redis cleanup error: {e}")
        
        # Semantic cache optimization
        for cluster_key in list(self.semantic_cache.keys()):
            entries = self.semantic_cache[cluster_key]
            
            # Remove entries with low similarity
            filtered_entries = [
                entry for entry in entries 
                if entry[2] > self.config["semantic_similarity_threshold"] * 0.8
            ]
            
            if filtered_entries:
                self.semantic_cache[cluster_key] = filtered_entries
            else:
                del self.semantic_cache[cluster_key]

# app/optimization/performance_optimizer.py - Advanced Performance Optimization

class PerformanceOptimizer:
    """Advanced performance optimization system"""
    
    def __init__(self):
        self.optimization_strategies = {
            "query_routing": QueryRoutingOptimizer(),
            "resource_allocation": ResourceAllocationOptimizer(),
            "parallelization": ParallelizationOptimizer(),
            "caching": CachingOptimizer(),
            "cost_optimization": CostOptimizer()
        }
        
        self.performance_history = []
        self.optimization_models = {}
        
    async def optimize_search_execution(self, state: AdvancedSearchState) -> AdvancedSearchState:
        """Optimize search execution based on real-time analysis"""
        
        # Analyze current context
        optimization_context = await self._analyze_optimization_context(state)
        
        # Apply optimization strategies
        for strategy_name, optimizer in self.optimization_strategies.items():
            try:
                state = await optimizer.optimize(state, optimization_context)
                state["optimizations_applied"] = state.get("optimizations_applied", []) + [strategy_name]
            except Exception as e:
                print(f"Optimization error in {strategy_name}: {e}")
        
        return state
    
    async def _analyze_optimization_context(self, state: AdvancedSearchState) -> Dict[str, Any]:
        """Analyze context for optimization decisions"""
        
        return {
            "current_load": await self._get_system_load(),
            "cost_budget_remaining": await self._get_budget_status(),
            "cache_performance": await self._get_cache_performance(),
            "user_preferences": await self._get_user_preferences(state.get("user_id")),
            "query_patterns": await self._analyze_query_patterns(),
            "time_constraints": self._extract_time_constraints(state)
        }

class QueryRoutingOptimizer:
    """Optimizes query routing decisions"""
    
    async def optimize(self, state: AdvancedSearchState, context: Dict[str, Any]) -> AdvancedSearchState:
        """Optimize query routing based on context"""
        
        # Analyze query characteristics
        query_features = self._extract_query_features(state["query"])
        
        # Predict optimal routing strategy
        if context["current_load"] > 0.8:
            # High load - prefer cached/simple paths
            state["routing_preference"] = "fast"
            state["complexity_threshold"] = 0.3
        elif context["cost_budget_remaining"] < 0.2:
            # Low budget - cost-conscious routing
            state["routing_preference"] = "cost_efficient"
            state["max_search_engines"] = 1
        elif query_features["complexity"] > 0.8:
            # Complex query - quality-focused routing
            state["routing_preference"] = "quality"
            state["enable_all_agents"] = True
        
        return state
    
    def _extract_query_features(self, query: str) -> Dict[str, float]:
        """Extract features for routing optimization"""
        
        return {
            "complexity": len(query.split()) / 20,
            "specificity": len([w for w in query.split() if len(w) > 6]) / len(query.split()),
            "question_type": 1.0 if query.strip().endswith('?') else 0.0,
            "temporal_urgency": 1.0 if any(word in query.lower() for word in ["urgent", "latest", "now"]) else 0.0
        }

class ResourceAllocationOptimizer:
    """Optimizes resource allocation across search pipeline"""
    
    async def optimize(self, state: AdvancedSearchState, context: Dict[str, Any]) -> AdvancedSearchState:
        """Optimize resource allocation"""
        
        total_budget = state["performance_budget"]["max_time"]
        
        # Allocate time budget across stages
        if state.get("routing_preference") == "fast":
            allocation = {
                "search": 0.4,
                "content": 0.3,
                "analysis": 0.2,
                "formatting": 0.1
            }
        elif state.get("routing_preference") == "quality":
            allocation = {
                "search": 0.3,
                "content": 0.4,
                "analysis": 0.25,
                "formatting": 0.05
            }
        else:  # balanced
            allocation = {
                "search": 0.35,
                "content": 0.35,
                "analysis": 0.22,
                "formatting": 0.08
            }
        
        # Apply allocation
        state["time_allocation"] = {
            stage: total_budget * ratio 
            for stage, ratio in allocation.items()
        }
        
        return state

class ParallelizationOptimizer:
    """Optimizes parallel execution strategies"""
    
    async def optimize(self, state: AdvancedSearchState, context: Dict[str, Any]) -> AdvancedSearchState:
        """Optimize parallelization strategy"""
        
        # Determine optimal parallelization
        if context["current_load"] < 0.5:
            # Low load - aggressive parallelization
            state["parallel_search_engines"] = 3
            state["parallel_content_fetches"] = 8
            state["parallel_analysis_agents"] = 4
        elif context["current_load"] < 0.8:
            # Medium load - moderate parallelization
            state["parallel_search_engines"] = 2
            state["parallel_content_fetches"] = 5
            state["parallel_analysis_agents"] = 2
        else:
            # High load - conservative parallelization
            state["parallel_search_engines"] = 1
            state["parallel_content_fetches"] = 3
            state["parallel_analysis_agents"] = 1
        
        return state

class CachingOptimizer:
    """Optimizes caching strategies"""
    
    async def optimize(self, state: AdvancedSearchState, context: Dict[str, Any]) -> AdvancedSearchState:
        """Optimize caching strategy"""
        
        cache_performance = context["cache_performance"]
        
        if cache_performance["hit_rate"] < 0.5:
            # Low hit rate - more aggressive caching
            state["cache_strategy"] = "aggressive"
            state["cache_ttl_multiplier"] = 2.0
        elif cache_performance["hit_rate"] > 0.8:
            # High hit rate - optimize for freshness
            state["cache_strategy"] = "freshness_focused"
            state["cache_ttl_multiplier"] = 0.8
        
        # Query-specific caching
        if any(word in state["query"].lower() for word in ["latest", "current", "breaking"]):
            state["bypass_cache"] = True
        elif state.get("query_complexity", 0) < 0.3:
            state["cache_priority"] = "high"
        
        return state

class CostOptimizer:
    """Optimizes cost efficiency"""
    
    async def optimize(self, state: AdvancedSearchState, context: Dict[str, Any]) -> AdvancedSearchState:
        """Optimize for cost efficiency"""
        
        budget_remaining = context["cost_budget_remaining"]
        
        if budget_remaining < 0.1:
            # Very low budget - emergency cost saving
            state["cost_mode"] = "emergency"
            state["max_search_engines"] = 1
            state["max_content_urls"] = 2
            state["disable_expensive_agents"] = True
        elif budget_remaining < 0.3:
            # Low budget - cost conscious
            state["cost_mode"] = "conscious"
            state["max_search_engines"] = 2
            state["max_content_urls"] = 4
        
        # Estimate cost for current query
        estimated_cost = self._estimate_query_cost(state)
        state["estimated_cost"] = estimated_cost
        
        # Adjust strategy if cost too high
        if estimated_cost > budget_remaining * 100:  # 100 queries worth of budget
            state["cost_adjustment"] = "reduce_scope"
            state["quality_threshold"] = 0.6  # Lower threshold
        
        return state
    
    def _estimate_query_cost(self, state: AdvancedSearchState) -> float:
        """Estimate cost for current query configuration"""
        
        cost = 0.0
        
        # Search engine costs
        search_engines = state.get("max_search_engines", 2)
        cost += search_engines * 0.004  # Average search cost
        
        # Content fetching costs
        content_urls = state.get("max_content_urls", 6)
        cost += content_urls * 0.01  # ZenRows cost
        
        # LLM costs (estimated)
        if state.get("enable_all_agents", False):
            cost += 0.02  # Multiple LLM calls
        else:
            cost += 0.005  # Basic LLM usage
        
        return cost

# Integration with main workflow
class OptimizedSearchWorkflow(SophisticatedSearchWorkflow):
    """Search workflow with advanced optimization"""
    
    def __init__(self):
        super().__init__()
        self.performance_optimizer = PerformanceOptimizer()
        self.cache_manager = AdvancedCacheManager()
        
    async def execute_optimized_search(self, initial_state: AdvancedSearchState) -> AdvancedSearchState:
        """Execute search with advanced optimization"""
        
        # Apply performance optimizations
        optimized_state = await self.performance_optimizer.optimize_search_execution(initial_state)
        
        # Check advanced cache first
        cache_key = self._generate_cache_key(optimized_state)
        
        async with self.cache_manager:
            cached_result = await self.cache_manager.get(
                cache_key, 
                levels=[CacheLevel.MEMORY, CacheLevel.SEMANTIC, CacheLevel.REDIS]
            )
            
            if cached_result:
                optimized_state["final_response"] = cached_result
                optimized_state["cache_hit"] = True
                return optimized_state
            
            # Execute workflow
            config = {"configurable": {"thread_id": f"optimized_{hash(optimized_state['query'])}"}}
            final_state = await self.workflow.ainvoke(optimized_state, config)
            
            # Cache result with intelligent TTL
            cache_ttl = self._calculate_intelligent_ttl(final_state)
            await self.cache_manager.set(
                cache_key,
                final_state["final_response"],
                ttl=cache_ttl,
                levels=[CacheLevel.MEMORY, CacheLevel.REDIS, CacheLevel.SEMANTIC],
                metadata={
                    "query_type": final_state.get("query_type"),
                    "confidence": final_state.get("confidence_score"),
                    "cost": final_state.get("total_cost")
                }
            )
            
        return final_state
    
    def _generate_cache_key(self, state: AdvancedSearchState) -> str:
        """Generate intelligent cache key"""
        
        # Include relevant state factors in cache key
        key_components = [
            state["query"],
            state.get("workflow_complexity", "unknown"),
            state.get("optimization_level", "balanced"),
            str(state.get("max_results", 10))
        ]
        
        # Create hash of components
        key_string = "|".join(str(comp) for comp in key_components)
        cache_key = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return f"search:{cache_key}"
    
    def _calculate_intelligent_ttl(self, state: AdvancedSearchState) -> int:
        """Calculate intelligent TTL based on query characteristics"""
        
        base_ttl = 3600  # 1 hour default
        
        # Adjust based on query type
        query_type = state.get("query_type", "unknown")
        if "news" in query_type.lower() or "current" in state["query"].lower():
            base_ttl = 900  # 15 minutes for news
        elif "factual" in query_type.lower():
            base_ttl = 7200  # 2 hours for facts
        
        # Adjust based on confidence
        confidence = state.get("confidence_score", 0.5)
        if confidence > 0.9:
            base_ttl = int(base_ttl * 1.5)  # Cache longer for high confidence
        elif confidence < 0.6:
            base_ttl = int(base_ttl * 0.5)  # Cache shorter for low confidence
        
        return base_ttl
