# app/langgraph/monitoring/performance_monitor.py
import asyncio
import time
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class PerformanceMetrics:
    request_id: str
    query: str
    total_time: float
    stage_times: Dict[str, float]
    agent_performance: Dict[str, float]
    quality_score: float
    cost_breakdown: Dict[str, float]
    cache_hit: bool
    error_count: int
    
class LangGraphPerformanceMonitor:
    def __init__(self):
        self.metrics_store = []
        self.real_time_stats = {
            "requests_per_minute": 0,
            "average_response_time": 0,
            "current_quality_score": 0,
            "cache_hit_rate": 0,
            "error_rate": 0
        }
        
    async def track_workflow_performance(self, state: SearchState) -> Dict[str, Any]:
        """Comprehensive workflow performance tracking"""
        
        # Extract timing data from state
        processing_times = state.get("processing_times", {})
        total_time = sum(processing_times.values())
        
        # Calculate per-agent performance
        agent_performance = {}
        for agent, output in state.get("agent_outputs", {}).items():
            if isinstance(output, dict) and "processing_time" in output:
                agent_performance[agent] = output["processing_time"]
        
        # Create performance record
        metrics = PerformanceMetrics(
            request_id=state["trace_id"],
            query=state["query"][:100],  # Truncate for storage
            total_time=total_time,
            stage_times=processing_times,
            agent_performance=agent_performance,
            quality_score=state.get("confidence_score", 0),
            cost_breakdown=state.get("api_costs", {}),
            cache_hit=state.get("cache_hit", False),
            error_count=len(state.get("errors", []))
        )
        
        # Store metrics
        self.metrics_store.append(metrics)
        
        # Update real-time stats
        await self._update_real_time_stats()
        
        # Performance alerts
        await self._check_performance_alerts(metrics)
        
        return {
            "performance_score": self._calculate_performance_score(metrics),
            "bottlenecks": self._identify_bottlenecks(metrics),
            "optimization_suggestions": self._generate_optimization_suggestions(metrics)
        }
    
    async def _update_real_time_stats(self):
        """Update real-time performance statistics"""
        
        # Get recent metrics (last 5 minutes)
        cutoff_time = datetime.now() - timedelta(minutes=5)
        recent_metrics = [
            m for m in self.metrics_store 
            if datetime.now() - timedelta(seconds=m.total_time) > cutoff_time
        ]
        
        if not recent_metrics:
            return
        
        # Calculate stats
        self.real_time_stats.update({
            "requests_per_minute": len(recent_metrics),
            "average_response_time": sum(m.total_time for m in recent_metrics) / len(recent_metrics),
            "current_quality_score": sum(m.quality_score for m in recent_metrics) / len(recent_metrics),
            "cache_hit_rate": sum(1 for m in recent_metrics if m.cache_hit) / len(recent_metrics),
            "error_rate": sum(1 for m in recent_metrics if m.error_count > 0) / len(recent_metrics)
        })
    
    def _identify_bottlenecks(self, metrics: PerformanceMetrics) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks"""
        
        bottlenecks = []
        
        # Check stage times
        for stage, time_taken in metrics.stage_times.items():
            if time_taken > 5.0:  # 5 second threshold
                bottlenecks.append({
                    "type": "stage_bottleneck",
                    "stage": stage,
                    "time": time_taken,
                    "severity": "high" if time_taken > 10 else "medium"
                })
        
        # Check agent performance
        for agent, time_taken in metrics.agent_performance.items():
            if time_taken > 3.0:  # 3 second threshold for agents
                bottlenecks.append({
                    "type": "agent_bottleneck", 
                    "agent": agent,
                    "time": time_taken,
                    "severity": "high" if time_taken > 6 else "medium"
                })
        
        return bottlenecks
    
    def _generate_optimization_suggestions(self, metrics: PerformanceMetrics) -> List[str]:
        """Generate optimization suggestions"""
        
        suggestions = []
        
        # High-level performance suggestions
        if metrics.total_time > 15:
            suggestions.append("Consider implementing more aggressive caching")
            suggestions.append("Evaluate parallel execution opportunities")
        
        # Cache suggestions
        if not metrics.cache_hit and metrics.quality_score > 0.8:
            suggestions.append("This high-quality result should be cached longer")
        
        # Cost optimization
        total_cost = sum(metrics.cost_breakdown.values())
        if total_cost > 0.05:  # 5 cents threshold
            suggestions.append("Consider using fewer search engines for simple queries")
        
        # Quality vs performance trade-off
        if metrics.quality_score < 0.6 and metrics.total_time > 10:
            suggestions.append("Performance is slow but quality is low - review agent logic")
        
        return suggestions

# FastAPI integration for monitoring
@router.get("/performance/dashboard")
async def get_performance_dashboard():
    """Real-time performance dashboard endpoint"""
    
    monitor = LangGraphPerformanceMonitor()
    
    # Get recent performance data
    recent_metrics = monitor.metrics_store[-100:]  # Last 100 requests
    
    dashboard_data = {
        "real_time_stats": monitor.real_time_stats,
        "recent_performance": [
            {
                "request_id": m.request_id,
                "query": m.query,
                "total_time": m.total_time,
                "quality_score": m.quality_score,
                "cache_hit": m.cache_hit
            }
            for m in recent_metrics[-20:]  # Last 20 requests
        ],
        "performance_trends": {
            "average_time_trend": [m.total_time for m in recent_metrics],
            "quality_trend": [m.quality_score for m in recent_metrics],
            "cache_hit_trend": [1 if m.cache_hit else 0 for m in recent_metrics]
        },
        "common_bottlenecks": monitor._analyze_common_bottlenecks(recent_metrics)
    }
    
    return dashboard_data
