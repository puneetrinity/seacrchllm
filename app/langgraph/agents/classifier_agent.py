# app/langgraph/agents/classifier_agent.py
import asyncio
from typing import Dict, List, Tuple
from langchain.llms import Ollama
from langchain.schema import HumanMessage
from app.langgraph.state.search_state import SearchState, QueryType

class AdvancedQueryClassifier:
    def __init__(self):
        self.llm = Ollama(model="llama2:7b")
        self.classification_cache = {}
        
    async def classify_query(self, state: SearchState) -> SearchState:
        """Advanced multi-dimensional query classification"""
        
        query = state["query"]
        
        # Check cache first
        if query in self.classification_cache:
            cached_result = self.classification_cache[query]
            state.update(cached_result)
            return state
        
        # Parallel classification tasks
        classification_tasks = await asyncio.gather(
            self._classify_query_type(query),
            self._detect_intent(query),
            self._assess_complexity(query),
            self._detect_temporal_context(query),
            self._identify_domain(query)
        )
        
        query_type, intent, complexity, temporal, domain = classification_tasks
        
        # Update state with classification results
        state["query_type"] = query_type
        state["query_intent"] = intent
        state["query_complexity"] = complexity
        state["processing_stage"] = ProcessingStage.CLASSIFIED
        state["agent_outputs"]["classifier"] = {
            "type": query_type,
            "intent": intent,
            "complexity": complexity,
            "temporal_context": temporal,
            "domain": domain,
            "confidence": min(classification_tasks[i].get("confidence", 0.8) for i in range(len(classification_tasks)))
        }
        
        # Cache the result
        self.classification_cache[query] = {
            "query_type": query_type,
            "query_intent": intent,
            "query_complexity": complexity
        }
        
        return state
    
    async def _classify_query_type(self, query: str) -> QueryType:
        """Classify the fundamental type of query"""
        
        classification_prompt = f"""
        Classify this search query into ONE of these categories:
        
        1. SIMPLE_FACTUAL: Basic facts, definitions, single answers
        2. COMPLEX_RESEARCH: Multi-faceted research requiring analysis
        3. REAL_TIME_NEWS: Current events, breaking news, recent updates
        4. COMPARISON: Comparing multiple things, pros/cons, alternatives
        5. PROCEDURAL: How-to, step-by-step instructions
        6. OPINION_BASED: Reviews, opinions, subjective analysis
        
        Query: "{query}"
        
        Respond with just the category name and confidence (0-1):
        Category: [CATEGORY]
        Confidence: [0.XX]
        """
        
        response = await self.llm.agenerate([HumanMessage(content=classification_prompt)])
        result = response.generations[0][0].text.strip()
        
        # Parse response
        lines = result.split('\n')
        category = lines[0].split(': ')[1] if len(lines) > 0 else "COMPLEX_RESEARCH"
        confidence = float(lines[1].split(': ')[1]) if len(lines) > 1 else 0.7
        
        return QueryType(category.lower())
    
    async def _detect_intent(self, query: str) -> str:
        """Detect the user's specific intent"""
        
        intent_patterns = {
            "informational": ["what", "how", "why", "who", "when", "where"],
            "navigational": ["find", "locate", "go to", "website", "official"],
            "transactional": ["buy", "purchase", "price", "cost", "deal"],
            "investigational": ["analyze", "compare", "evaluate", "research"],
            "temporal": ["latest", "recent", "current", "today", "now", "breaking"]
        }
        
        query_lower = query.lower()
        intent_scores = {}
        
        for intent, keywords in intent_patterns.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            intent_scores[intent] = score / len(keywords)
        
        return max(intent_scores, key=intent_scores.get)
    
    async def _assess_complexity(self, query: str) -> float:
        """Assess query complexity (0-1 scale)"""
        
        complexity_factors = {
            "length": len(query.split()) / 20,  # Longer queries often more complex
            "questions": query.count('?') * 0.2,
            "conjunctions": sum(1 for word in ["and", "or", "but", "versus", "vs"] if word in query.lower()) * 0.3,
            "specificity": sum(1 for word in query.split() if len(word) > 8) / len(query.split())
        }
        
        base_complexity = sum(complexity_factors.values()) / len(complexity_factors)
        return min(1.0, base_complexity)
    
    async def _detect_temporal_context(self, query: str) -> Dict[str, bool]:
        """Detect temporal requirements"""
        
        query_lower = query.lower()
        
        return {
            "requires_current": any(word in query_lower for word in ["current", "latest", "recent", "today", "now"]),
            "historical": any(word in query_lower for word in ["history", "past", "before", "ago", "previously"]),
            "trending": any(word in query_lower for word in ["trending", "popular", "viral", "breaking"]),
            "time_sensitive": any(word in query_lower for word in ["urgent", "immediate", "asap", "quickly"])
        }
    
    async def _identify_domain(self, query: str) -> str:
        """Identify the primary domain/topic"""
        
        domain_keywords = {
            "technology": ["tech", "software", "AI", "programming", "computer", "digital"],
            "health": ["health", "medical", "doctor", "medicine", "treatment", "symptoms"],
            "business": ["business", "market", "finance", "economy", "company", "investment"],
            "science": ["science", "research", "study", "experiment", "theory", "scientific"],
            "news": ["news", "breaking", "report", "announcement", "update", "alert"],
            "education": ["learn", "education", "school", "university", "course", "tutorial"],
            "entertainment": ["movie", "music", "game", "entertainment", "celebrity", "show"]
        }
        
        query_lower = query.lower()
        domain_scores = {}
        
        for domain, keywords in domain_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            domain_scores[domain] = score
        
        return max(domain_scores, key=domain_scores.get) if max(domain_scores.values()) > 0 else "general"
