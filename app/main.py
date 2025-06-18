# app/main.py - FastAPI Application Entry Point
"""
LangGraph Search System - Main Application
Advanced AI-powered search with multi-agent workflows
"""

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
import uvicorn

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

# Prometheus metrics
from prometheus_client import make_asgi_app, Counter, Histogram, Gauge
import time

# Core application imports
from app.core.config import get_config, ConfigurationError
from app.core.logging import setup_logging
from app.database.connection import DatabaseManager
from app.cache.redis_manager import RedisManager
from app.security.auth import get_current_user, setup_security
from app.security.rate_limiting import RateLimiter
from app.security.compliance_framework import SecurityComplianceEngine

# API endpoints
from app.api.endpoints import (
    search_v2,
    health,
    admin,
    analytics,
    auth as auth_routes,
    vector_search,
    workflow_management
)

# LangGraph workflows
from app.langgraph.workflows.search_workflow import MasterSearchWorkflow
from app.langgraph.workflows.workflow_manager import WorkflowManager

# Services
from app.services.search_service import SearchService
from app.services.analytics_service import AnalyticsService
from app.ml.model_management import ModelManagementService

# Initialize logging
logger = logging.getLogger(__name__)

# Metrics
REQUEST_COUNT = Counter('langgraph_search_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('langgraph_search_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('langgraph_search_active_connections', 'Active connections')
SEARCH_QUALITY_SCORE = Histogram('langgraph_search_quality_score', 'Search quality scores')
CACHE_HIT_RATE = Gauge('langgraph_search_cache_hit_rate', 'Cache hit rate')

class ApplicationState:
    """Global application state management"""
    def __init__(self):
        self.config = None
        self.db_manager = None
        self.redis_manager = None
        self.search_workflow = None
        self.workflow_manager = None
        self.search_service = None
        self.analytics_service = None
        self.model_service = None
        self.security_engine = None
        self.rate_limiter = None
        self.is_ready = False

# Global application state
app_state = ApplicationState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("🚀 Starting LangGraph Search System...")
    
    try:
        # Load configuration
        logger.info("📋 Loading configuration...")
        app_state.config = get_config()
        
        # Setup logging
        setup_logging(app_state.config.logging.level)
        
        # Initialize database
        logger.info("🗄️  Initializing database...")
        app_state.db_manager = DatabaseManager(app_state.config.database)
        await app_state.db_manager.initialize()
        
        # Initialize Redis
        logger.info("⚡ Initializing Redis...")
        app_state.redis_manager = RedisManager(app_state.config.redis)
        await app_state.redis_manager.initialize()
        
        # Initialize security
        logger.info("🔒 Initializing security...")
        app_state.security_engine = SecurityComplianceEngine(app_state.config.security)
        app_state.rate_limiter = RateLimiter(app_state.redis_manager)
        
        # Initialize LangGraph workflows
        logger.info("🕸️  Initializing LangGraph workflows...")
        app_state.search_workflow = MasterSearchWorkflow()
        app_state.workflow_manager = WorkflowManager()
        
        # Initialize services
        logger.info("🔧 Initializing services...")
        app_state.search_service = SearchService(
            workflow=app_state.search_workflow,
            db_manager=app_state.db_manager,
            redis_manager=app_state.redis_manager
        )
        
        app_state.analytics_service = AnalyticsService(
            db_manager=app_state.db_manager,
            redis_manager=app_state.redis_manager
        )
        
        app_state.model_service = ModelManagementService(
            config=app_state.config.ml
        )
        
        # Health check
        logger.info("🏥 Running startup health checks...")
        await run_startup_health_checks()
        
        app_state.is_ready = True
        logger.info("✅ LangGraph Search System started successfully!")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to start application: {e}")
        raise
    
    finally:
        # Cleanup
        logger.info("🧹 Shutting down LangGraph Search System...")
        
        if app_state.db_manager:
            await app_state.db_manager.close()
        
        if app_state.redis_manager:
            await app_state.redis_manager.close()
        
        logger.info("👋 LangGraph Search System shutdown complete")

async def run_startup_health_checks():
    """Run comprehensive startup health checks"""
    checks = {
        "database": app_state.db_manager.health_check(),
        "redis": app_state.redis_manager.health_check(),
        "search_workflow": app_state.search_workflow.health_check(),
        "external_apis": check_external_apis()
    }
    
    for check_name, check_coro in checks.items():
        try:
            result = await check_coro
            if result.get("healthy", False):
                logger.info(f"  ✅ {check_name}: healthy")
            else:
                logger.warning(f"  ⚠️  {check_name}: {result.get('message', 'unhealthy')}")
        except Exception as e:
            logger.error(f"  ❌ {check_name}: {e}")

async def check_external_apis():
    """Check external API connectivity"""
    # Implementation would check search engines and LLM providers
    return {"healthy": True, "message": "External APIs accessible"}

# Create FastAPI application
app = FastAPI(
    title="LangGraph Search System",
    description="Advanced AI-powered search with multi-agent workflows",
    version="2.0.0-langgraph",
    docs_url=None,  # Custom docs endpoint
    redoc_url=None,  # Custom redoc endpoint
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Middleware setup
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

async def add_request_metrics(request: Request, call_next):
    """Add request metrics and timing"""
    start_time = time.time()
    
    # Increment active connections
    ACTIVE_CONNECTIONS.inc()
    
    try:
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        REQUEST_DURATION.observe(duration)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        # Add timing header
        response.headers["X-Process-Time"] = str(duration)
        
        return response
    
    finally:
        ACTIVE_CONNECTIONS.dec()

# Add middleware (order matters!)
app.middleware("http")(add_security_headers)
app.middleware("http")(add_request_metrics)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Exception handlers
@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError):
    logger.error(f"Configuration error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Configuration error", "detail": str(exc)}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )

# Dependency injection
async def get_search_service():
    """Get search service dependency"""
    if not app_state.is_ready:
        raise HTTPException(status_code=503, detail="Service not ready")
    return app_state.search_service

async def get_analytics_service():
    """Get analytics service dependency"""
    if not app_state.is_ready:
        raise HTTPException(status_code=503, detail="Service not ready")
    return app_state.analytics_service

# Include API routers
app.include_router(
    search_v2.router,
    prefix="/api/v2",
    tags=["search"],
    dependencies=[Depends(app_state.rate_limiter.check_rate_limit)]
)

app.include_router(
    health.router,
    prefix="/api/v2",
    tags=["health"]
)

app.include_router(
    admin.router,
    prefix="/api/v2/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    analytics.router,
    prefix="/api/v2/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    auth_routes.router,
    prefix="/api/v2/auth",
    tags=["authentication"]
)

app.include_router(
    vector_search.router,
    prefix="/api/v2/vector",
    tags=["vector-search"],
    dependencies=[Depends(app_state.rate_limiter.check_rate_limit)]
)

app.include_router(
    workflow_management.router,
    prefix="/api/v2/workflows",
    tags=["workflows"],
    dependencies=[Depends(get_current_user)]
)

# Custom documentation endpoints
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )

# Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="LangGraph Search System API",
        version="2.0.0-langgraph",
        description="""
        ## Advanced AI-Powered Search System
        
        This API provides intelligent search capabilities using LangGraph workflows and multi-agent coordination.
        
        ### Features
        - **Adaptive Query Routing**: Automatic complexity-based routing
        - **Multi-Agent Workflows**: Specialized agents for different tasks
        - **Real-time Streaming**: Server-sent events for live updates
        - **Vector Search**: Semantic similarity search
        - **Quality Assurance**: Built-in quality gates
        - **Analytics**: Comprehensive search analytics
        
        ### Authentication
        Most endpoints require authentication via Bearer token.
        
        ### Rate Limiting
        Rate limits apply based on your subscription tier.
        """,
        routes=app.routes,
    )
    
    # Add custom security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Static files (if needed)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with system information"""
    return {
        "service": "LangGraph Search System",
        "version": "2.0.0-langgraph",
        "status": "operational" if app_state.is_ready else "starting",
        "docs": "/docs",
        "health": "/api/v2/health",
        "metrics": "/metrics"
    }

# Development server
if __name__ == "__main__":
    config = get_config()
    
    uvicorn.run(
        "app.main:app",
        host=config.server.get("host", "0.0.0.0"),
        port=config.server.get("port", 8000),
        reload=config.server.get("reload", False),
        workers=config.server.get("workers", 1),
        log_level=config.logging.level.lower(),
        access_log=True
    )