# app/langgraph/agents/search_agents.py
import asyncio
from typing import List, Dict, Any
from app.langgraph.state.search_state import SearchState, SearchResult

class ParallelSearchAgent:
    def __init__(self):
        self.search_engines = {
            "brave": BraveSearchEngine(),
            "serp": SerpApiSearchEngine(), 
            "bing": BingSearchEngine()
        }
        self.performance_tracker = SearchPerformanceTracker()
        
    async def execute_parallel_search(self, state: SearchState) -> SearchState:
        """Execute intelligent parallel search across multiple engines"""
        
        enhanced_queries = state["enhanced_queries"][:3]  # Top 3 enhanced queries
        query_complexity = state["query_complexity"]
        
        # Determine search strategy based on complexity and query type
        search_strategy = self._determine_search_strategy(state)
        
        # Execute searches in parallel
        search_tasks = []
        
        for query in enhanced_queries:
            for engine_name, engine in self.search_engines.items():
                if self._should_use_engine(engine_name, search_strategy, query_complexity):
                    task = self._search_with_engine(engine, query, engine_name)
                    search_tasks.append(task)
        
        # Execute all searches concurrently
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Filter successful results
        valid_results = [r for r in search_results if not isinstance(r, Exception)]
        
        # Deduplicate and rank results
        deduplicated_results = self._deduplicate_and_rank(valid_results, state["query"])
        
        # Update state
        state["search_results"] = deduplicated_results
        state["search_metadata"] = {
            "total_searches": len(search_tasks),
            "successful_searches": len(valid_results),
            "strategy_used": search_strategy,
            "deduplication_ratio": len(valid_results) / max(1, len(deduplicated_results))
        }
        
        return state
    
    def _determine_search_strategy(self, state: SearchState) -> Dict[str, Any]:
        """Determine optimal search strategy"""
        
        query_type = state["query_type"]
        complexity = state["query_complexity"]
        
        if query_type == "REAL_TIME_NEWS":
            return {
                "engines": ["serp", "bing"],  # Better for current events
                "max_results_per_engine": 8,
                "focus_recency": True
            }
        elif query_type == "SIMPLE_FACTUAL" and complexity < 0.3:
            return {
                "engines": ["brave"],  # Single engine for simple queries
                "max_results_per_engine": 5,
                "focus_authority": True
            }
        else:
            return {
                "engines": ["brave", "serp", "bing"],  # All engines for complex queries
                "max_results_per_engine": 10,
                "focus_diversity": True
            }
    
    async def _search_with_engine(self, engine, query: str, engine_name: str) -> List[SearchResult]:
        """Execute search with a specific engine"""
        
        try:
            start_time = asyncio.get_event_loop().time()
            raw_results = await engine.search(query)
            end_time = asyncio.get_event_loop().time()
            
            # Track performance
            await self.performance_tracker.record_search(
                engine_name, 
                end_time - start_time, 
                len(raw_results)
            )
            
            # Convert to SearchResult objects
            search_results = []
            for result in raw_results:
                search_result = SearchResult(
                    url=result.get("url", ""),
                    title=result.get("title", ""),
                    snippet=result.get("snippet", ""),
                    source_engine=engine_name,
                    relevance_score=result.get("relevance_score", 0.5),
                    timestamp=datetime.now(),
                    metadata=result.get("metadata", {})
                )
                search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed for engine {engine_name}: {e}")
            return []
    
    def _deduplicate_and_rank(self, results: List[List[SearchResult]], original_query: str) -> List[SearchResult]:
        """Advanced deduplication and ranking"""
        
        # Flatten results
        all_results = [result for sublist in results for result in sublist]
        
        # Deduplicate by URL similarity
        seen_urls = set()
        deduplicated = []
        
        for result in all_results:
            url_normalized = self._normalize_url(result.url)
            if url_normalized not in seen_urls:
                seen_urls.add(url_normalized)
                deduplicated.append(result)
        
        # Re-rank results
        ranked_results = self._rank_results(deduplicated, original_query)
        
        return ranked_results[:15]  # Return top 15 results
    
    def _rank_results(self, results: List[SearchResult], query: str) -> List[SearchResult]:
        """Advanced result ranking"""
        
        for result in results:
            score = 0.0
            
            # Relevance score from search engine
            score += result.relevance_score * 0.4
            
            # Title relevance
            title_words = set(result.title.lower().split())
            query_words = set(query.lower().split())
            title_overlap = len(title_words.intersection(query_words)) / max(1, len(query_words))
            score += title_overlap * 0.3
            
            # Domain authority (simplified)
            domain_authority = self._get_domain_authority(result.url)
            score += domain_authority * 0.2
            
            # Recency bonus
            if "news" in result.url or "blog" in result.url:
                score += 0.1
            
            result.relevance_score = score
        
        return sorted(results, key=lambda x: x.relevance_score, reverse=True)
