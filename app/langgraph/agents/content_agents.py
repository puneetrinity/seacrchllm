# app/langgraph/agents/content_agents.py
from typing import List, Dict, Any
import asyncio
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

class ContentProcessingAgent:
    def __init__(self):
        self.content_fetcher = ZenRowsContentFetcher()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        self.entity_extractor = EntityExtractor()
        
    async def fetch_content(self, state: SearchState) -> SearchState:
        """Intelligent content fetching with quality filtering"""
        
        search_results = state["search_results"]
        
        # Select best URLs for content fetching
        selected_urls = self._select_content_urls(search_results, state["query_type"])
        
        # Parallel content fetching
        fetch_tasks = [
            self._fetch_single_content(url, result.title) 
            for url, result in selected_urls
        ]
        
        content_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        # Filter successful content
        valid_content = [c for c in content_results if not isinstance(c, Exception)]
        
        # Process and enhance content
        processed_content = await self._process_content_batch(valid_content, state["query"])
        
        state["content_data"] = processed_content
        state["content_metadata"] = {
            "attempted_fetches": len(selected_urls),
            "successful_fetches": len(valid_content),
            "total_word_count": sum(c.word_count for c in processed_content),
            "average_quality_score": sum(c.metadata.get("quality_score", 0) for c in processed_content) / max(1, len(processed_content))
        }
        
        return state
    
    def _select_content_urls(self, search_results: List[SearchResult], query_type: str) -> List[Tuple[str, SearchResult]]:
        """Intelligent URL selection for content fetching"""
        
        # Quality scoring for URLs
        scored_results = []
        for result in search_results:
            score = result.relevance_score
            
            # Boost authoritative domains
            if any(domain in result.url for domain in ["wikipedia.org", "reuters.com", "bbc.com", "cnn.com"]):
                score += 0.2
            
            # Boost recent content for news queries
            if query_type == "REAL_TIME_NEWS" and any(word in result.url for word in ["news", "breaking", "latest"]):
                score += 0.15
            
            # Penalize low-quality indicators
            if any(indicator in result.url for indicator in ["spam", "ads", "clickbait"]):
                score -= 0.3
            
            scored_results.append((score, result.url, result))
        
        # Sort by score and select top URLs
        scored_results.sort(reverse=True)
        return [(url, result) for score, url, result in scored_results[:8]]
    
    async def _fetch_single_content(self, url: str, title: str) -> ContentData:
        """Fetch and initially process single content item"""
        
        try:
            # Fetch content using ZenRows
            content_response = await self.content_fetcher.fetch_content(url)
            
            if not content_response or len(content_response.strip()) < 100:
                raise ValueError("Content too short or empty")
            
            # Basic content processing
            cleaned_content = self._clean_content(content_response)
            word_count = len(cleaned_content.split())
            
            # Language detection
            language = self._detect_language(cleaned_content)
            
            return ContentData(
                url=url,
                title=title,
                content=cleaned_content,
                word_count=word_count,
                language=language,
                metadata={"fetch_success": True}
            )
            
        except Exception as e:
            logger.error(f"Content fetch failed for {url}: {e}")
            return ContentData(
                url=url,
                title=title,
                content="",
                word_count=0,
                language="unknown",
                metadata={"fetch_success": False, "error": str(e)}
            )
    
    async def _process_content_batch(self, content_list: List[ContentData], query: str) -> List[ContentData]:
        """Process content batch with enhancements"""
        
        processing_tasks = []
        for content in content_list:
            if content.word_count > 50:  # Only process substantial content
                task = self._enhance_single_content(content, query)
                processing_tasks.append(task)
        
        enhanced_content = await asyncio.gather(*processing_tasks)
        
        return [c for c in enhanced_content if c is not None]
    
    async def _enhance_single_content(self, content: ContentData, query: str) -> ContentData:
        """Enhance single content item with advanced processing"""
        
        try:
            # Parallel enhancement tasks
            enhancement_tasks = await asyncio.gather(
                self._extract_entities(content.content),
                self._generate_summary(content.content, query),
                self._analyze_sentiment(content.content),
                self._calculate_quality_score(content, query)
            )
            
            entities, summary, sentiment, quality_score = enhancement_tasks
            
            # Update content data
            content.extracted_entities = entities
            content.summary = summary
            content.sentiment_score = sentiment
            content.metadata.update({
                "quality_score": quality_score,
                "entity_count": len(entities),
                "summary_length": len(summary.split()) if summary else 0
            })
            
            return content
            
        except Exception as e:
            logger.error(f"Content enhancement failed: {e}")
            return content
    
    async def _extract_entities(self, content: str) -> List[str]:
        """Extract named entities from content"""
        return await self.entity_extractor.extract(content)
    
    async def _generate_summary(self, content: str, query: str) -> str:
        """Generate query-focused summary"""
        
        # Split content into chunks
        chunks = self.text_splitter.split_text(content)
        
        # Find most relevant chunks
        relevant_chunks = self._find_relevant_chunks(chunks, query)[:3]
        
        # Generate summary from relevant chunks
        combined_text = " ".join(relevant_chunks)
        
        summary_prompt = f"""
        Summarize this content in 2-3 sentences, focusing on information relevant to: "{query}"
        
        Content: {combined_text[:1500]}
        
        Summary:
        """
        
        # Use your existing LLM service
        summary = await self.llm.agenerate([HumanMessage(content=summary_prompt)])
        return summary.generations[0][0].text.strip()
    
    def _find_relevant_chunks(self, chunks: List[str], query: str) -> List[str]:
        """Find chunks most relevant to the query"""
        
        query_words = set(query.lower().split())
        scored_chunks = []
        
        for chunk in chunks:
            chunk_words = set(chunk.lower().split())
            relevance_score = len(query_words.intersection(chunk_words)) / len(query_words)
            scored_chunks.append((relevance_score, chunk))
        
        scored_chunks.sort(reverse=True)
        return [chunk for score, chunk in scored_chunks]
