# app/langgraph/agents/validation_agents.py
from typing import Dict, List, Any, Literal
from app.langgraph.state.search_state import SearchState

class QualityValidationAgent:
    def __init__(self):
        self.quality_thresholds = {
            "minimum_confidence": 0.4,
            "minimum_sources": 2,
            "minimum_content_words": 200,
            "maximum_processing_time": 15.0
        }
        
    async def validate_quality(self, state: SearchState) -> SearchState:
        """Comprehensive quality validation"""
        
        # Calculate multiple quality metrics
        quality_metrics = await self._calculate_quality_metrics(state)
        
        # Overall quality assessment
        overall_quality = self._assess_overall_quality(quality_metrics)
        
        # Update state
        state["quality_metrics"] = quality_metrics
        state["confidence_score"] = overall_quality["confidence"]
        
        return state
    
    async def validate_and_route(self, state: SearchState) -> Literal["sufficient", "needs_improvement", "needs_more_content", "failed"]:
        """Intelligent routing based on quality assessment"""
        
        quality_metrics = state["quality_metrics"]
        retry_count = state.get("retry_count", 0)
        
        # Check if we've exceeded retry limits
        if retry_count >= 2:
            return "failed"
        
        # Check critical failure conditions
        if quality_metrics["content_availability"] < 0.2:
            return "needs_more_content"
        
        if quality_metrics["overall_confidence"] < self.quality_thresholds["minimum_confidence"]:
            if quality_metrics["source_diversity"] < 0.5:
                return "needs_more_content"
            else:
                return "needs_improvement"
        
        # Check if quality is sufficient
        if (quality_metrics["overall_confidence"] > 0.7 and 
            quality_metrics["content_availability"] > 0.6 and
            quality_metrics["source_credibility"] > 0.5):
            return "sufficient"
        
        # Default to improvement needed
        return "needs_improvement"
    
    async def _calculate_quality_metrics(self, state: SearchState) -> Dict[str, float]:
        """Calculate comprehensive quality metrics"""
        
        content_data = state["content_data"]
        search_results = state["search_results"]
        analysis_result = state.get("analysis_result")
        
        metrics = {}
        
        # Content availability and quality
        metrics["content_availability"] = len(content_data) / max(1, len(search_results))
        metrics["content_quality"] = self._assess_content_quality(content_data)
        
        # Source diversity and credibility
        metrics["source_diversity"] = self._calculate_source_diversity(search_results)
        metrics["source_credibility"] = self._calculate_average_credibility(content_data)
        
        # Analysis quality
        if analysis_result:
            metrics["analysis_confidence"] = analysis_result.confidence_score
            metrics["fact_verification"] = state.get("fact_check_results", {}).get("overall_score", 0.5)
        else:
            metrics["analysis_confidence"] = 0.0
            metrics["fact_verification"] = 0.0
        
        # Processing efficiency
        processing_times = state.get("processing_times", {})
        total_time = sum(processing_times.values())
        metrics["processing_efficiency"] = max(0, 1 - (total_time / 30))  # 30s max expected
        
        # Query-answer alignment
        metrics["query_alignment"] = await self._assess_query_alignment(
            state["query"], 
            analysis_result.summary if analysis_result else ""
        )
        
        # Overall confidence calculation
        weights = {
            "content_availability": 0.2,
            "content_quality": 0.2,
            "source_credibility": 0.15,
            "analysis_confidence": 0.25,
            "fact_verification": 0.1,
            "query_alignment": 0.1
        }
        
        metrics["overall_confidence"] = sum(
            metrics.get(metric, 0) * weight 
            for metric, weight in weights.items()
        )
        
        return metrics
    
    def _assess_content_quality(self, content_data: List[ContentData]) -> float:
        """Assess quality of fetched content"""
        
        if not content_data:
            return 0.0
        
        quality_scores = []
        for content in content_data:
            score = 0.0
            
            # Word count quality
            if content.word_count > 500:
                score += 0.3
            elif content.word_count > 200:
                score += 0.2
            elif content.word_count > 50:
                score += 0.1
            
            # Language quality
            if content.language == "english":
                score += 0.2
            
            # Entity extraction success
            if len(content.extracted_entities) > 3:
                score += 0.2
            
            # Summary availability
            if content.summary and len(content.summary) > 50:
                score += 0.2
            
            # Overall quality from metadata
            score += content.metadata.get("quality_score", 0.5) * 0.1
            
            quality_scores.append(min(1.0, score))
        
        return sum(quality_scores) / len(quality_scores)
    
    async def _assess_query_alignment(self, query: str, answer: str) -> float:
        """Assess how well the answer addresses the query"""
        
        if not answer or len(answer) < 20:
            return 0.0
        
        # Simple keyword overlap assessment
        query_words = set(query.lower().split())
        answer_words = set(answer.lower().split())
        
        overlap = len(query_words.intersection(answer_words))
        alignment_score = overlap / max(1, len(query_words))
        
        # Boost for direct question answering patterns
        if query.strip().endswith('?') and any(pattern in answer.lower() for pattern in ['is', 'are', 'yes', 'no', 'because']):
            alignment_score += 0.2
        
        return min(1.0, alignment_score)
