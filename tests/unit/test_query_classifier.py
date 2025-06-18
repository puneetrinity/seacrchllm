# tests/unit/test_query_classifier.py - Query Classifier Tests  
import pytest
from app.langgraph.agents.classifier_agent import ConcreteQueryClassifier
from app.langgraph.state.search_state import SearchState, QueryType

class TestConcreteQueryClassifier:
    
    @pytest.mark.asyncio
    async def test_quick_classify_patterns(self):
        """Test pattern-based classification"""
        
        classifier = ConcreteQueryClassifier()
        
        test_cases = [
            ("What is Python?", QueryType.SIMPLE_FACTUAL),
            ("Latest news about AI", QueryType.REAL_TIME_NEWS),
            ("How to install Docker", QueryType.PROCEDURAL),
            ("Python vs Java comparison", QueryType.COMPARISON)
        ]
        
        for query, expected_type in test_cases:
            result = classifier._quick_classify(query)
            assert result["query_type"] == expected_type
            assert result["confidence"] > 0.8
    
    @pytest.mark.asyncio
    async def test_classify_query_full_workflow(self, mock_ollama_service):
        """Test full query classification workflow"""
        
        classifier = ConcreteQueryClassifier()
        classifier.llm = mock_ollama_service
        
        # Mock LLM response for classification
        mock_ollama_service.generate.return_value.text = """
        TYPE: SIMPLE_FACTUAL
        INTENT: informational
        COMPLEXITY: 0.3
        CONFIDENCE: 0.9
        """
        
        state = SearchState(
            query="What is machine learning?",
            # ... other required fields with defaults
            trace_id="test_trace"
        )
        
        result_state = await classifier.classify_query(state)
        
        assert result_state["query_type"] == QueryType.SIMPLE_FACTUAL
        assert result_state["query_intent"] == "informational"
        assert 0.0 <= result_state["query_complexity"] <= 1.0
    
    def test_intent_detection(self):
        """Test intent detection logic"""
        
        classifier = ConcreteQueryClassifier()
        
        test_cases = [
            ("What is the capital of France?", "informational"),
            ("Find the official Python website", "navigational"),
            ("Buy Python programming books", "transactional"),
            ("Compare Python vs Java performance", "investigational"),
            ("Latest Python release news", "temporal")
        ]
        
        for query, expected_intent in test_cases:
            intent = classifier._detect_intent(query)
            assert intent == expected_intent
    
    def test_complexity_assessment(self):
        """Test query complexity assessment"""
        
        classifier = ConcreteQueryClassifier()
        
        # Simple query
        simple_complexity = classifier._assess_complexity("What is Python?")
        assert simple_complexity < 0.3
        
        # Complex query
        complex_complexity = classifier._assess_complexity(
            "Compare the performance implications of using asyncio versus threading "
            "in Python for high-concurrency web applications, considering memory usage, "
            "CPU utilization, and scalability patterns."
        )
        assert complex_complexity > 0.7
