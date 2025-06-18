# tests/conftest.py - Test Configuration
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, Mock
from typing import AsyncGenerator

# Set test environment
os.environ["TESTING"] = "true"
os.environ["BRAVE_SEARCH_API_KEY"] = "test_brave_key"
os.environ["SERPAPI_API_KEY"] = "test_serp_key" 
os.environ["ZENROWS_API_KEY"] = "test_zenrows_key"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def mock_ollama_service():
    """Mock Ollama service for testing"""
    from app.services.llm_service import OllamaLLMService, LLMResponse
    
    service = OllamaLLMService()
    
    # Mock the generate method
    async def mock_generate(prompt: str, **kwargs):
        return LLMResponse(
            text="Test LLM response",
            confidence=0.8,
            processing_time=0.5,
            model_used="test_model",
            tokens_used=50
        )
    
    service.generate = AsyncMock(side_effect=mock_generate)
    service.agenerate = AsyncMock(return_value=[await mock_generate("test")])
    service.health_check = AsyncMock(return_value=True)
    
    return service

@pytest.fixture
async def mock_search_engines():
    """Mock search engines for testing"""
    from app.services.search_engines import SearchResult
    from datetime import datetime
    
    mock_results = [
        SearchResult(
            url="https://example.com/1",
            title="Test Result 1",
            snippet="This is a test search result",
            source_engine="brave",
            relevance_score=0.9,
            timestamp=datetime.now()
        ),
        SearchResult(
            url="https://example.com/2", 
            title="Test Result 2",
            snippet="Another test result",
            source_engine="serpapi",
            relevance_score=0.8,
            timestamp=datetime.now()
        )
    ]

    # Mock search engines
    brave_engine = Mock()
    brave_engine.search = AsyncMock(return_value=mock_results[:1])
    
    serpapi_engine = Mock() 
    serpapi_engine.search = AsyncMock(return_value=mock_results[1:])
    
    return {"brave": brave_engine, "serpapi": serpapi_engine}

@pytest.fixture
async def mock_content_fetcher():
    """Mock content fetcher for testing"""
    from app.services.search_engines import ZenRowsContentFetcher
    
    fetcher = ZenRowsContentFetcher()
    
    mock_content = [
        {
            "url": "https://example.com/1",
            "content": "This is detailed content from example.com with lots of information about the topic.",
            "word_count": 15,
            "success": True,
            "timestamp": "2024-01-01T00:00:00"
        }
    ]
    
    fetcher.fetch_content = AsyncMock(return_value=mock_content)
    
    return fetcher

