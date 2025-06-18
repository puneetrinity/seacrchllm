# app/langgraph/agents/analysis_agents.py
import asyncio
from typing import Dict, List, Any
from langchain.schema import HumanMessage

class MultiAgentAnalysisSystem:
    def __init__(self):
        self.llm = Ollama(model="llama2:7b")
        self.fact_checker = FactCheckingAgent()
        self.sentiment_analyzer = SentimentAnalysisAgent()
        self.credibility_scorer = CredibilityAgent()
        
    async def synthesize_results(self, state: SearchState) -> SearchState:
        """Master synthesis orchestrator"""
        
        content_data = state["content_data"]
        query = state["query"]
        
        # Run all analysis agents in parallel
        analysis_tasks = await asyncio.gather(
            self._master_summarization(content_data, query),
            self._fact_verification(content_data, query),
            self._sentiment_analysis(content_data),
            self._credibility_assessment(content_data),
            self._topic_extraction(content_data),
            self._consensus_building(content_data, query)
        )
        
        (summary, fact_check, sentiment, credibility, 
         topics, consensus) = analysis_tasks
        
        # Create comprehensive analysis result
        analysis_result = AnalysisResult(
            summary=summary["text"],
            key_facts=fact_check["verified_facts"],
            confidence_score=consensus["confidence"],
            sentiment=sentiment,
            entities=self._extract_all_entities(content_data),
            topics=topics,
            source_credibility=credibility
        )
        
        state["analysis_result"] = analysis_result
        state["fact_check_results"] = fact_check
        state["agent_outputs"]["analysis"] = {
            "summary_confidence": summary["confidence"],
            "fact_check_score": fact_check["overall_score"],
            "sentiment_distribution": sentiment,
            "credibility_average": sum(credibility.values()) / len(credibility),
            "topic_coherence": topics.get("coherence_score", 0),
            "consensus_level": consensus["level"]
        }
        
        return state
    
    async def _master_summarization(self, content_data: List[ContentData], query: str) -> Dict[str, Any]:
        """Advanced multi-perspective summarization"""
        
        # Collect all summaries
        individual_summaries = [c.summary for c in content_data if c.summary]
        
        if not individual_summaries:
            return {"text": "No sufficient content available for summarization.", "confidence": 0.1}
        
        # Create comprehensive summary
        synthesis_prompt = f"""
        Create a comprehensive answer to: "{query}"
        
        Based on these source summaries:
        {chr(10).join(f"Source {i+1}: {summary}" for i, summary in enumerate(individual_summaries[:5]))}
        
        Provide:
        1. A direct answer to the question (2-3 sentences)
        2. Key supporting details (2-3 bullet points)
        3. Any important caveats or limitations
        
        Focus on accuracy and cite when sources disagree.
        """
        
        response = await self.llm.agenerate([HumanMessage(content=synthesis_prompt)])
        summary_text = response.generations[0][0].text.strip()
        
        # Calculate confidence based on source agreement
        confidence = self._calculate_summary_confidence(individual_summaries, summary_text)
        
        return {"text": summary_text, "confidence": confidence}
    
    async def _fact_verification(self, content_data: List[ContentData], query: str) -> Dict[str, Any]:
        """Advanced fact checking across sources"""
        
        # Extract claims from content
        all_claims = []
        for content in content_data:
            claims = await self._extract_claims(content.content)
            all_claims.extend(claims)
        
        # Cross-verify claims across sources
        verified_facts = []
        disputed_facts = []
        
        for claim in all_claims[:10]:  # Limit to top 10 claims
            verification_result = await self._verify_claim_across_sources(claim, content_data)
            
            if verification_result["confidence"] > 0.7:
                verified_facts.append({
                    "claim": claim,
                    "confidence": verification_result["confidence"],
                    "supporting_sources": verification_result["supporting_sources"]
                })
            elif verification_result["confidence"] < 0.3:
                disputed_facts.append({
                    "claim": claim,
                    "confidence": verification_result["confidence"],
                    "conflicting_info": verification_result["conflicts"]
                })
        
        overall_score = len(verified_facts) / max(1, len(all_claims))
        
        return {
            "verified_facts": [f["claim"] for f in verified_facts],
            "disputed_claims": disputed_facts,
            "overall_score": overall_score,
            "fact_check_details": verified_facts
        }
    
    async def _consensus_building(self, content_data: List[ContentData], query: str) -> Dict[str, Any]:
        """Build consensus across multiple sources"""
        
        if len(content_data) < 2:
            return {"confidence": 0.5, "level": "insufficient_sources"}
        
        # Extract key points from each source
        source_points = []
        for content in content_data:
            points = await self._extract_key_points(content.content, query)
            source_points.append(points)
        
        # Find agreement and disagreement
        agreement_matrix = self._calculate_agreement_matrix(source_points)
        consensus_points = self._identify_consensus_points(source_points, agreement_matrix)
        
        consensus_level = len(consensus_points) / max(1, max(len(points) for points in source_points))
        
        return {
            "confidence": min(0.9, consensus_level + 0.1),
            "level": "high" if consensus_level > 0.7 else "medium" if consensus_level > 0.4 else "low",
            "consensus_points": consensus_points,
            "agreement_score": consensus_level
        }
