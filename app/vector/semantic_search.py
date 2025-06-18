# app/vector/semantic_search.py - Vector Database Integration for Semantic Search

import asyncio
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import hashlib
from enum import Enum

# Vector database integrations
try:
    import pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

try:
    import weaviate
    WEAVIATE_AVAILABLE = True
except ImportError:
    WEAVIATE_AVAILABLE = False

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Embedding models
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class VectorProvider(str, Enum):
    PINECONE = "pinecone"
    WEAVIATE = "weaviate"
    CHROMADB = "chromadb"
    QDRANT = "qdrant"
    MILVUS = "milvus"

class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    HUGGINGFACE = "huggingface"
    COHERE = "cohere"

@dataclass
class SemanticSearchResult:
    content: str
    metadata: Dict[str, Any]
    similarity_score: float
    vector_id: str
    source_url: Optional[str] = None
    timestamp: Optional[datetime] = None

@dataclass
class VectorDocument:
    id: str
    content: str
    vector: List[float]
    metadata: Dict[str, Any]
    namespace: Optional[str] = None

class UniversalEmbeddingService:
    """Universal embedding service supporting multiple providers"""
    
    def __init__(self, 
                 provider: EmbeddingProvider = EmbeddingProvider.SENTENCE_TRANSFORMERS,
                 model_name: str = "all-MiniLM-L6-v2"):
        self.provider = provider
        self.model_name = model_name
        self.model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize embedding model based on provider"""
        
        if self.provider == EmbeddingProvider.SENTENCE_TRANSFORMERS and SENTENCE_TRANSFORMERS_AVAILABLE:
            self.model = SentenceTransformer(self.model_name)
            self.embedding_dimension = self.model.get_sentence_embedding_dimension()
            
        elif self.provider == EmbeddingProvider.OPENAI and OPENAI_AVAILABLE:
            # OpenAI embeddings don't need local model loading
            self.embedding_dimension = 1536 if "ada-002" in self.model_name else 1024
            
        else:
            raise ValueError(f"Embedding provider {self.provider} not available or unsupported")
    
    async def encode_texts(self, texts: List[str]) -> List[List[float]]:
        """Encode texts into embeddings"""
        
        if self.provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            # Batch encoding for efficiency
            embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False)
            return embeddings.tolist()
            
        elif self.provider == EmbeddingProvider.OPENAI:
            # OpenAI embeddings API
            embeddings = []
            for text in texts:
                response = await openai.Embedding.acreate(
                    model=self.model_name,
                    input=text
                )
                embeddings.append(response['data'][0]['embedding'])
            return embeddings
        
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")
    
    async def encode_single(self, text: str) -> List[float]:
        """Encode single text into embedding"""
        embeddings = await self.encode_texts([text])
        return embeddings[0]

class UniversalVectorDatabase:
    """Universal vector database interface supporting multiple providers"""
    
    def __init__(self, 
                 provider: VectorProvider,
                 config: Dict[str, Any],
                 embedding_service: UniversalEmbeddingService):
        self.provider = provider
        self.config = config
        self.embedding_service = embedding_service
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize vector database client"""
        
        if self.provider == VectorProvider.PINECONE and PINECONE_AVAILABLE:
            pinecone.init(
                api_key=self.config["api_key"],
                environment=self.config["environment"]
            )
            self.client = pinecone.Index(self.config["index_name"])
            
        elif self.provider == VectorProvider.WEAVIATE and WEAVIATE_AVAILABLE:
            self.client = weaviate.Client(
                url=self.config["url"],
                auth_client_secret=weaviate.auth.AuthApiKey(api_key=self.config.get("api_key"))
            )
            
        elif self.provider == VectorProvider.CHROMADB and CHROMADB_AVAILABLE:
            self.client = chromadb.Client()
            self.collection = self.client.get_or_create_collection(
                name=self.config["collection_name"]
            )
            
        else:
            raise ValueError(f"Vector provider {self.provider} not available")
    
    async def upsert_documents(self, documents: List[VectorDocument]) -> bool:
        """Upsert documents into vector database"""
        
        try:
            if self.provider == VectorProvider.PINECONE:
                # Prepare data for Pinecone
                vectors = [
                    (doc.id, doc.vector, doc.metadata)
                    for doc in documents
                ]
                self.client.upsert(vectors=vectors, namespace=documents[0].namespace)
                
            elif self.provider == VectorProvider.WEAVIATE:
                # Batch upsert for Weaviate
                with self.client.batch as batch:
                    for doc in documents:
                        batch.add_data_object(
                            data_object={
                                "content": doc.content,
                                **doc.metadata
                            },
                            class_name=self.config["class_name"],
                            uuid=doc.id,
                            vector=doc.vector
                        )
                        
            elif self.provider == VectorProvider.CHROMADB:
                # ChromaDB upsert
                self.collection.upsert(
                    ids=[doc.id for doc in documents],
                    embeddings=[doc.vector for doc in documents],
                    documents=[doc.content for doc in documents],
                    metadatas=[doc.metadata for doc in documents]
                )
            
            return True
            
        except Exception as e:
            print(f"Error upserting documents: {e}")
            return False
    
    async def semantic_search(self, 
                            query: str,
                            top_k: int = 10,
                            namespace: Optional[str] = None,
                            filters: Optional[Dict[str, Any]] = None) -> List[SemanticSearchResult]:
        """Perform semantic search"""
        
        # Generate query embedding
        query_vector = await self.embedding_service.encode_single(query)
        
        if self.provider == VectorProvider.PINECONE:
            # Pinecone search
            search_response = self.client.query(
                vector=query_vector,
                top_k=top_k,
                namespace=namespace,
                filter=filters,
                include_metadata=True
            )
            
            results = []
            for match in search_response['matches']:
                results.append(SemanticSearchResult(
                    content=match['metadata'].get('content', ''),
                    metadata=match['metadata'],
                    similarity_score=match['score'],
                    vector_id=match['id'],
                    source_url=match['metadata'].get('source_url'),
                    timestamp=match['metadata'].get('timestamp')
                ))
            
        elif self.provider == VectorProvider.WEAVIATE:
            # Weaviate search
            search_response = (
                self.client.query
                .get(self.config["class_name"], ["content", "_additional {certainty}"])
                .with_near_vector({"vector": query_vector})
                .with_limit(top_k)
                .do()
            )
            
            results = []
            for item in search_response['data']['Get'][self.config["class_name"]]:
                results.append(SemanticSearchResult(
                    content=item['content'],
                    metadata=item,
                    similarity_score=item['_additional']['certainty'],
                    vector_id=item.get('id', ''),
                    source_url=item.get('source_url'),
                    timestamp=item.get('timestamp')
                ))
                
        elif self.provider == VectorProvider.CHROMADB:
            # ChromaDB search
            search_response = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=filters
            )
            
            results = []
            for i, (id, distance, metadata, document) in enumerate(zip(
                search_response['ids'][0],
                search_response['distances'][0],
                search_response['metadatas'][0],
                search_response['documents'][0]
            )):
                # Convert distance to similarity (assuming cosine distance)
                similarity = 1 - distance
                results.append(SemanticSearchResult(
                    content=document,
                    metadata=metadata,
                    similarity_score=similarity,
                    vector_id=id,
                    source_url=metadata.get('source_url'),
                    timestamp=metadata.get('timestamp')
                ))
        
        return results
    
    async def hybrid_search(self,
                          query: str,
                          text_fields: List[str],
                          top_k: int = 10,
                          semantic_weight: float = 0.7) -> List[SemanticSearchResult]:
        """Perform hybrid search combining semantic and keyword search"""
        
        # Semantic search
        semantic_results = await self.semantic_search(query, top_k=top_k * 2)
        
        # Keyword search (implementation depends on provider)
        keyword_results = await self._keyword_search(query, text_fields, top_k=top_k * 2)
        
        # Combine and re-rank results
        combined_results = self._combine_search_results(
            semantic_results,
            keyword_results,
            semantic_weight
        )
        
        return combined_results[:top_k]
    
    async def _keyword_search(self, 
                            query: str, 
                            text_fields: List[str], 
                            top_k: int) -> List[SemanticSearchResult]:
        """Perform keyword-based search"""
        
        if self.provider == VectorProvider.WEAVIATE:
            # Weaviate BM25 search
            search_response = (
                self.client.query
                .get(self.config["class_name"], text_fields + ["_additional {score}"])
                .with_bm25(query=query)
                .with_limit(top_k)
                .do()
            )
            
            results = []
            for item in search_response['data']['Get'][self.config["class_name"]]:
                results.append(SemanticSearchResult(
                    content=item.get('content', ''),
                    metadata=item,
                    similarity_score=item['_additional']['score'],
                    vector_id=item.get('id', ''),
                    source_url=item.get('source_url'),
                    timestamp=item.get('timestamp')
                ))
            
            return results
        
        else:
            # For other providers, return empty results or implement custom keyword search
            return []

class SemanticSearchEngine:
    """Enhanced search engine with semantic capabilities"""
    
    def __init__(self,
                 vector_db: UniversalVectorDatabase,
                 embedding_service: UniversalEmbeddingService,
                 traditional_search_engine: Any = None):
        self.vector_db = vector_db
        self.embedding_service = embedding_service
        self.traditional_search = traditional_search_engine
        
        # Search configuration
        self.semantic_threshold = 0.7
        self.hybrid_enabled = True
        self.reranking_enabled = True
    
    async def enhanced_search(self,
                            query: str,
                            search_type: str = "hybrid",
                            max_results: int = 10,
                            filters: Optional[Dict[str, Any]] = None) -> List[SemanticSearchResult]:
        """Enhanced search with multiple strategies"""
        
        if search_type == "semantic_only":
            return await self.vector_db.semantic_search(
                query=query,
                top_k=max_results,
                filters=filters
            )
        
        elif search_type == "hybrid" and self.hybrid_enabled:
            return await self.vector_db.hybrid_search(
                query=query,
                text_fields=["content", "title"],
                top_k=max_results
            )
        
        elif search_type == "traditional_enhanced":
            return await self._traditional_enhanced_search(query, max_results, filters)
        
        else:
            # Default to semantic search
            return await self.vector_db.semantic_search(
                query=query,
                top_k=max_results,
                filters=filters
            )
    
    async def _traditional_enhanced_search(self,
                                         query: str,
                                         max_results: int,
                                         filters: Optional[Dict[str, Any]]) -> List[SemanticSearchResult]:
        """Enhance traditional search with semantic reranking"""
        
        if not self.traditional_search:
            return await self.vector_db.semantic_search(query, max_results, filters=filters)
        
        # Get traditional search results
        traditional_results = await self.traditional_search.search(query, max_results * 2)
        
        # Convert to semantic format and add to vector DB if not exists
        semantic_candidates = []
        
        for result in traditional_results:
            # Check if already in vector DB
            existing = await self._check_existing_document(result.url)
            
            if not existing:
                # Add to vector DB
                await self._add_to_vector_db(result)
            
            semantic_candidates.append(SemanticSearchResult(
                content=result.snippet + " " + getattr(result, 'content', ''),
                metadata={
                    "url": result.url,
                    "title": result.title,
                    "source_engine": result.source_engine
                },
                similarity_score=result.relevance_score,
                vector_id=hashlib.md5(result.url.encode()).hexdigest(),
                source_url=result.url
            ))
        
        # Semantic reranking
        if self.reranking_enabled:
            reranked_results = await self._semantic_rerank(query, semantic_candidates)
            return reranked_results[:max_results]
        
        return semantic_candidates[:max_results]
    
    async def _semantic_rerank(self,
                             query: str,
                             candidates: List[SemanticSearchResult]) -> List[SemanticSearchResult]:
        """Rerank candidates using semantic similarity"""
        
        # Generate query embedding
        query_embedding = await self.embedding_service.encode_single(query)
        
        # Generate embeddings for candidates
        candidate_texts = [result.content for result in candidates]
        candidate_embeddings = await self.embedding_service.encode_texts(candidate_texts)
        
        # Calculate similarity scores
        for i, result in enumerate(candidates):
            similarity = self._cosine_similarity(query_embedding, candidate_embeddings[i])
            # Combine with original score
            result.similarity_score = (result.similarity_score * 0.3) + (similarity * 0.7)
        
        # Sort by new similarity scores
        candidates.sort(key=lambda x: x.similarity_score, reverse=True)
        
        return candidates
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        dot_product = np.dot(vec1_np, vec2_np)
        magnitude1 = np.linalg.norm(vec1_np)
        magnitude2 = np.linalg.norm(vec2_np)
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    async def _add_to_vector_db(self, search_result: Any):
        """Add search result to vector database"""
        
        content = search_result.snippet
        if hasattr(search_result, 'content') and search_result.content:
            content = search_result.content
        
        # Generate embedding
        embedding = await self.embedding_service.encode_single(content)
        
        # Create vector document
        doc = VectorDocument(
            id=hashlib.md5(search_result.url.encode()).hexdigest(),
            content=content,
            vector=embedding,
            metadata={
                "url": search_result.url,
                "title": search_result.title,
                "source_engine": search_result.source_engine,
                "relevance_score": search_result.relevance_score,
                "timestamp": datetime.now().isoformat(),
                "indexed_at": datetime.now().isoformat()
            }
        )
        
        # Upsert to vector DB
        await self.vector_db.upsert_documents([doc])

class SemanticCacheManager:
    """Semantic cache manager for query similarity"""
    
    def __init__(self, 
                 vector_db: UniversalVectorDatabase,
                 embedding_service: UniversalEmbeddingService,
                 similarity_threshold: float = 0.85):
        self.vector_db = vector_db
        self.embedding_service = embedding_service
        self.similarity_threshold = similarity_threshold
        self.cache_namespace = "semantic_cache"
    
    async def get_similar_cached_result(self, query: str) -> Optional[Dict[str, Any]]:
        """Get cached result for semantically similar query"""
        
        # Search for similar queries in cache
        similar_results = await self.vector_db.semantic_search(
            query=query,
            top_k=5,
            namespace=self.cache_namespace
        )
        
        # Check if any result meets similarity threshold
        for result in similar_results:
            if result.similarity_score >= self.similarity_threshold:
                # Check if cache is still valid
                cached_at = datetime.fromisoformat(result.metadata.get("cached_at"))
                ttl_hours = result.metadata.get("ttl_hours", 24)
                
                if datetime.now() - cached_at < timedelta(hours=ttl_hours):
                    return {
                        "cached_result": json.loads(result.metadata["cached_response"]),
                        "original_query": result.metadata["original_query"],
                        "similarity_score": result.similarity_score,
                        "cached_at": cached_at
                    }
        
        return None
    
    async def cache_query_result(self,
                                query: str,
                                result: Dict[str, Any],
                                ttl_hours: int = 24):
        """Cache query result for semantic similarity matching"""
        
        # Generate embedding for query
        query_embedding = await self.embedding_service.encode_single(query)
        
        # Create cache document
        cache_doc = VectorDocument(
            id=hashlib.md5(f"{query}_{datetime.now().isoformat()}".encode()).hexdigest(),
            content=query,
            vector=query_embedding,
            metadata={
                "original_query": query,
                "cached_response": json.dumps(result),
                "cached_at": datetime.now().isoformat(),
                "ttl_hours": ttl_hours,
                "cache_type": "semantic_query_cache"
            },
            namespace=self.cache_namespace
        )
        
        # Store in vector database
        await self.vector_db.upsert_documents([cache_doc])

class KnowledgeGraphIntegration:
    """Integration with knowledge graphs for enhanced semantic understanding"""
    
    def __init__(self, 
                 vector_db: UniversalVectorDatabase,
                 embedding_service: UniversalEmbeddingService):
        self.vector_db = vector_db
        self.embedding_service = embedding_service
        self.entity_extraction_model = None
        self.relation_extraction_model = None
    
    async def extract_and_store_entities(self, content: str, source_url: str) -> Dict[str, Any]:
        """Extract entities and relationships from content"""
        
        # Entity extraction (simplified - in production use spaCy, Hugging Face NER, etc.)
        entities = await self._extract_entities(content)
        
        # Relationship extraction
        relationships = await self._extract_relationships(content, entities)
        
        # Create entity embeddings
        entity_documents = []
        
        for entity in entities:
            entity_embedding = await self.embedding_service.encode_single(
                f"{entity['text']} {entity['label']} {entity.get('context', '')}"
            )
            
            entity_doc = VectorDocument(
                id=f"entity_{hashlib.md5(f'{entity['text']}_{source_url}'.encode()).hexdigest()}",
                content=f"{entity['text']} ({entity['label']})",
                vector=entity_embedding,
                metadata={
                    "type": "entity",
                    "entity_text": entity['text'],
                    "entity_label": entity['label'],
                    "source_url": source_url,
                    "confidence": entity.get('confidence', 0.5),
                    "context": entity.get('context', ''),
                    "relationships": [r for r in relationships if entity['text'] in r['entities']]
                },
                namespace="knowledge_graph"
            )
            
            entity_documents.append(entity_doc)
        
        # Store entities in vector database
        if entity_documents:
            await self.vector_db.upsert_documents(entity_documents)
        
        return {
            "entities": entities,
            "relationships": relationships,
            "stored_count": len(entity_documents)
        }
    
    async def semantic_entity_search(self,
                                   query: str,
                                   entity_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for entities semantically related to query"""
        
        # Build filters for entity types
        filters = {"type": "entity"}
        if entity_types:
            filters["entity_label"] = {"$in": entity_types}
        
        # Semantic search in knowledge graph namespace
        results = await self.vector_db.semantic_search(
            query=query,
            top_k=20,
            namespace="knowledge_graph",
            filters=filters
        )
        
        # Group related entities
        entity_clusters = self._cluster_related_entities(results)
        
        return entity_clusters
    
    async def _extract_entities(self, content: str) -> List[Dict[str, Any]]:
        """Extract named entities from content"""
        
        # Simplified entity extraction - in production use proper NER models
        import re
        
        entities = []
        
        # Simple patterns for demonstration
        patterns = {
            "PERSON": r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',
            "ORG": r'\b[A-Z][a-z]+ (Inc|Corp|LLC|Ltd|Company|Corporation)\b',
            "DATE": r'\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b',
            "MONEY": r'\$\d+(?:,\d{3})*(?:\.\d{2})?'
        }
        
        for label, pattern in patterns.items():
            matches = re.finditer(pattern, content)
            for match in matches:
                entities.append({
                    "text": match.group(),
                    "label": label,
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.8,
                    "context": content[max(0, match.start()-50):match.end()+50]
                })
        
        return entities
    
    async def _extract_relationships(self, 
                                   content: str, 
                                   entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract relationships between entities"""
        
        relationships = []
        
        # Simplified relationship extraction
        for i, entity1 in enumerate(entities):
            for j, entity2 in enumerate(entities[i+1:], i+1):
                # Check if entities appear close to each other
                distance = abs(entity1['start'] - entity2['start'])
                
                if distance < 100:  # Within 100 characters
                    relationships.append({
                        "entities": [entity1['text'], entity2['text']],
                        "relationship_type": "co_occurrence",
                        "confidence": max(0.3, 1 - (distance / 100)),
                        "context": content[
                            min(entity1['start'], entity2['start'])-20:
                            max(entity1['end'], entity2['end'])+20
                        ]
                    })
        
        return relationships

# Integration with main LangGraph workflow
class VectorEnhancedSearchWorkflow:
    """LangGraph workflow enhanced with vector database capabilities"""
    
    def __init__(self, 
                 vector_config: Dict[str, Any],
                 embedding_config: Dict[str, Any]):
        
        # Initialize vector components
        self.embedding_service = UniversalEmbeddingService(
            provider=EmbeddingProvider(embedding_config["provider"]),
            model_name=embedding_config["model_name"]
        )
        
        self.vector_db = UniversalVectorDatabase(
            provider=VectorProvider(vector_config["provider"]),
            config=vector_config,
            embedding_service=self.embedding_service
        )
        
        self.semantic_search = SemanticSearchEngine(
            vector_db=self.vector_db,
            embedding_service=self.embedding_service
        )
        
        self.semantic_cache = SemanticCacheManager(
            vector_db=self.vector_db,
            embedding_service=self.embedding_service
        )
        
        self.knowledge_graph = KnowledgeGraphIntegration(
            vector_db=self.vector_db,
            embedding_service=self.embedding_service
        )
    
    async def vector_enhanced_search(self, 
                                   query: str,
                                   traditional_results: List[Any]) -> Dict[str, Any]:
        """Enhance traditional search results with vector capabilities"""
        
        # 1. Check semantic cache first
        cached_result = await self.semantic_cache.get_similar_cached_result(query)
        if cached_result:
            return {
                "type": "semantic_cache_hit",
                "result": cached_result,
                "processing_time": 0.1
            }
        
        # 2. Perform semantic search
        semantic_results = await self.semantic_search.enhanced_search(
            query=query,
            search_type="hybrid",
            max_results=20
        )
        
        # 3. Entity-based search
        entity_results = await self.knowledge_graph.semantic_entity_search(
            query=query,
            entity_types=["PERSON", "ORG", "LOCATION"]
        )
        
        # 4. Combine and enhance traditional results
        enhanced_results = await self._combine_all_results(
            traditional_results,
            semantic_results,
            entity_results,
            query
        )
        
        # 5. Cache the enhanced results
        await self.semantic_cache.cache_query_result(
            query=query,
            result=enhanced_results,
            ttl_hours=24
        )
        
        return {
            "type": "vector_enhanced",
            "result": enhanced_results,
            "semantic_matches": len(semantic_results),
            "entity_matches": len(entity_results),
            "enhancement_applied": True
        }
    
    async def _combine_all_results(self,
                                 traditional_results: List[Any],
                                 semantic_results: List[SemanticSearchResult],
                                 entity_results: List[Dict[str, Any]],
                                 query: str) -> Dict[str, Any]:
        """Combine all types of search results intelligently"""
        
        # Score and merge results
        combined_sources = []
        
        # Add traditional results
        for result in traditional_results[:10]:
            combined_sources.append({
                "url": getattr(result, 'url', ''),
                "title": getattr(result, 'title', ''),
                "content": getattr(result, 'snippet', ''),
                "score": getattr(result, 'relevance_score', 0.5),
                "type": "traditional",
                "source_engine": getattr(result, 'source_engine', 'unknown')
            })
        
        # Add semantic results
        for result in semantic_results[:10]:
            combined_sources.append({
                "url": result.source_url or '',
                "title": result.metadata.get('title', ''),
                "content": result.content,
                "score": result.similarity_score,
                "type": "semantic",
                "semantic_similarity": result.similarity_score
            })
        
        # Generate enhanced answer using all sources
        enhanced_answer = await self._generate_enhanced_answer(
            query, 
            combined_sources, 
            entity_results
        )
        
        # Remove duplicates and rank
        unique_sources = self._deduplicate_sources(combined_sources)
        ranked_sources = sorted(unique_sources, key=lambda x: x['score'], reverse=True)
        
        return {
            "answer": enhanced_answer,
            "sources": ranked_sources[:15],
            "entity_insights": entity_results[:5],
            "semantic_enhancement": True,
            "total_sources_analyzed": len(combined_sources)
        }
    
    def _deduplicate_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate sources based on URL similarity"""
        
        unique_sources = []
        seen_urls = set()
        
        for source in sources:
            url = source.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(source)
        
        return unique_sources
