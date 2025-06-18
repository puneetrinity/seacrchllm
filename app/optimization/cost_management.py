# app/optimization/cost_management.py - Advanced Cost Optimization System

import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class CostCategory(str, Enum):
    SEARCH_ENGINES = "search_engines"
    CONTENT_FETCHING = "content_fetching"
    LLM_PROCESSING = "llm_processing"
    VECTOR_DATABASE = "vector_database"
    CACHING = "caching"
    INFRASTRUCTURE = "infrastructure"

class BudgetPeriod(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"

@dataclass
class CostEntry:
    timestamp: datetime
    category: CostCategory
    subcategory: str
    amount: Decimal
    currency: str
    tenant_id: Optional[str]
    user_id: Optional[str]
    request_id: str
    metadata: Dict[str, Any]

@dataclass
class BudgetAlert:
    alert_id: str
    tenant_id: Optional[str]
    category: CostCategory
    threshold_percentage: float
    current_percentage: float
    period: BudgetPeriod
    amount_spent: Decimal
    budget_limit: Decimal
    triggered_at: datetime
    severity: str  # info, warning, critical

class SmartCostOptimizer:
    """Intelligent cost optimization system"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.cost_history: List[CostEntry] = []
        self.budgets: Dict[str, Dict[str, Any]] = {}
        self.optimization_rules: Dict[str, Any] = {}
        self.cost_predictions: Dict[str, float] = {}
        
        # Cost rates (per operation)
        self.base_rates = {
            CostCategory.SEARCH_ENGINES: {
                "brave": 0.005,
                "serpapi": 0.003,
                "bing": 0.004  # deprecated but kept for migration
            },
            CostCategory.CONTENT_FETCHING: {
                "zenrows": 0.010,
                "basic_fetch": 0.001
            },
            CostCategory.LLM_PROCESSING: {
                "ollama_local": 0.0,  # Free local processing
                "openai_gpt4": 0.030,
                "claude": 0.025
            },
            CostCategory.VECTOR_DATABASE: {
                "pinecone": 0.002,
                "weaviate": 0.001,
                "chromadb": 0.0  # Free local
            }
        }
        
        # Initialize optimization rules
        self._initialize_optimization_rules()
    
    def _initialize_optimization_rules(self):
        """Initialize cost optimization rules"""
        
        self.optimization_rules = {
            "high_cost_query_detection": {
                "enabled": True,
                "threshold": 0.10,  # $0.10 per query
                "action": "optimize_strategy"
            },
            "budget_approaching": {
                "enabled": True,
                "warning_threshold": 0.8,  # 80% of budget
                "critical_threshold": 0.95,  # 95% of budget
                "actions": ["reduce_quality", "limit_sources", "increase_caching"]
            },
            "peak_hours_optimization": {
                "enabled": True,
                "peak_hours": [(9, 17)],  # 9 AM to 5 PM
                "optimization": "reduce_latency_over_cost"
            },
            "tenant_specific_limits": {
                "enabled": True,
                "default_daily_limit": 50.0,
                "default_monthly_limit": 1000.0
            }
        }
    
    async def track_cost(self, 
                        category: CostCategory,
                        subcategory: str,
                        amount: float,
                        tenant_id: Optional[str] = None,
                        user_id: Optional[str] = None,
                        request_id: str = None,
                        metadata: Dict[str, Any] = None) -> str:
        """Track a cost entry"""
        
        cost_entry = CostEntry(
            timestamp=datetime.now(),
            category=category,
            subcategory=subcategory,
            amount=Decimal(str(amount)),
            currency="USD",
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id or str(uuid.uuid4()),
            metadata=metadata or {}
        )
        
        # Store in memory and Redis
        self.cost_history.append(cost_entry)
        
        if self.redis_client:
            await self._store_cost_in_redis(cost_entry)
        
        # Check budget alerts
        await self._check_budget_alerts(cost_entry)
        
        # Apply real-time optimizations
        optimization_suggestions = await self._generate_optimization_suggestions(cost_entry)
        
        logger.info(f"Cost tracked: {category.value}/{subcategory} = ${amount}")
        
        return cost_entry.request_id
    
    async def estimate_query_cost(self, 
                                query: str,
                                search_strategy: Dict[str, Any],
                                tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Estimate cost for a search query before execution"""
        
        estimated_costs = {}
        total_estimate = 0.0
        
        # Search engine costs
        search_engines = search_strategy.get("search_engines", ["brave", "serpapi"])
        for engine in search_engines:
            if engine in self.base_rates[CostCategory.SEARCH_ENGINES]:
                cost = self.base_rates[CostCategory.SEARCH_ENGINES][engine]
                estimated_costs[f"search_{engine}"] = cost
                total_estimate += cost
        
        # Content fetching costs
        max_urls = search_strategy.get("max_content_urls", 6)
        content_cost = max_urls * self.base_rates[CostCategory.CONTENT_FETCHING]["zenrows"]
        estimated_costs["content_fetching"] = content_cost
        total_estimate += content_cost
        
        # LLM processing costs
        llm_calls = search_strategy.get("llm_calls", 3)
        llm_provider = search_strategy.get("llm_provider", "ollama_local")
        if llm_provider in self.base_rates[CostCategory.LLM_PROCESSING]:
            llm_cost = llm_calls * self.base_rates[CostCategory.LLM_PROCESSING][llm_provider]
            estimated_costs["llm_processing"] = llm_cost
            total_estimate += llm_cost
        
        # Vector database costs
        if search_strategy.get("use_vector_db", False):
            vector_provider = search_strategy.get("vector_provider", "chromadb")
            if vector_provider in self.base_rates[CostCategory.VECTOR_DATABASE]:
                vector_cost = self.base_rates[CostCategory.VECTOR_DATABASE][vector_provider]
                estimated_costs["vector_database"] = vector_cost
                total_estimate += vector_cost
        
        # Apply tenant-specific adjustments
        if tenant_id:
            tenant_multiplier = await self._get_tenant_cost_multiplier(tenant_id)
            total_estimate *= tenant_multiplier
        
        return {
            "total_estimated_cost": round(total_estimate, 4),
            "cost_breakdown": estimated_costs,
            "optimization_suggestions": await self._suggest_cost_optimizations(
                total_estimate, 
                search_strategy,
                tenant_id
            )
        }
    
    async def optimize_search_strategy(self,
                                     query: str,
                                     current_strategy: Dict[str, Any],
                                     budget_constraint: float,
                                     tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Optimize search strategy based on budget constraints"""
        
        # Estimate current cost
        current_estimate = await self.estimate_query_cost(query, current_strategy, tenant_id)
        
        if current_estimate["total_estimated_cost"] <= budget_constraint:
            return current_strategy  # No optimization needed
        
        optimized_strategy = current_strategy.copy()
        
        # Apply optimization strategies in order of impact
        optimization_steps = []
        
        # 1. Reduce search engines
        if len(optimized_strategy.get("search_engines", [])) > 1:
            # Keep only the most cost-effective engine
            best_engine = self._get_most_cost_effective_engine()
            optimized_strategy["search_engines"] = [best_engine]
            optimization_steps.append("reduced_search_engines")
        
        # 2. Reduce content URLs
        if optimized_strategy.get("max_content_urls", 6) > 3:
            optimized_strategy["max_content_urls"] = 3
            optimization_steps.append("reduced_content_urls")
        
        # 3. Use local LLM if available
        if optimized_strategy.get("llm_provider") != "ollama_local":
            optimized_strategy["llm_provider"] = "ollama_local"
            optimization_steps.append("switched_to_local_llm")
        
        # 4. Reduce LLM calls
        if optimized_strategy.get("llm_calls", 3) > 1:
            optimized_strategy["llm_calls"] = 1
            optimization_steps.append("reduced_llm_calls")
        
        # 5. Disable vector database if enabled
        if optimized_strategy.get("use_vector_db", False):
            optimized_strategy["use_vector_db"] = False
            optimization_steps.append("disabled_vector_db")
        
        # Re-estimate cost
        new_estimate = await self.estimate_query_cost(query, optimized_strategy, tenant_id)
        
        return {
            "optimized_strategy": optimized_strategy,
            "original_cost": current_estimate["total_estimated_cost"],
            "optimized_cost": new_estimate["total_estimated_cost"],
            "cost_savings": current_estimate["total_estimated_cost"] - new_estimate["total_estimated_cost"],
            "optimization_steps": optimization_steps,
            "meets_budget": new_estimate["total_estimated_cost"] <= budget_constraint
        }
    
    async def get_cost_analytics(self,
                               tenant_id: Optional[str] = None,
                               period: BudgetPeriod = BudgetPeriod.DAILY,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get comprehensive cost analytics"""
        
        # Filter costs by criteria
        filtered_costs = self._filter_costs(tenant_id, start_date, end_date)
        
        if not filtered_costs:
            return {"error": "No cost data found for specified criteria"}
        
        # Calculate analytics
        analytics = {
            "summary": await self._calculate_cost_summary(filtered_costs),
            "by_category": await self._calculate_costs_by_category(filtered_costs),
            "by_tenant": await self._calculate_costs_by_tenant(filtered_costs),
            "trends": await self._calculate_cost_trends(filtered_costs, period),
            "top_expensive_queries": await self._find_expensive_queries(filtered_costs),
            "optimization_opportunities": await self._identify_optimization_opportunities(filtered_costs),
            "budget_status": await self._get_budget_status(tenant_id, period),
            "predictions": await self._predict_future_costs(filtered_costs, period)
        }
        
        return analytics
    
    async def _suggest_cost_optimizations(self,
                                        estimated_cost: float,
                                        strategy: Dict[str, Any],
                                        tenant_id: Optional[str]) -> List[str]:
        """Suggest cost optimizations"""
        
        suggestions = []
        
        if estimated_cost > 0.05:  # High cost query
            suggestions.append("Consider using aggressive caching for similar queries")
            suggestions.append("Reduce the number of search engines if quality permits")
        
        if strategy.get("max_content_urls", 6) > 4:
            suggestions.append("Reduce max_content_urls to 4 for cost efficiency")
        
        if strategy.get("llm_provider") != "ollama_local":
            suggestions.append("Use local Ollama LLM to eliminate external LLM costs")
        
        if len(strategy.get("search_engines", [])) > 2:
            suggestions.append("Limit to 2 search engines for most queries")
        
        # Tenant-specific suggestions
        if tenant_id:
            tenant_usage = await self._get_tenant_usage_pattern(tenant_id)
            if tenant_usage.get("high_repeat_queries", False):
                suggestions.append("Enable semantic caching for this tenant")
        
        return suggestions

class MultiTenantArchitecture:
    """Multi-tenant architecture for SaaS deployment"""
    
    def __init__(self, cost_optimizer: SmartCostOptimizer):
        self.cost_optimizer = cost_optimizer
        self.tenant_configs: Dict[str, Dict[str, Any]] = {}
        self.tenant_usage_stats: Dict[str, Dict[str, Any]] = {}
        self.isolation_strategy = "namespace"  # namespace, database, schema
        
    async def create_tenant(self,
                          tenant_id: str,
                          tenant_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new tenant with isolated resources"""
        
        # Validate tenant configuration
        validated_config = await self._validate_tenant_config(tenant_config)
        
        # Set up tenant isolation
        isolation_setup = await self._setup_tenant_isolation(tenant_id, validated_config)
        
        # Initialize tenant budgets and limits
        await self._initialize_tenant_budgets(tenant_id, validated_config)
        
        # Create tenant-specific caching namespace
        await self._setup_tenant_caching(tenant_id)
        
        # Initialize usage tracking
        self.tenant_usage_stats[tenant_id] = {
            "created_at": datetime.now(),
            "total_queries": 0,
            "total_cost": 0.0,
            "last_activity": datetime.now(),
            "features_used": [],
            "performance_metrics": {}
        }
        
        self.tenant_configs[tenant_id] = validated_config
        
        logger.info(f"Tenant {tenant_id} created successfully")
        
        return {
            "tenant_id": tenant_id,
            "status": "created",
            "isolation_setup": isolation_setup,
            "configuration": validated_config
        }
    
    async def get_tenant_search_strategy(self,
                                       tenant_id: str,
                                       query: str,
                                       user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get tenant-specific search strategy"""
        
        if tenant_id not in self.tenant_configs:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        tenant_config = self.tenant_configs[tenant_id]
        
        # Base strategy from tenant configuration
        base_strategy = {
            "search_engines": tenant_config.get("allowed_search_engines", ["brave", "serpapi"]),
            "max_content_urls": tenant_config.get("max_content_urls", 6),
            "llm_provider": tenant_config.get("preferred_llm_provider", "ollama_local"),
            "llm_calls": tenant_config.get("max_llm_calls", 3),
            "use_vector_db": tenant_config.get("vector_db_enabled", True),
            "vector_provider": tenant_config.get("vector_provider", "chromadb"),
            "cache_strategy": tenant_config.get("cache_strategy", "aggressive"),
            "quality_threshold": tenant_config.get("quality_threshold", 0.7)
        }
        
        # Apply tenant-specific optimizations
        current_usage = await self._get_current_usage(tenant_id)
        budget_status = await self._get_tenant_budget_status(tenant_id)
        
        # Adjust strategy based on budget and usage
        if budget_status["remaining_percentage"] < 0.2:  # Less than 20% budget remaining
            base_strategy = await self._apply_budget_constraints(base_strategy, tenant_config)
        
        # Apply user preferences if provided
        if user_preferences:
            base_strategy = await self._apply_user_preferences(base_strategy, user_preferences)
        
        return base_strategy
    
    async def execute_tenant_search(self,
                                  tenant_id: str,
                                  query: str,
                                  user_id: Optional[str] = None,
                                  user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute search with tenant-specific configuration"""
        
        # Get tenant strategy
        search_strategy = await self.get_tenant_search_strategy(
            tenant_id, 
            query, 
            user_preferences
        )
        
        # Pre-execution cost estimation
        cost_estimate = await self.cost_optimizer.estimate_query_cost(
            query, 
            search_strategy, 
            tenant_id
        )
        
        # Check if tenant can afford the query
        budget_check = await self._check_tenant_budget(tenant_id, cost_estimate["total_estimated_cost"])
        
        if not budget_check["allowed"]:
            # Try to optimize for budget
            optimization_result = await self.cost_optimizer.optimize_search_strategy(
                query,
                search_strategy,
                budget_check["remaining_budget"],
                tenant_id
            )
            
            if optimization_result["meets_budget"]:
                search_strategy = optimization_result["optimized_strategy"]
                cost_estimate = optimization_result["optimized_cost"]
            else:
                return {
                    "error": "Insufficient budget for query",
                    "budget_status": budget_check,
                    "estimated_cost": cost_estimate["total_estimated_cost"],
                    "suggestions": optimization_result["optimization_steps"]
                }
        
        # Execute search with tenant isolation
        start_time = datetime.now()
        
        try:
            # This would integrate with your main search workflow
            search_result = await self._execute_isolated_search(
                tenant_id,
                query,
                search_strategy,
                user_id
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Track actual costs
            actual_cost = await self._calculate_actual_cost(search_result, search_strategy)
            await self.cost_optimizer.track_cost(
                category=CostCategory.SEARCH_ENGINES,
                subcategory="tenant_search",
                amount=actual_cost,
                tenant_id=tenant_id,
                user_id=user_id,
                metadata={
                    "query": query[:100],  # Truncate for privacy
                    "processing_time": processing_time,
                    "strategy_used": search_strategy
                }
            )
            
            # Update tenant usage statistics
            await self._update_tenant_usage(tenant_id, actual_cost, processing_time)
            
            return {
                "result": search_result,
                "tenant_id": tenant_id,
                "processing_time": processing_time,
                "actual_cost": actual_cost,
                "estimated_cost": cost_estimate["total_estimated_cost"],
                "strategy_used": search_strategy
            }
            
        except Exception as e:
            logger.error(f"Search execution failed for tenant {tenant_id}: {e}")
            
            # Track failed cost (partial)
            await self.cost_optimizer.track_cost(
                category=CostCategory.SEARCH_ENGINES,
                subcategory="failed_search",
                amount=cost_estimate["total_estimated_cost"] * 0.1,  # 10% of estimated
                tenant_id=tenant_id,
                user_id=user_id,
                metadata={"error": str(e), "query": query[:100]}
            )
            
            raise
    
    async def get_tenant_analytics(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive tenant analytics"""
        
        if tenant_id not in self.tenant_configs:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # Cost analytics
        cost_analytics = await self.cost_optimizer.get_cost_analytics(
            tenant_id=tenant_id,
            period=BudgetPeriod.MONTHLY
        )
        
        # Usage statistics
        usage_stats = self.tenant_usage_stats.get(tenant_id, {})
        
        # Performance metrics
        performance_metrics = await self._calculate_tenant_performance_metrics(tenant_id)
        
        # Feature usage
        feature_usage = await self._analyze_tenant_feature_usage(tenant_id)
        
        # Optimization opportunities
        optimization_opportunities = await self._identify_tenant_optimizations(tenant_id)
        
        return {
            "tenant_id": tenant_id,
            "cost_analytics": cost_analytics,
            "usage_statistics": usage_stats,
            "performance_metrics": performance_metrics,
            "feature_usage": feature_usage,
            "optimization_opportunities": optimization_opportunities,
            "generated_at": datetime.now().isoformat()
        }
    
    async def _validate_tenant_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tenant configuration"""
        
        # Default configuration
        default_config = {
            "plan_type": "basic",
            "max_queries_per_hour": 100,
            "max_queries_per_day": 1000,
            "daily_budget": 50.0,
            "monthly_budget": 1000.0,
            "allowed_search_engines": ["brave", "serpapi"],
            "max_content_urls": 6,
            "preferred_llm_provider": "ollama_local",
            "max_llm_calls": 3,
            "vector_db_enabled": True,
            "vector_provider": "chromadb",
            "cache_strategy": "standard",
            "quality_threshold": 0.7,
            "features_enabled": ["basic_search", "caching", "analytics"]
        }
        
        # Merge with provided config
        validated_config = {**default_config, **config}
        
        # Validate plan-specific limits
        plan_limits = {
            "basic": {
                "max_queries_per_day": 1000,
                "daily_budget": 50.0,
                "max_content_urls": 4,
                "allowed_features": ["basic_search", "caching"]
            },
            "professional": {
                "max_queries_per_day": 5000,
                "daily_budget": 200.0,
                "max_content_urls": 8,
                "allowed_features": ["basic_search", "caching", "analytics", "vector_search"]
            },
            "enterprise": {
                "max_queries_per_day": 50000,
                "daily_budget": 1000.0,
                "max_content_urls": 15,
                "allowed_features": ["basic_search", "caching", "analytics", "vector_search", "custom_models", "priority_support"]
            }
        }
        
        plan_type = validated_config["plan_type"]
        if plan_type in plan_limits:
            plan_config = plan_limits[plan_type]
            
            # Apply plan limits
            validated_config["max_queries_per_day"] = min(
                validated_config["max_queries_per_day"],
                plan_config["max_queries_per_day"]
            )
            validated_config["daily_budget"] = min(
                validated_config["daily_budget"],
                plan_config["daily_budget"]
            )
            validated_config["max_content_urls"] = min(
                validated_config["max_content_urls"],
                plan_config["max_content_urls"]
            )
            
            # Restrict features
            validated_config["features_enabled"] = [
                feature for feature in validated_config["features_enabled"]
                if feature in plan_config["allowed_features"]
            ]
        
        return validated_config
    
    async def _setup_tenant_isolation(self, 
                                    tenant_id: str, 
                                    config: Dict[str, Any]) -> Dict[str, Any]:
        """Setup tenant isolation"""
        
        isolation_setup = {}
        
        if self.isolation_strategy == "namespace":
            # Namespace-based isolation (Redis, Vector DB, etc.)
            isolation_setup["cache_namespace"] = f"tenant:{tenant_id}"
            isolation_setup["vector_namespace"] = f"vectors:tenant:{tenant_id}"
            isolation_setup["metrics_namespace"] = f"metrics:tenant:{tenant_id}"
            
        elif self.isolation_strategy == "database":
            # Database-level isolation
            isolation_setup["database_name"] = f"tenant_{tenant_id}"
            isolation_setup["vector_collection"] = f"tenant_{tenant_id}_vectors"
            
        elif self.isolation_strategy == "schema":
            # Schema-based isolation
            isolation_setup["schema_name"] = f"tenant_{tenant_id}"
            
        return isolation_setup

class PerformanceTuningSystem:
    """Advanced performance tuning and optimization"""
    
    def __init__(self):
        self.performance_history: List[Dict[str, Any]] = []
        self.optimization_models: Dict[str, Any] = {}
        self.tuning_parameters: Dict[str, Any] = {}
        
    async def analyze_performance_bottlenecks(self, 
                                            tenant_id: Optional[str] = None,
                                            time_window: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """Analyze performance bottlenecks"""
        
        # Collect performance data
        performance_data = await self._collect_performance_data(tenant_id, time_window)
        
        # Identify bottlenecks
        bottlenecks = {
            "slow_queries": await self._identify_slow_queries(performance_data),
            "resource_constraints": await self._identify_resource_constraints(performance_data),
            "cache_misses": await self._analyze_cache_performance(performance_data),
            "api_latencies": await self._analyze_api_latencies(performance_data),
            "cost_inefficiencies": await self._identify_cost_inefficiencies(performance_data)
        }
        
        # Generate optimization recommendations
        recommendations = await self._generate_performance_recommendations(bottlenecks)
        
        return {
            "analysis_period": {
                "start": (datetime.now() - time_window).isoformat(),
                "end": datetime.now().isoformat()
            },
            "bottlenecks": bottlenecks,
            "recommendations": recommendations,
            "performance_score": await self._calculate_performance_score(performance_data),
            "optimization_potential": await self._estimate_optimization_potential(bottlenecks)
        }
    
    async def auto_tune_performance(self, 
                                  tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Automatically tune performance parameters"""
        
        # Analyze current performance
        bottlenecks = await self.analyze_performance_bottlenecks(tenant_id)
        
        # Apply automatic optimizations
        optimizations_applied = []
        
        # Cache optimization
        if bottlenecks["bottlenecks"]["cache_misses"]["hit_rate"] < 0.6:
            cache_optimization = await self._optimize_cache_settings(tenant_id)
            optimizations_applied.append(cache_optimization)
        
        # Query routing optimization
        if bottlenecks["bottlenecks"]["slow_queries"]["average_time"] > 8.0:
            routing_optimization = await self._optimize_query_routing(tenant_id)
            optimizations_applied.append(routing_optimization)
        
        # Resource allocation optimization
        if bottlenecks["bottlenecks"]["resource_constraints"]["cpu_utilization"] > 0.8:
            resource_optimization = await self._optimize_resource_allocation(tenant_id)
            optimizations_applied.append(resource_optimization)
        
        # Cost optimization
        if bottlenecks["bottlenecks"]["cost_inefficiencies"]["cost_per_query"] > 0.05:
            cost_optimization = await self._optimize_cost_efficiency(tenant_id)
            optimizations_applied.append(cost_optimization)
        
        return {
            "tenant_id": tenant_id,
            "optimizations_applied": optimizations_applied,
            "expected_improvements": await self._predict_improvement_impact(optimizations_applied),
            "monitoring_period": "24_hours",
            "rollback_available": True
        }
    
    async def _optimize_cache_settings(self, tenant_id: Optional[str]) -> Dict[str, Any]:
        """Optimize caching settings"""
        
        current_settings = await self._get_current_cache_settings(tenant_id)
        
        optimizations = []
        
        # Increase TTL for stable content
        if current_settings["default_ttl"] < 7200:  # 2 hours
            optimizations.append({
                "parameter": "default_ttl",
                "old_value": current_settings["default_ttl"],
                "new_value": 7200,
                "expected_impact": "15% reduction in API calls"
            })
        
        # Enable semantic caching
        if not current_settings.get("semantic_caching_enabled", False):
            optimizations.append({
                "parameter": "semantic_caching_enabled",
                "old_value": False,
                "new_value": True,
                "expected_impact": "25% improvement in cache hit rate"
            })
        
        # Adjust cache size
        if current_settings["max_cache_size"] < 1000:
            optimizations.append({
                "parameter": "max_cache_size",
                "old_value": current_settings["max_cache_size"],
                "new_value": 1000,
                "expected_impact": "10% improvement in cache hit rate"
            })
        
        return {
            "optimization_type": "cache_settings",
            "optimizations": optimizations,
            "implementation_status": "applied",
            "monitoring_required": True
        }

# Integration with main system
class ProductionOptimizedOrchestrator:
    """Production-optimized orchestrator with all advanced features"""
    
    def __init__(self):
        self.cost_optimizer = SmartCostOptimizer()
        self.multi_tenant = MultiTenantArchitecture(self.cost_optimizer)
        self.performance_tuner = PerformanceTuningSystem()
        self.vector_enhanced = VectorEnhancedSearchWorkflow(
            vector_config={"provider": "chromadb"},
            embedding_config={"provider": "sentence_transformers", "model_name": "all-MiniLM-L6-v2"}
        )
        
    async def execute_production_search(self,
                                      query: str,
                                      tenant_id: str,
                                      user_id: Optional[str] = None,
                                      user_preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute search with full production optimizations"""
        
        start_time = datetime.now()
        
        try:
            # 1. Execute tenant-specific search
            tenant_result = await self.multi_tenant.execute_tenant_search(
                tenant_id=tenant_id,
                query=query,
                user_id=user_id,
                user_preferences=user_preferences
            )
            
            # 2. Enhance with vector capabilities
            vector_enhancement = await self.vector_enhanced.vector_enhanced_search(
                query=query,
                traditional_results=tenant_result["result"].get("sources", [])
            )
            
            # 3. Apply performance optimizations
            if tenant_result["processing_time"] > 8.0:  # Slow query
                performance_optimization = await self.performance_tuner.auto_tune_performance(tenant_id)
                tenant_result["performance_optimization"] = performance_optimization
            
            # 4. Generate comprehensive response
            final_result = {
                "query": query,
                "answer": vector_enhancement["result"]["answer"],
                "sources": vector_enhancement["result"]["sources"],
                "tenant_metadata": {
                    "tenant_id": tenant_id,
                    "cost_breakdown": tenant_result["actual_cost"],
                    "strategy_used": tenant_result["strategy_used"],
                    "processing_time": tenant_result["processing_time"]
                },
                "enhancement_metadata": {
                    "vector_enhanced": vector_enhancement["enhancement_applied"],
                    "semantic_matches": vector_enhancement.get("semantic_matches", 0),
                    "entity_insights": vector_enhancement["result"].get("entity_insights", [])
                },
                "performance_metadata": {
                    "total_processing_time": (datetime.now() - start_time).total_seconds(),
                    "optimizations_applied": tenant_result.get("performance_optimization", {}),
                    "cache_utilization": "calculated_separately"
                }
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"Production search failed: {e}")
            
            # Track error for analytics
            await self.cost_optimizer.track_cost(
                category=CostCategory.SEARCH_ENGINES,
                subcategory="error_handling",
                amount=0.001,  # Small cost for error tracking
                tenant_id=tenant_id,
                user_id=user_id,
                metadata={"error": str(e), "query": query[:100]}
            )
            
            raise
