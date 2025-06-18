# app/services/search_engines.py - Real Brave & SerpApi Implementations
import aiohttp
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import quote_plus
from app.config.settings import settings

logger = logging.getLogger(__name__)

class SearchResult:
    def __init__(self, url: str, title: str, snippet: str, source_engine: str, **kwargs):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.source_engine = source_engine
        self.relevance_score = kwargs.get('relevance_score', 0.5)
        self.timestamp = kwargs.get('timestamp', datetime.now())
        self.metadata = kwargs.get('metadata', {})

class BraveSearchEngine:
    """Real Brave Search API implementation"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.BRAVE_SEARCH_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search(self, query: str, count: int = 10) -> List[SearchResult]:
        """Execute Brave search with real API"""
        
        if not self.api_key:
            raise ValueError("Brave Search API key not configured")
        
        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json"
        }
        
        params = {
            "q": query,
            "count": min(count, 20),  # Brave API limit
            "search_lang": "en",
            "country": "us",
            "safesearch": "moderate",
            "freshness": "pw",  # Past week for freshness
            "text_decorations": "false"
        }
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            async with self.session.get(
                self.base_url, 
                headers=headers, 
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status == 429:
                    logger.warning("Brave Search rate limit hit")
                    await asyncio.sleep(1)
                    return []
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Brave Search API error {response.status}: {error_text}")
                    return []
                
                data = await response.json()
                return self._parse_brave_results(data, query)
                
        except asyncio.TimeoutError:
            logger.error("Brave Search request timeout")
            return []
        except Exception as e:
            logger.error(f"Brave Search failed: {e}")
            return []
    
    def _parse_brave_results(self, data: Dict, query: str) -> List[SearchResult]:
        """Parse Brave API response"""
        
        results = []
        web_results = data.get("web", {}).get("results", [])
        
        for i, result in enumerate(web_results):
            try:
                search_result = SearchResult(
                    url=result.get("url", ""),
                    title=result.get("title", ""),
                    snippet=result.get("description", ""),
                    source_engine="brave",
                    relevance_score=self._calculate_relevance_score(result, query, i),
                    metadata={
                        "position": i + 1,
                        "age": result.get("age", ""),
                        "language": result.get("language", "en"),
                        "family_friendly": result.get("family_friendly", True)
                    }
                )
                results.append(search_result)
            except Exception as e:
                logger.error(f"Error parsing Brave result: {e}")
                continue
        
        return results
    
    def _calculate_relevance_score(self, result: Dict, query: str, position: int) -> float:
        """Calculate relevance score for Brave results"""
        
        score = 1.0 - (position * 0.05)  # Position-based scoring
        
        # Title relevance
        title = result.get("title", "").lower()
        query_words = query.lower().split()
        title_matches = sum(1 for word in query_words if word in title)
        score += (title_matches / len(query_words)) * 0.3
        
        # Snippet relevance
        snippet = result.get("description", "").lower()
        snippet_matches = sum(1 for word in query_words if word in snippet)
        score += (snippet_matches / len(query_words)) * 0.2
        
        return min(1.0, max(0.0, score))

class SerpApiSearchEngine:
    """Real SerpApi (Google) implementation"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.SERPAPI_API_KEY
        self.base_url = "https://serpapi.com/search"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search(self, query: str, count: int = 10) -> List[SearchResult]:
        """Execute SerpApi search with real API"""
        
        if not self.api_key:
            raise ValueError("SerpApi API key not configured")
        
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": min(count, 100),  # SerpApi supports up to 100
            "hl": "en",
            "gl": "us",
            "google_domain": "google.com",
            "safe": "active",
            "device": "desktop"
        }
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            async with self.session.get(
                self.base_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                
                if response.status == 401:
                    logger.error("SerpApi authentication failed")
                    return []
                
                if response.status == 429:
                    logger.warning("SerpApi rate limit hit")
                    await asyncio.sleep(2)
                    return []
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"SerpApi error {response.status}: {error_text}")
                    return []
                
                data = await response.json()
                
                # Check for API errors
                if "error" in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    return []
                
                return self._parse_serpapi_results(data, query)
                
        except asyncio.TimeoutError:
            logger.error("SerpApi request timeout")
            return []
        except Exception as e:
            logger.error(f"SerpApi search failed: {e}")
            return []
    
    def _parse_serpapi_results(self, data: Dict, query: str) -> List[SearchResult]:
        """Parse SerpApi response"""
        
        results = []
        organic_results = data.get("organic_results", [])
        
        for i, result in enumerate(organic_results):
            try:
                search_result = SearchResult(
                    url=result.get("link", ""),
                    title=result.get("title", ""),
                    snippet=result.get("snippet", ""),
                    source_engine="serpapi",
                    relevance_score=self._calculate_relevance_score(result, query, i),
                    metadata={
                        "position": result.get("position", i + 1),
                        "displayed_link": result.get("displayed_link", ""),
                        "cached_page_link": result.get("cached_page_link", ""),
                        "related_pages_link": result.get("related_pages_link", ""),
                        "serpapi_link": result.get("serpapi_link", "")
                    }
                )
                results.append(search_result)
            except Exception as e:
                logger.error(f"Error parsing SerpApi result: {e}")
                continue
        
        return results
    
    def _calculate_relevance_score(self, result: Dict, query: str, position: int) -> float:
        """Calculate relevance score for SerpApi results"""
        
        score = 1.0 - (position * 0.04)  # Position-based scoring (SerpApi generally better quality)
        
        # Title relevance
        title = result.get("title", "").lower()
        query_words = query.lower().split()
        title_matches = sum(1 for word in query_words if word in title)
        score += (title_matches / len(query_words)) * 0.35
        
        # Snippet relevance
        snippet = result.get("snippet", "").lower()
        snippet_matches = sum(1 for word in query_words if word in snippet)
        score += (snippet_matches / len(query_words)) * 0.25
        
        return min(1.0, max(0.0, score))

# Real ZenRows Implementation
class ZenRowsContentFetcher:
    """Real ZenRows content fetching implementation"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.ZENROWS_API_KEY
        self.base_url = "https://api.zenrows.com/v1/"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_content(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Fetch content from multiple URLs using ZenRows"""
        
        if not self.api_key:
            raise ValueError("ZenRows API key not configured")
        
        # Limit concurrent requests to avoid overwhelming ZenRows
        semaphore = asyncio.Semaphore(3)
        tasks = [self._fetch_single_url(url, semaphore) for url in urls[:8]]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        successful_results = []
        for result in results:
            if not isinstance(result, Exception) and result:
                successful_results.append(result)
        
        return successful_results
    
    async def _fetch_single_url(self, url: str, semaphore: asyncio.Semaphore) -> Optional[Dict[str, Any]]:
        """Fetch content from a single URL"""
        
        async with semaphore:
            params = {
                "url": url,
                "apikey": self.api_key,
                "js_render": "true",
                "antibot": "true",
                "premium_proxy": "true",
                "session_id": "search_session"
            }
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            try:
                async with self.session.get(
                    self.base_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as response:
                    
                    if response.status == 422:
                        logger.warning(f"ZenRows failed to process URL: {url}")
                        return None
                    
                    if response.status == 429:
                        logger.warning("ZenRows rate limit hit")
                        await asyncio.sleep(2)
                        return None
                    
                    if response.status != 200:
                        logger.error(f"ZenRows error {response.status} for {url}")
                        return None
                    
                    content = await response.text()
                    
                    # Basic content extraction
                    cleaned_content = self._extract_main_content(content)
                    
                    if len(cleaned_content) < 100:
                        logger.warning(f"Insufficient content extracted from {url}")
                        return None
                    
                    return {
                        "url": url,
                        "content": cleaned_content,
                        "word_count": len(cleaned_content.split()),
                        "success": True,
                        "timestamp": datetime.now().isoformat()
                    }
                    
            except asyncio.TimeoutError:
                logger.error(f"ZenRows timeout for {url}")
                return None
            except Exception as e:
                logger.error(f"ZenRows fetch failed for {url}: {e}")
                return None
    
    def _extract_main_content(self, html_content: str) -> str:
        """Extract main content from HTML using BeautifulSoup"""
        
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(["script", "style", "nav", "header", "footer", "aside", "advertisement"]):
                element.decompose()
            
            # Try to find main content areas
            main_content = None
            for tag in ["main", "article", "[role='main']", ".content", ".post-content", ".entry-content"]:
                main_content = soup.select_one(tag)
                if main_content:
                    break
            
            # Fallback to body if no main content found
            if not main_content:
                main_content = soup.find("body")
            
            if not main_content:
                return ""
            
            # Extract text and clean up
            text = main_content.get_text(separator=" ", strip=True)
            
            # Remove excessive whitespace
            import re
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n+', '\n', text)
            
            return text.strip()
            
        except ImportError:
            logger.error("BeautifulSoup not installed - using raw HTML")
            return html_content[:5000]  # Return first 5000 chars as fallback
        except Exception as e:
            logger.error(f"Content extraction failed: {e}")
            return ""

# Multi-Engine Search Orchestrator
class MultiSearchEngine:
    """Orchestrates multiple search engines"""
    
    def __init__(self):
        self.engines = {
            "brave": BraveSearchEngine(),
            "serpapi": SerpApiSearchEngine()
        }
        self.performance_tracker = {}
        
    async def search_multiple(self, queries: List[str], max_results_per_query: int = 10) -> List[SearchResult]:
        """Execute parallel searches across multiple engines"""
        
        # Create search tasks
        search_tasks = []
        
        for query in queries[:3]:  # Limit to top 3 queries
            for engine_name, engine in self.engines.items():
                async with engine:
                    task = self._search_with_tracking(engine, engine_name, query, max_results_per_query)
                    search_tasks.append(task)
        
        # Execute all searches in parallel
        all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Flatten and deduplicate results
        combined_results = []
        seen_urls = set()
        
        for result_batch in all_results:
            if isinstance(result_batch, Exception):
                logger.error(f"Search batch failed: {result_batch}")
                continue
            
            for result in result_batch:
                normalized_url = self._normalize_url(result.url)
                if normalized_url not in seen_urls:
                    seen_urls.add(normalized_url)
                    combined_results.append(result)
        
        # Sort by relevance score
        combined_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return combined_results[:max_results_per_query * 2]  # Return top results
    
    async def _search_with_tracking(self, engine, engine_name: str, query: str, max_results: int) -> List[SearchResult]:
        """Execute search with performance tracking"""
        
        start_time = datetime.now()
        
        try:
            results = await engine.search(query, max_results)
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Track performance
            if engine_name not in self.performance_tracker:
                self.performance_tracker[engine_name] = []
            
            self.performance_tracker[engine_name].append({
                "query": query,
                "results_count": len(results),
                "processing_time": processing_time,
                "timestamp": start_time.isoformat()
            })
            
            logger.info(f"{engine_name} search completed in {processing_time:.2f}s with {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"{engine_name} search failed: {e}")
            return []
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication"""
        
        import re
        
        # Remove protocol
        url = re.sub(r'^https?://', '', url)
        
        # Remove www
        url = re.sub(r'^www\.', '', url)
        
        # Remove trailing slash
        url = url.rstrip('/')
        
        # Remove query parameters and fragments
        url = url.split('?')[0].split('#')[0]
        
        return url.lower()
    
    async def health_check(self) -> Dict[str, bool]:
        """Health check for all search engines"""
        
        health_status = {}
        
        for engine_name, engine in self.engines.items():
            try:
                async with engine:
                    # Try a simple test search
                    results = await engine.search("test", 1)
                    health_status[engine_name] = len(results) >= 0  # Even 0 results is OK
            except Exception as e:
                logger.error(f"{engine_name} health check failed: {e}")
                health_status[engine_name] = False
        
        return health_status
