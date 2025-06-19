# app/main.py - Fixed FastAPI Application
"""
LangGraph Search System - Main Application
Advanced AI-powered search with multi-agent workflows
"""

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
import uvicorn

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

# Prometheus metrics
try:
    from prometheus_client import make_asgi_app, Counter, Histogram, Gauge
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

import time

# Core application imports with error handling
try:
    from app.core.config import get_config, ConfigurationError
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    get_config = lambda: type('Config', (), {
        'app': {'name': 'LangGraph Search', 'version': '2.0.0'},
        'server': {'host': '0.0.0.0', 'port': 8000, 'reload': False, 'workers': 1},
        'logging': type('Logging', (), {'level': 'INFO'})()
    })()

try:
    from app.core.logging import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(level=logging.INFO)

try:
    from app.database.connection import DatabaseManager
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

try:
    from app.cache.redis_manager import RedisManager
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Import available API endpoints
try:
    from app.api.endpoints import search_v2
    SEARCH_V2_AVAILABLE = True
except ImportError:
    SEARCH_V2_AVAILABLE = False

# Import other endpoints with fallbacks
try:
    from app.api.endpoints import health, admin, analytics, auth as auth_routes
    from app.api.endpoints import vector_search, workflow_management
except ImportError:
    # Create mock endpoints for missing modules
    health = admin = analytics = auth_routes = vector_search = workflow_management = None

# Optional services
try:
    from app.langgraph.workflows.search_workflow import MasterSearchWorkflow
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

logger = logging.getLogger(__name__)

# Application state
class AppState:
    def __init__(self):
        self.config = get_config() if CONFIG_AVAILABLE else None
        self.db_manager: Optional[Any] = None
        self.redis_manager: Optional[Any] = None
        self.search_workflow: Optional[Any] = None
        self.is_ready = False

app_state = AppState()

# Metrics
if METRICS_AVAILABLE:
    REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
    REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
    ACTIVE_CONNECTIONS = Gauge('http_active_connections', 'Active HTTP connections')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    try:
        logger.info("🚀 Starting LangGraph Search System...")
        
        # Initialize database if available
        if DATABASE_AVAILABLE and hasattr(app_state.config, 'database'):
            try:
                logger.info("📊 Initializing database...")
                app_state.db_manager = DatabaseManager(app_state.config.database)
                await app_state.db_manager.initialize()
            except Exception as e:
                logger.warning(f"Database initialization failed: {e}")
        
        # Initialize Redis if available
        if REDIS_AVAILABLE and hasattr(app_state.config, 'redis'):
            try:
                logger.info("⚡ Initializing Redis...")
                app_state.redis_manager = RedisManager(app_state.config.redis)
                await app_state.redis_manager.initialize()
            except Exception as e:
                logger.warning(f"Redis initialization failed: {e}")
        
        # Initialize LangGraph workflows if available
        if LANGGRAPH_AVAILABLE:
            try:
                logger.info("🕸️  Initializing LangGraph workflows...")
                app_state.search_workflow = MasterSearchWorkflow()
            except Exception as e:
                logger.warning(f"LangGraph initialization failed: {e}")
        
        app_state.is_ready = True
        logger.info("✅ LangGraph Search System started successfully!")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Failed to start application: {e}")
        raise
    
    finally:
        # Cleanup
        logger.info("🧹 Shutting down LangGraph Search System...")
        
        if app_state.db_manager and hasattr(app_state.db_manager, 'close'):
            try:
                await app_state.db_manager.close()
            except:
                pass
        
        if app_state.redis_manager and hasattr(app_state.redis_manager, 'close'):
            try:
                await app_state.redis_manager.close()
            except:
                pass
        
        logger.info("👋 LangGraph Search System shutdown complete")

# Create FastAPI application
app = FastAPI(
    title="LangGraph Search System",
    description="Advanced AI-powered search with multi-agent workflows",
    version="2.0.0-langgraph",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Middleware setup
if METRICS_AVAILABLE:
    async def add_request_metrics(request: Request, call_next):
        """Add request metrics and timing"""
        start_time = time.time()
        ACTIVE_CONNECTIONS.inc()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            REQUEST_DURATION.observe(duration)
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()
            response.headers["X-Process-Time"] = str(duration)
            return response
        finally:
            ACTIVE_CONNECTIONS.dec()
    
    app.middleware("http")(add_request_metrics)

# Security headers middleware
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

app.middleware("http")(add_security_headers)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API routers
if SEARCH_V2_AVAILABLE:
    app.include_router(search_v2.router, prefix="/api/v2", tags=["search"])

# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with system information"""
    return {
        "service": "LangGraph Search System",
        "version": "2.0.0-langgraph",
        "status": "operational" if app_state.is_ready else "starting",
        "docs": "/docs",
        "health": "/health",
        "components": {
            "config": CONFIG_AVAILABLE,
            "database": DATABASE_AVAILABLE,
            "redis": REDIS_AVAILABLE,
            "search_v2": SEARCH_V2_AVAILABLE,
            "langgraph": LANGGRAPH_AVAILABLE,
            "metrics": METRICS_AVAILABLE
        }
    }

@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    checks = {
        "status": "healthy" if app_state.is_ready else "starting",
        "timestamp": time.time(),
        "components": {}
    }
    
    # Check database if available
    if app_state.db_manager and hasattr(app_state.db_manager, 'health_check'):
        try:
            db_health = await app_state.db_manager.health_check()
            checks["components"]["database"] = db_health
        except Exception as e:
            checks["components"]["database"] = {"healthy": False, "error": str(e)}
    
    # Check Redis if available
    if app_state.redis_manager and hasattr(app_state.redis_manager, 'health_check'):
        try:
            redis_health = await app_state.redis_manager.health_check()
            checks["components"]["redis"] = redis_health
        except Exception as e:
            checks["components"]["redis"] = {"healthy": False, "error": str(e)}
    
    return checks

# Prometheus metrics endpoint
if METRICS_AVAILABLE:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="LangGraph Search System",
        version="2.0.0-langgraph",
        description="""
        Advanced AI-powered search system with LangGraph workflows.
        
        ## Features
        - Multi-agent search workflows
        - Real-time analytics
        - Enterprise security
        - Vector search capabilities
        """,
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Development server
if __name__ == "__main__":
    config = get_config()
    
    uvicorn.run(
        "app.main:app",
        host=config.server.get("host", "0.0.0.0"),
        port=config.server.get("port", 8000),
        reload=config.server.get("reload", False),
        workers=config.server.get("workers", 1),
        log_level=config.logging.level.lower() if hasattr(config, 'logging') else 'info'
    )
