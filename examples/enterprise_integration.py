# examples/enterprise_integration.py - Enterprise Integration Patterns

class EnterpriseSearchIntegration:
    """Enterprise-grade integration examples"""
    
    def __init__(self):
        self.search_workflow = OptimizedSearchWorkflow()
        self.auth_service = EnterpriseAuthService()
        self.audit_logger = AuditLogger()
        self.compliance_checker = ComplianceChecker()
    
    async def enterprise_search_handler(self, request: EnterpriseSearchRequest) -> EnterpriseSearchResponse:
        """Enterprise search with full compliance and audit trail"""
        
        # 1. Authentication & Authorization
        user_context = await self.auth_service.authenticate_and_authorize(
            token=request.auth_token,
            required_permissions=["search:execute", "data:read"]
        )
        
        # 2. Compliance checking
        compliance_result = await self.compliance_checker.validate_query(
            query=request.query,
            user_context=user_context,
            data_classification_level=request.data_classification
        )
        
        if not compliance_result.approved:
            await self.audit_logger.log_compliance_violation(
                user=user_context.user_id,
                query=request.query,
                violation=compliance_result.violation_reason
            )
            raise ComplianceViolationError(compliance_result.violation_reason)
        
        # 3. Execute search with enterprise features
        search_state = AdvancedSearchState(
            query=request.query,
            user_id=user_context.user_id,
            session_id=request.session_id,
            enterprise_context={
                "department": user_context.department,
                "security_clearance": user_context.security_clearance,
                "data_access_policies": user_context.data_policies
            },
            compliance_requirements=compliance_result.requirements
        )
        
        # 4. Execute with audit trail
        start_time = datetime.now()
        
        try:
            result = await self.search_workflow.execute_optimized_search(search_state)
            
            # 5. Post-process for enterprise requirements
            enterprise_result = await self._apply_enterprise_policies(result, user_context)
            
            # 6. Audit logging
            await self.audit_logger.log_search_execution(
                user_id=user_context.user_id,
                query=request.query,
                result_count=len(enterprise_result.sources),
                execution_time=(datetime.now() - start_time).total_seconds(),
                compliance_level=request.data_classification,
                success=True
            )
            
            return EnterpriseSearchResponse(
                query=request.query,
                answer=enterprise_result.answer,
                sources=enterprise_result.sources,
                confidence_score=enterprise_result.confidence_score,
                compliance_metadata=enterprise_result.compliance_metadata,
                audit_trail_id=enterprise_result.audit_trail_id
            )
            
        except Exception as e:
            # Error audit logging
            await self.audit_logger.log_search_error(
                user_id=user_context.user_id,
                query=request.query,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds()
            )
            raise
    
    async def _apply_enterprise_policies(self, result, user_context):
        """Apply enterprise data policies to results"""
        
        # Filter sources based on user access
        filtered_sources = []
        for source in result.sources:
            if await self._user_can_access_source(source, user_context):
                filtered_sources.append(source)
        
        # Redact sensitive information
        redacted_answer = await self._redact_sensitive_content(
            result.answer, 
            user_context.security_clearance
        )
        
        return EnterpriseSearchResult(
            answer=redacted_answer,
            sources=filtered_sources,
            confidence_score=result.confidence_score,
            compliance_metadata={
                "data_classification": "internal",
                "access_level": user_context.security_clearance,
                "redaction_applied": len(result.sources) != len(filtered_sources)
            },
            audit_trail_id=f"audit_{uuid.uuid4().hex[:8]}"
        )

# examples/microservices_integration.py - Microservices Integration

class MicroservicesSearchGateway:
    """Search gateway for microservices architecture"""
    
    def __init__(self):
        self.service_registry = ServiceRegistry()
        self.circuit_breaker = CircuitBreaker()
        self.load_balancer = LoadBalancer()
        self.message_bus = MessageBus()
    
    async def federated_search(self, query: str, services: List[str]) -> FederatedSearchResult:
        """Execute federated search across multiple services"""
        
        # 1. Discover available search services
        available_services = await self.service_registry.get_healthy_services(
            service_types=services,
            capabilities=["search", "semantic_analysis"]
        )
        
        # 2. Distribute query across services
        search_tasks = []
        for service in available_services:
            if self.circuit_breaker.is_service_healthy(service.name):
                task = self._search_service(service, query)
                search_tasks.append(task)
        
        # 3. Execute searches in parallel with timeout
        service_results = await asyncio.gather(
            *search_tasks, 
            return_exceptions=True
        )
        
        # 4. Aggregate and rank results
        aggregated_results = await self._aggregate_service_results(
            service_results, 
            query
        )
        
        # 5. Publish results to message bus for other services
        await self.message_bus.publish(
            topic="search.results",
            message={
                "query": query,
                "results": aggregated_results,
                "timestamp": datetime.now().isoformat(),
                "source_services": [s.name for s in available_services]
            }
        )
        
        return aggregated_results
    
    async def _search_service(self, service: ServiceInfo, query: str) -> ServiceSearchResult:
        """Search individual microservice with resilience patterns"""
        
        # Apply circuit breaker pattern
        with self.circuit_breaker.context(service.name):
            # Load balance across service instances
            endpoint = await self.load_balancer.get_endpoint(service.name)
            
            # Execute search with timeout and retry
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        f"{endpoint}/search",
                        json={"query": query},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        
                        if response.status == 200:
                            result = await response.json()
                            return ServiceSearchResult(
                                service_name=service.name,
                                results=result["results"],
                                confidence=result.get("confidence", 0.5),
                                processing_time=result.get("processing_time", 0),
                                success=True
                            )
                        else:
                            return ServiceSearchResult(
                                service_name=service.name,
                                error=f"HTTP {response.status}",
                                success=False
                            )
                            
                except asyncio.TimeoutError:
                    return ServiceSearchResult(
                        service_name=service.name,
                        error="Request timeout",
                        success=False
                    )

# examples/event_driven_integration.py - Event-Driven Architecture

class EventDrivenSearchSystem:
    """Event-driven search system with real-time updates"""
    
    def __init__(self):
        self.event_bus = EventBus()
        self.search_cache = AdvancedCacheManager()
        self.workflow_engine = OptimizedSearchWorkflow()
        
        # Subscribe to relevant events
        self.event_bus.subscribe("content.updated", self._handle_content_update)
        self.event_bus.subscribe("user.preference.changed", self._handle_preference_change)
        self.event_bus.subscribe("search.feedback", self._handle_search_feedback)
    
    async def reactive_search(self, query: str, user_id: str) -> ReactiveSearchResult:
        """Reactive search that adapts based on real-time events"""
        
        # 1. Check for real-time context updates
        recent_events = await self.event_bus.get_recent_events(
            user_id=user_id,
            event_types=["content.updated", "trending.topic"],
            time_window=timedelta(hours=1)
        )
        
        # 2. Adjust search strategy based on events
        search_context = self._build_search_context(query, recent_events)
        
        # 3. Execute search with reactive context
        search_state = AdvancedSearchState(
            query=query,
            user_id=user_id,
            reactive_context=search_context,
            real_time_events=recent_events
        )
        
        result = await self.workflow_engine.execute_optimized_search(search_state)
        
        # 4. Publish search completion event
        await self.event_bus.publish(
            event_type="search.completed",
            event_data={
                "query": query,
                "user_id": user_id,
                "confidence": result.confidence_score,
                "processing_time": result.processing_time,
                "result_count": len(result.sources)
            }
        )
        
        return ReactiveSearchResult(
            standard_result=result,
            real_time_insights=search_context["insights"],
            trending_topics=search_context["trending"],
            personalized_adjustments=search_context["personalizations"]
        )
    
    async def _handle_content_update(self, event: ContentUpdateEvent):
        """Handle content update events"""
        
        # Invalidate related cache entries
        related_queries = await self._find_related_cached_queries(event.content_topic)
        
        for query_hash in related_queries:
            await self.search_cache.invalidate(query_hash)
        
        # Trigger re-indexing if needed
        if event.content_importance > 0.8:
            await self._trigger_reindexing(event.content_id)
    
    async def _handle_search_feedback(self, event: SearchFeedbackEvent):
        """Handle user feedback on search results"""
        
        if event.feedback_type == "poor_quality":
            # Adjust search parameters for similar queries
            await self._adjust_search_parameters(
                query_pattern=event.query_pattern,
                adjustment_type="increase_quality_threshold"
            )
        elif event.feedback_type == "too_slow":
            # Optimize for speed
            await self._adjust_search_parameters(
                query_pattern=event.query_pattern,
                adjustment_type="optimize_for_speed"
            )

# Start command for production
if __name__ == "__main__":
    import uvicorn
    
    # Production configuration
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,
        log_level="info",
        access_log=True,
        reload=False,
        loop="uvloop"  # High-performance event loop
    )
