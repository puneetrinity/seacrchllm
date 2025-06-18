# tests/unit/test_search_engines.py - Search Engine Tests
import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.services.search_engines import BraveSearchEngine, SerpApiSearchEngine, MultiSearchEngine

class TestBraveSearchEngine:
    
    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful Brave search"""
        
        engine = BraveSearchEngine(api_key="test_key")
        
        # Mock the HTTP response
        mock_response_data = {
            "web": {
                "results": [
                    {
                        "url": "https://example.com",
                        "title": "Test Title",
                        "description": "Test description",
                        "age": "2024-01-01",
                        "language": "en"
                    }
                ]
            }
        }
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response
            
            results = await engine.search("test query")
            
            assert len(results) == 1
            assert results[0].title == "Test Title"
            assert results[0].source_engine == "brave"
    
    @pytest.mark.asyncio
    async def test_search_api_error(self):
        """Test Brave search API error handling"""
        
        engine = BraveSearchEngine(api_key="test_key")
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 403
            mock_response.text = AsyncMock(return_value="API key invalid")
            mock_get.return_value.__aenter__.return_value = mock_response
            
            results = await engine.search("test query")
            
            assert results == []
    
    def test_relevance_score_calculation(self):
        """Test relevance score calculation"""
        
        engine = BraveSearchEngine()
        
        result = {
            "title": "Python Programming Guide",
            "description": "Learn Python programming with examples"
        }
        
        score = engine._calculate_relevance_score(result, "Python programming", 0)
        
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be high due to matching keywords

class TestSerpApiSearchEngine:
    
    @pytest.mark.asyncio
    async def test_search_success(self):
        """Test successful SerpApi search"""
        
        engine = SerpApiSearchEngine(api_key="test_key")
        
        mock_response_data = {
            "organic_results": [
                {
                    "link": "https://example.com",
                    "title": "Test Title",
                    "snippet": "Test snippet",
                    "position": 1
                }
            ]
        }
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_get.return_value.__aenter__.return_value = mock_response
            
            results = await engine.search("test query")
            
            assert len(results) == 1
            assert results[0].title == "Test Title"
            assert results[0].source_engine == "serpapi"

class TestMultiSearchEngine:
    
    @pytest.mark.asyncio
    async def test_search_multiple_engines(self, mock_search_engines):
        """Test multi-engine search orchestration"""
        
        multi_engine = MultiSearchEngine()
        multi_engine.engines = mock_search_engines
        
        results = await multi_engine.search_multiple(["test query"])
        
        assert len(results) >= 1
        assert any(r.source_engine == "brave" for r in results)
    
    @pytest.mark.asyncio  
    async def test_url_normalization(self):
        """Test URL normalization for deduplication"""
        
        multi_engine = MultiSearchEngine()
        
        test_cases = [
            ("https://www.example.com/", "example.com"),
            ("http://example.com/page?param=1", "example.com/page"),
            ("https://example.com/page#section", "example.com/page")
        ]
        
        for input_url, expected in test_cases:
            normalized = multi_engine._normalize_url(input_url)
            assert normalized == expected
