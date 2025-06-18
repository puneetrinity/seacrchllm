# app/services/llm_service.py - Real Ollama Implementation
import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class LLMResponse(BaseModel):
    text: str
    confidence: float
    processing_time: float
    model_used: str
    tokens_used: int

class OllamaLLMService:
    """Concrete Ollama LLM implementation"""
    
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama2:7b"):
        self.host = host.rstrip('/')
        self.model = model
        self.session = None
        self.request_timeout = 30
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.request_timeout)
            )
        return self.session
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response using Ollama API"""
        
        start_time = datetime.now()
        session = await self._get_session()
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.1),
                "top_p": kwargs.get("top_p", 0.9),
                "max_tokens": kwargs.get("max_tokens", 500)
            }
        }
        
        try:
            async with session.post(f"{self.host}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")
                
                result = await response.json()
                processing_time = (datetime.now() - start_time).total_seconds()
                
                return LLMResponse(
                    text=result.get("response", "").strip(),
                    confidence=self._calculate_confidence(result),
                    processing_time=processing_time,
                    model_used=self.model,
                    tokens_used=result.get("eval_count", 0)
                )
                
        except asyncio.TimeoutError:
            logger.error(f"Ollama request timeout after {self.request_timeout}s")
            raise Exception("LLM request timeout")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
    
    async def agenerate(self, messages: List[str], **kwargs) -> List[LLMResponse]:
        """Generate multiple responses (for compatibility with LangChain interface)"""
        
        tasks = [self.generate(message, **kwargs) for message in messages]
        return await asyncio.gather(*tasks)
    
    def _calculate_confidence(self, result: Dict) -> float:
        """Calculate confidence score from Ollama response"""
        
        # Basic confidence calculation based on response length and completeness
        response_text = result.get("response", "")
        
        if not response_text:
            return 0.0
        
        confidence = 0.5  # Base confidence
        
        # Length factor
        if len(response_text) > 50:
            confidence += 0.2
        if len(response_text) > 200:
            confidence += 0.1
        
        # Completeness factor (doesn't end mid-sentence)
        if response_text.rstrip().endswith(('.', '!', '?')):
            confidence += 0.2
        
        return min(1.0, confidence)
    
    async def health_check(self) -> bool:
        """Check if Ollama service is available"""
        
        try:
            session = await self._get_session()
            async with session.get(f"{self.host}/api/tags") as response:
                return response.status == 200
        except Exception:
            return False

# app/langgraph/agents/classifier_agent.py - Real Implementation
import re
from typing import Dict, List, Tuple
from app.langgraph.state.search_state import SearchState, QueryType, ProcessingStage
from app.services.llm_service import OllamaLLMService

class ConcreteQueryClassifier:
    """Real implementation with actual LLM calls"""
    
    def __init__(self):
        self.llm = OllamaLLMService()
        self.classification_cache = {}
        
        # Pre-defined patterns for quick classification
        self.quick_patterns = {
            QueryType.REAL_TIME_NEWS: [
                r'\b(breaking|latest|current|today|now|recent|live|happening)\b',
                r'\b(news|update|announcement|alert)\b'
            ],
            QueryType.SIMPLE_FACTUAL: [
                r'^(what is|what are|who is|when is|where is|how many)',
                r'\b(definition|meaning|explain)\b'
            ],
            QueryType.COMPARISON: [
                r'\b(vs|versus|compared to|difference between|better than)\b',
                r'\b(compare|contrast|pros and cons)\b'
            ],
            QueryType.PROCEDURAL: [
                r'\b(how to|steps to|guide|tutorial|instructions)\b',
                r'\b(install|setup|configure|create)\b'
            ]
        }
    
    async def classify_query(self, state: SearchState) -> SearchState:
        """Real query classification with LLM"""
        
        query = state["query"]
        
        # Quick pattern-based classification first
        quick_result = self._quick_classify(query)
        if quick_result["confidence"] > 0.8:
            state.update(quick_result)
            state["processing_stage"] = ProcessingStage.CLASSIFIED
            return state
        
        # Fall back to LLM classification for complex cases
        llm_result = await self._llm_classify(query)
        
        # Combine results
        final_result = self._combine_classification_results(quick_result, llm_result)
        
        state.update(final_result)
        state["processing_stage"] = ProcessingStage.CLASSIFIED
        state["agent_outputs"]["classifier"] = final_result
        
        return state
    
    def _quick_classify(self, query: str) -> Dict:
        """Fast pattern-based classification"""
        
        query_lower = query.lower()
        
        for query_type, patterns in self.quick_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return {
                        "query_type": query_type,
                        "query_intent": self._detect_intent(query),
                        "query_complexity": self._assess_complexity(query),
                        "confidence": 0.85,
                        "classification_method": "pattern_based"
                    }
        
        return {
            "query_type": QueryType.COMPLEX_RESEARCH,
            "query_intent": "informational",
            "query_complexity": 0.7,
            "confidence": 0.3,
            "classification_method": "default"
        }
    
    async def _llm_classify(self, query: str) -> Dict:
        """LLM-based classification with real prompts"""
        
        classification_prompt = f"""
You are a search query classifier. Analyze this query and respond with EXACTLY this format:

QUERY: "{query}"

TYPE: [Choose ONE: SIMPLE_FACTUAL, COMPLEX_RESEARCH, REAL_TIME_NEWS, COMPARISON, PROCEDURAL, OPINION_BASED]
INTENT: [Choose ONE: informational, navigational, transactional, investigational, temporal]
COMPLEXITY: [Number between 0.0 and 1.0]
CONFIDENCE: [Number between 0.0 and 1.0]

Examples:
- "What is Python?" → TYPE: SIMPLE_FACTUAL, INTENT: informational, COMPLEXITY: 0.2, CONFIDENCE: 0.9
- "Latest news about AI" → TYPE: REAL_TIME_NEWS, INTENT: temporal, COMPLEXITY: 0.4, CONFIDENCE: 0.95
- "How to setup Docker" → TYPE: PROCEDURAL, INTENT: informational, COMPLEXITY: 0.6, CONFIDENCE: 0.9

Analyze the query and respond in the exact format above.
"""
        
        try:
            async with self.llm:
                response = await self.llm.generate(classification_prompt, temperature=0.1)
            
            # Parse LLM response
            return self._parse_llm_classification(response.text, response.confidence)
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                "query_type": QueryType.COMPLEX_RESEARCH,
                "query_intent": "informational", 
                "query_complexity": 0.7,
                "confidence": 0.2,
                "classification_method": "llm_fallback"
            }
    
    def _parse_llm_classification(self, response_text: str, llm_confidence: float) -> Dict:
        """Parse LLM classification response"""
        
        try:
            lines = response_text.split('\n')
            result = {}
            
            for line in lines:
                if 'TYPE:' in line:
                    type_str = line.split('TYPE:')[1].strip().upper()
                    result["query_type"] = QueryType(type_str.lower())
                elif 'INTENT:' in line:
                    result["query_intent"] = line.split('INTENT:')[1].strip().lower()
                elif 'COMPLEXITY:' in line:
                    complexity_str = line.split('COMPLEXITY:')[1].strip()
                    result["query_complexity"] = float(complexity_str)
                elif 'CONFIDENCE:' in line:
                    confidence_str = line.split('CONFIDENCE:')[1].strip()
                    result["confidence"] = float(confidence_str) * llm_confidence
            
            result["classification_method"] = "llm_based"
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse LLM classification: {e}")
            return {
                "query_type": QueryType.COMPLEX_RESEARCH,
                "query_intent": "informational",
                "query_complexity": 0.7,
                "confidence": 0.2,
                "classification_method": "parse_error"
            }
    
    def _detect_intent(self, query: str) -> str:
        """Enhanced intent detection"""
        
        query_lower = query.lower()
        
        intent_indicators = {
            "informational": ["what", "how", "why", "explain", "describe", "tell me"],
            "navigational": ["find", "locate", "go to", "website", "official site"],
            "transactional": ["buy", "purchase", "price", "cost", "order", "download"],
            "investigational": ["analyze", "compare", "evaluate", "research", "study"],
            "temporal": ["latest", "recent", "current", "today", "now", "breaking", "when"]
        }
        
        for intent, indicators in intent_indicators.items():
            if any(indicator in query_lower for indicator in indicators):
                return intent
        
        return "informational"
    
    def _assess_complexity(self, query: str) -> float:
        """Assess query complexity (0-1 scale)"""
        
        complexity = 0.0
        
        # Length factor
        word_count = len(query.split())
        complexity += min(0.3, word_count / 20)
        
        # Question complexity
        complexity += query.count('?') * 0.1
        
        # Conjunctions (indicate complex relationships)
        conjunctions = ['and', 'or', 'but', 'however', 'versus', 'vs', 'compared to']
        complexity += sum(0.15 for conj in conjunctions if conj in query.lower())
        
        # Technical terms (longer words often more complex)
        long_words = [word for word in query.split() if len(word) > 8]
        complexity += len(long_words) * 0.1
        
        # Multiple concepts
        if ',' in query:
            complexity += 0.1
        
        return min(1.0, complexity)
    
    def _combine_classification_results(self, quick_result: Dict, llm_result: Dict) -> Dict:
        """Combine quick and LLM classification results"""
        
        # If quick classification is confident, use it
        if quick_result["confidence"] > 0.8:
            return quick_result
        
        # If LLM is confident, use it
        if llm_result["confidence"] > 0.7:
            return llm_result
        
        # Otherwise, blend results
        return {
            "query_type": llm_result["query_type"],
            "query_intent": llm_result["query_intent"],
            "query_complexity": (quick_result["query_complexity"] + llm_result["query_complexity"]) / 2,
            "confidence": (quick_result["confidence"] + llm_result["confidence"]) / 2,
            "classification_method": "blended"
        }
