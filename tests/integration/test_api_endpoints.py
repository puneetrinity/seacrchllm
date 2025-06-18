# tests/integration/test_api_endpoints.py - API Integration Tests
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app

client = TestClient(app)

class TestSearchAPI:
    
    def test_search_endpoint_success(self):
        """Test successful search API call"""
        
        with patch('app.api.endpoints.search_v2.MasterSearchWorkflow') as mock_workflow:
            # Mock workflow execution
            mock_instance = AsyncMock()
            mock_instance.workflow.ainvoke = AsyncMock(return_value={
                "final_response": {
                    "answer": "Python is a programming language",
                    "sources": ["https://python.org"]
                },
                "confidence_score": 0.85,
                "processing_path": ["classified", "searched", "analyzed"],
                "query_type": "SIMPLE_FACTUAL"
            })
            mock_workflow.return_value = mock_instance
            
            response = client.post(
                "/api/v2/search",
                json={
                    "query": "What is Python?",
                    "max_results": 5
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "confidence_score" in data
            assert data["query"] == "What is Python?"
    
    def test_search_endpoint_validation(self):
        """Test search endpoint input validation"""
        
        # Test empty query
        response = client.post(
            "/api/v2/search",
            json={"query": "", "max_results": 5}
        )
        assert response.status_code == 422
        
        # Test query too long
        response = client.post(
            "/api/v2/search", 
            json={"query": "x" * 1000, "max_results": 5}
        )
        assert response.status_code == 422
        
        # Test invalid max_results
        response = client.post(
            "/api/v2/search",
            json={"query": "test", "max_results": 100}
        )
        assert response.status_code == 422
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        
        with patch('app.api.endpoints.search_v2.MasterSearchWorkflow') as mock_workflow:
            mock_instance = AsyncMock()
            mock_instance.health_check = AsyncMock(return_value={
                "query_enhancer": "healthy",
                "search_engine": "healthy", 
                "llm_analyzer": "healthy"
            })
            mock_workflow.return_value = mock_instance
            
            response = client.get("/api/v2/health")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "components" in data
    
    def test_metrics_endpoint(self):
        """Test metrics endpoint"""
        
        response = client.get("/api/v2/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "total_searches" in data["metrics"]
