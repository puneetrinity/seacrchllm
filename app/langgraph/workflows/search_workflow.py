# app/langgraph/workflows/search_workflow.py
from langgraph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresCheckpointer
from app.langgraph.state.search_state import SearchState, ProcessingStage
from app.langgraph.agents import *

class MasterSearchWorkflow:
    def __init__(self):
        self.checkpointer = PostgresCheckpointer.from_env()
        self.workflow = self._build_master_workflow()
        
    def _build_master_workflow(self) -> StateGraph:
        """Build the complete LangGraph workflow"""
        
        # Create the main workflow
        workflow = StateGraph(SearchState)
        
        # === STAGE 1: INITIALIZATION & CLASSIFICATION ===
        workflow.add_node("initialize", self.initialize_search)
        workflow.add_node("classify_query", self.classify_query)
        workflow.add_node("route_strategy", self.determine_strategy)
        
        # === STAGE 2: CACHING & FAST PATHS ===
        workflow.add_node("check_cache", self.check_cache)
        workflow.add_node("simple_fast_path", self.simple_fast_path)
        workflow.add_node("cached_response", self.return_cached_response)
        
        # === STAGE 3: QUERY ENHANCEMENT ===
        workflow.add_node("enhance_query", self.enhance_query)
        workflow.add_node("semantic_expansion", self.semantic_expansion)
        workflow.add_node("intent_refinement", self.refine_intent)
        
        # === STAGE 4: PARALLEL SEARCH EXECUTION ===
        workflow.add_node("parallel_search", self.execute_parallel_search)
        workflow.add_node("real_time_search", self.execute_real_time_search)
        workflow.add_node("specialized_search", self.execute_specialized_search)
        
        # === STAGE 5: CONTENT PROCESSING ===
        workflow.add_node("fetch_content", self.fetch_content)
        workflow.add_node("extract_entities", self.extract_entities)
        workflow.add_node("content_analysis", self.analyze_content)
        
        # === STAGE 6: MULTI-AGENT ANALYSIS ===
        workflow.add_node("summarization_agent", self.summarization_agent)
        workflow.add_node("fact_checking_agent", self.fact_checking_agent)
        workflow.add_node("sentiment_agent", self.sentiment_analysis_agent)
        workflow.add_node("credibility_agent", self.source_credibility_agent)
        
        # === STAGE 7: SYNTHESIS & VALIDATION ===
        workflow.add_node("synthesize_results", self.synthesize_results)
        workflow.add_node("quality_validation", self.validate_quality)
        workflow.add_node("confidence_scoring", self.calculate_confidence)
        
        # === STAGE 8: RESPONSE FORMATTING ===
        workflow.add_node("format_response", self.format_response)
        workflow.add_node("add_metadata", self.add_response_metadata)
        workflow.add_node("final_validation", self.final_validation)
        
        # === CONDITIONAL ROUTING LOGIC ===
        
        # Entry point routing
        workflow.add_conditional_edges(
            "classify_query",
            self.route_by_classification,
            {
                "cache_check": "check_cache",
                "simple": "simple_fast_path",
                "complex": "enhance_query",
                "real_time": "real_time_search"
            }
        )
        
        # Cache routing
        workflow.add_conditional_edges(
            "check_cache",
            self.route_cache_result,
            {
                "hit": "cached_response",
                "miss": "enhance_query",
                "stale": "enhance_query"
            }
        )
        
        # Search strategy routing
        workflow.add_conditional_edges(
            "route_strategy",
            self.route_search_strategy,
            {
                "parallel": "parallel_search",
                "real_time": "real_time_search", 
                "specialized": "specialized_search"
            }
        )
        
        # Analysis routing
        workflow.add_conditional_edges(
            "content_analysis",
            self.route_analysis_strategy,
            {
                "full_analysis": "summarization_agent",
                "fact_check_only": "fact_checking_agent",
                "sentiment_only": "sentiment_agent"
            }
        )
        
        # Quality validation routing
        workflow.add_conditional_edges(
            "quality_validation",
            self.route_quality_decision,
            {
                "sufficient": "format_response",
                "needs_improvement": "enhance_query",  # Retry with better queries
                "needs_more_content": "specialized_search",  # Get more sources
                "failed": END  # Return error response
            }
        )
        
        # === EDGE CONNECTIONS ===
        
        # Linear progressions
        workflow.add_edge("initialize", "classify_query")
        workflow.add_edge("enhance_query", "semantic_expansion")
        workflow.add_edge("semantic_expansion", "intent_refinement")
        workflow.add_edge("intent_refinement", "route_strategy")
        
        # Search to content processing
        for search_node in ["parallel_search", "real_time_search", "specialized_search"]:
            workflow.add_edge(search_node, "fetch_content")
        
        workflow.add_edge("fetch_content", "extract_entities")
        workflow.add_edge("extract_entities", "content_analysis")
        
        # Analysis chain
        workflow.add_edge("summarization_agent", "fact_checking_agent")
        workflow.add_edge("fact_checking_agent", "sentiment_agent")
        workflow.add_edge("sentiment_agent", "credibility_agent")
        workflow.add_edge("credibility_agent", "synthesize_results")
        
        # Final processing
        workflow.add_edge("synthesize_results", "quality_validation")
        workflow.add_edge("format_response", "add_metadata")
        workflow.add_edge("add_metadata", "final_validation")
        workflow.add_edge("final_validation", END)
        workflow.add_edge("cached_response", END)
        workflow.add_edge("simple_fast_path", END)
        
        # Set entry point
        workflow.set_entry_point("initialize")
        
        return workflow.compile(checkpointer=self.checkpointer)
