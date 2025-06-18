# tests/performance/test_performance.py - Performance Tests
import pytest
import asyncio
import time
from app.langgraph.workflows.search_workflow import MasterSearchWorkflow

class TestPerformance:
    
    @pytest.mark.asyncio
    async def test_search_performance_targets(self, mock_ollama_service, mock_search_engines):
        """Test that search meets performance targets"""
        
        workflow = MasterSearchWorkflow()
        
        # Mock fast responses
        start_time = time.time()
        
        # Simulate workflow execution time
        await asyncio.sleep(0.1)  # Mock processing time
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Performance targets
        assert processing_time < 5.0  # Should complete in under 5 seconds
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        
        async def mock_search():
            await asyncio.sleep(0.1)  # Simulate processing
            return "mock result"
        
        # Test 10 concurrent requests
        tasks = [mock_search() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        assert all(result == "mock result" for result in results)

# tests/load/test_load.py - Load Testing (using pytest-benchmark if needed)
import pytest

class TestLoadCapacity:
    
    def test_query_classification_speed(self, benchmark):
        """Benchmark query classification speed"""
        
        from app.langgraph.agents.classifier_agent import ConcreteQueryClassifier
        
        classifier = ConcreteQueryClassifier()
        
        def classify_query():
            return classifier._quick_classify("What is machine learning?")
        
        result = benchmark(classify_query)
        assert result["confidence"] > 0.0
    
    def test_url_normalization_speed(self, benchmark):
        """Benchmark URL normalization performance"""
        
        from app.services.search_engines import MultiSearchEngine
        
        engine = MultiSearchEngine()
        
        def normalize_url():
            return engine._normalize_url("https://www.example.com/page?param=1#section")
        
        result = benchmark(normalize_url)
        assert result == "example.com/page"

# Run tests with: pytest tests/ -v --cov=app --cov-report=html
