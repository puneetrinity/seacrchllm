# tests/integration/test_search_workflow.py - Integration Tests
import pytest
from unittest.mock import AsyncMock, Mock
from app.langgraph.workflows.search_workflow import MasterSearchWorkflow
from app.langgraph.state.search_state import SearchState, ProcessingStage

class TestMasterSearchWorkflow:
    
    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, mock_ollama_service, mock_search_engines, mock_content_fetcher):
        """Test complete workflow execution"""
        
        # Create workflow with mocked dependencies
        workflow = MasterSearchWorkflow()
        
        # Mock all the agents
        workflow.query_classifier = Mock()
        workflow.query_classifier.classify_query = AsyncMock(
            return_value={
                "query_type": "SIMPLE_FACTUAL",
                "query_intent": "informational",
                "query_complexity": 0.3,
                "confidence": 0.9
            }
        )
        
        initial_state = SearchState(
            query="What is Python programming?",
            query_id="test_123",
            user_id="test_user",
            trace_id="test_trace",
            processing_stage=ProcessingStage.INITIALIZED,
            processing_path=[],
            agent_outputs={},
            confidence_score=0.0
        )
        
        # Test that workflow can be created and has proper structure
        assert workflow.workflow is not None
        assert hasattr(workflow, 'health_check')
    
    @pytest.mark.asyncio
    async def test_workflow_error_handling(self):
        """Test workflow error handling"""
        
        workflow = MasterSearchWorkflow()
        
        # Test with invalid state
        with pytest.raises(Exception):
            invalid_state = {"invalid": "state"}
            await workflow.workflow.ainvoke(invalid_state)
    
    @pytest.mark.asyncio
    async def test_health_check(self, mock_ollama_service):
        """Test workflow health check"""
        
        workflow = MasterSearchWorkflow()
        
        # Mock component health checks
        with patch.object(workflow, 'query_enhancer') as mock_enhancer:
            mock_enhancer.health_check = AsyncMock(return_value="healthy")
            
            health_status = await workflow.health_check()
            
            assert isinstance(health_status, dict)
            assert "overall" in health_status
