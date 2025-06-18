# tests/unit/test_llm_service.py - LLM Service Tests
import pytest
from unittest.mock import AsyncMock, patch
from app.services.llm_service import OllamaLLMService, LLMResponse

class TestOllamaLLMService:
    
    @pytest.mark.asyncio
    async def test_generate_success(self, mock_ollama_service):
        """Test successful LLM generation"""
        
        response = await mock_ollama_service.generate("Test prompt")
        
        assert isinstance(response, LLMResponse)
        assert response.text == "Test LLM response"
        assert response.confidence == 0.8
        assert response.model_used == "test_model"
    
    @pytest.mark.asyncio
    async def test_agenerate_multiple_prompts(self, mock_ollama_service):
        """Test multiple prompt generation"""
        
        prompts = ["Prompt 1", "Prompt 2"]
        responses = await mock_ollama_service.agenerate(prompts)
        
        assert len(responses) == 1  # Mock returns single response
        assert all(isinstance(r, LLMResponse) for r in responses)
    
    @pytest.mark.asyncio
    async def test_health_check(self, mock_ollama_service):
        """Test health check functionality"""
        
        is_healthy = await mock_ollama_service.health_check()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_confidence_calculation(self):
        """Test confidence score calculation"""
        
        service = OllamaLLMService()
        
        # Test empty response
        result_empty = {"response": ""}
        confidence_empty = service._calculate_confidence(result_empty)
        assert confidence_empty == 0.0
        
        # Test short response
        result_short = {"response": "Short"}
        confidence_short = service._calculate_confidence(result_short)
        assert 0.5 <= confidence_short <= 0.7
        
        # Test complete response
        result_complete = {"response": "This is a complete response with proper punctuation."}
        confidence_complete = service._calculate_confidence(result_complete)
        assert confidence_complete >= 0.8
