# LangGraph Advanced Search System

A sophisticated, production-ready AI search system built with LangGraph, featuring multi-agent workflows, real-time analytics, and enterprise-grade security.

## 🚀 Overview

This system leverages LangGraph's state-based workflow orchestration to provide intelligent search capabilities with adaptive routing, multi-round refinement, and collaborative agent coordination. It supports everything from simple factual queries to complex research workflows.

## 🏗️ Architecture

### Core Components

- **LangGraph Workflows**: Sophisticated multi-agent search patterns
- **Search Engines**: Multi-provider search (Brave, SerpAPI, ZenRows)
- **Analytics Engine**: Real-time monitoring and performance tracking
- **Security Framework**: Multi-compliance support (GDPR, CCPA, SOC2, HIPAA)
- **Multi-tenant Architecture**: Resource isolation and cost management
- **Vector Search**: Semantic search with embeddings

### Workflow Complexity Levels

```
SIMPLE      → Single-shot, fast response
ADAPTIVE    → Context-aware routing  
ITERATIVE   → Multi-round refinement
COLLABORATIVE → Multi-agent coordination
RESEARCH    → Deep investigative workflow
```

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- Redis 6.0+
- PostgreSQL 13+
- Docker & Docker Compose
- Kubernetes (for production)

### Environment Setup

```bash
# Clone repository
git clone <your-repo-url>
cd langgraph-search

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.langgraph.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Required API Keys

```bash
# Search APIs
BRAVE_SEARCH_API_KEY=your_brave_api_key
SERPAPI_API_KEY=your_serpapi_key
ZENROWS_API_KEY=your_zenrows_key

# LLM APIs  
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Infrastructure
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://user:password@localhost/langgraph_search
```

### Quick Start

```bash
# Start infrastructure services
docker-compose up -d redis postgres

# Run database migrations
python scripts/setup_database.py

# Start development server
uvicorn app.main:app --reload --port 8000

# Test the API
curl -X POST "http://localhost:8000/api/v2/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?", "max_results": 5}'
```

## 📡 API Reference

### Search Endpoint

**POST** `/api/v2/search`

```json
{
  "query": "Your search query",
  "max_results": 5,
  "workflow_complexity": "adaptive",
  "stream": false,
  "user_id": "optional_user_id"
}
```

**Response:**
```json
{
  "query": "What is machine learning?",
  "answer": "Machine learning is a subset of artificial intelligence...",
  "sources": [
    {
      "url": "https://example.com",
      "title": "Introduction to ML",
      "snippet": "Machine learning involves...",
      "relevance_score": 0.92
    }
  ],
  "confidence_score": 0.87,
  "processing_path": ["classified", "searched", "analyzed"],
  "query_type": "SIMPLE_FACTUAL",
  "response_time_ms": 1250
}
```

### Streaming Search

**POST** `/api/v2/search/stream`

Returns Server-Sent Events (SSE) for real-time updates:

```javascript
const eventSource = new EventSource('/api/v2/search/stream');
eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Search update:', data);
};
```

### Health Check

**GET** `/api/v2/health`

```json
{
  "status": "healthy",
  "components": {
    "query_enhancer": "healthy",
    "search_engine": "healthy", 
    "llm_analyzer": "healthy"
  },
  "version": "2.0.0-langgraph"
}
```

## 🏛️ Advanced Features

### Multi-Agent Workflows

The system uses specialized agents for different tasks:

- **Query Classifier**: Determines search complexity and routing
- **Query Enhancer**: Improves and expands search queries
- **Search Coordinator**: Orchestrates multiple search engines
- **Content Analyzer**: Processes and ranks search results
- **Response Synthesizer**: Generates comprehensive answers

### Adaptive Routing

Queries are automatically routed based on complexity:

```python
# Simple factual query → Fast single-shot response
"What is the capital of France?" → SIMPLE workflow

# Complex research query → Deep investigative workflow  
"Compare renewable energy policies across EU countries" → RESEARCH workflow
```

### Quality Assurance Gates

Built-in quality gates ensure high-quality responses:

1. **Initial Gate**: Validates strategy and resource allocation
2. **Intermediate Gate**: Checks progress and adjusts approach
3. **Final Gate**: Validates response quality and completeness

### Real-time Analytics

Monitor system performance in real-time:

- Query throughput and latency
- Search engine performance
- Cost per query optimization
- User satisfaction metrics
- Cache hit rates and optimization

## 🚀 Production Deployment

### Kubernetes Deployment

```bash
# Deploy to production
./scripts/deploy_production.sh v1.0.0 production

# Check deployment status
kubectl get pods -n langgraph-search

# View logs
kubectl logs -f deployment/langgraph-search-api -n langgraph-search
```

### Docker Compose (Development)

```bash
# Start full stack
docker-compose -f docker-compose.production.yml up -d

# Scale API instances
docker-compose -f docker-compose.production.yml up -d --scale api=3
```

### Environment Configuration

**Development:**
```bash
export ENVIRONMENT=development
export LOG_LEVEL=DEBUG
export ENABLE_TRACING=true
```

**Production:**
```bash
export ENVIRONMENT=production
export LOG_LEVEL=INFO
export ENABLE_TRACING=false
export ENABLE_METRICS=true
```

## 🧪 Testing

### Run Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test categories
pytest tests/unit/ -v           # Unit tests
pytest tests/integration/ -v    # Integration tests
pytest tests/performance/ -v    # Performance tests
```

### Load Testing

```bash
# Install load testing tools
pip install locust

# Run load tests
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## 🔒 Security & Compliance

### Supported Frameworks

- **GDPR**: EU data protection compliance
- **CCPA**: California privacy compliance  
- **SOC2**: Security and availability controls
- **HIPAA**: Healthcare data protection

### Security Features

- Role-based access control (RBAC)
- Data encryption at rest and in transit
- PII detection and anonymization
- Audit logging and compliance reporting
- Rate limiting and DDoS protection

### Enable Compliance Mode

```python
# In your configuration
COMPLIANCE_FRAMEWORKS = ["GDPR", "CCPA"]
ENABLE_PII_DETECTION = True
DATA_RETENTION_DAYS = 365
ENABLE_AUDIT_LOGGING = True
```

## 📊 Monitoring & Observability

### Metrics Dashboard

Access real-time metrics at:
- **Grafana**: `http://localhost:3000` (admin/admin)
- **Prometheus**: `http://localhost:9090`

### Key Metrics

- **Performance**: Response time, throughput, error rates
- **Business**: Cost per query, user satisfaction, revenue
- **Technical**: Cache hit rates, resource utilization
- **Quality**: Confidence scores, result relevance

### Alerting

Configure alerts for:
- High error rates (>5%)
- Slow response times (>5s)
- Low confidence scores (<0.6)
- Resource exhaustion
- Security incidents

## 🔧 Configuration

### Environment Variables

```bash
# Core Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=false

# Database
DATABASE_URL=postgresql://user:pass@localhost/db
REDIS_URL=redis://localhost:6379

# Search APIs
BRAVE_SEARCH_API_KEY=your_key
SERPAPI_API_KEY=your_key
ZENROWS_API_KEY=your_key

# LLM Configuration
OPENAI_API_KEY=your_key
DEFAULT_MODEL=gpt-4
MAX_TOKENS=2048

# Performance
CACHE_TTL=3600
MAX_CONCURRENT_REQUESTS=100
REQUEST_TIMEOUT=30

# Security
JWT_SECRET_KEY=your_secret
CORS_ORIGINS=["http://localhost:3000"]
RATE_LIMIT_PER_MINUTE=60

# Compliance
ENABLE_PII_DETECTION=true
DATA_RETENTION_DAYS=365
AUDIT_LOG_LEVEL=INFO
```

### Advanced Configuration

```yaml
# config/production.yml
search:
  engines:
    brave:
      enabled: true
      weight: 0.4
    serpapi:
      enabled: true  
      weight: 0.4
    zenrows:
      enabled: true
      weight: 0.2
  
  quality_gates:
    initial:
      strategy_validation: true
      resource_check: true
    final:
      confidence_threshold: 0.7
      source_diversity: 3

workflow:
  default_complexity: "adaptive"
  max_iterations: 5
  timeout_seconds: 30
  
analytics:
  sampling_rate: 0.1
  batch_size: 100
  flush_interval: 60
```

## 🚦 API Rate Limits

| Tier | Requests/minute | Concurrent | Features |
|------|----------------|------------|----------|
| Free | 60 | 5 | Basic search |
| Pro | 600 | 20 | Advanced workflows |
| Enterprise | Unlimited | 100 | All features |

## 🐛 Troubleshooting

### Common Issues

**Search returning empty results:**
```bash
# Check search engine health
curl http://localhost:8000/api/v2/health

# Verify API keys
echo $BRAVE_SEARCH_API_KEY
```

**High response times:**
```bash
# Check Redis connection
redis-cli ping

# Monitor resource usage  
kubectl top pods -n langgraph-search
```

**Database connection errors:**
```bash
# Check PostgreSQL status
pg_isready -h localhost -p 5432

# Test connection
psql $DATABASE_URL -c "SELECT 1;"
```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
export ENABLE_TRACING=true

# Start with verbose output
uvicorn app.main:app --reload --log-level debug
```

## 📝 Development

### Project Structure

```
app/
├── api/endpoints/          # API route handlers
├── langgraph/             # LangGraph workflows and agents
│   ├── workflows/         # Main workflow definitions  
│   ├── agents/           # Specialized agent implementations
│   ├── state/            # State management
│   └── advanced/         # Advanced patterns
├── services/             # Business logic services
├── analytics/            # Real-time analytics engine
├── security/             # Security and compliance
├── optimization/         # Performance optimization
└── vector/              # Vector search capabilities

tests/
├── unit/                # Unit tests
├── integration/         # Integration tests  
├── performance/         # Performance tests
└── load/               # Load testing

scripts/
├── deploy_production.sh  # Production deployment
├── setup_database.py    # Database initialization
└── migrate.py          # Database migrations
```

### Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Run tests: `pytest tests/ -v`
4. Commit changes: `git commit -m 'Add amazing feature'`
5. Push branch: `git push origin feature/amazing-feature`
6. Open Pull Request

### Code Quality

```bash
# Format code
black app/ tests/
isort app/ tests/

# Lint code  
flake8 app/ tests/
mypy app/

# Security check
bandit -r app/
```

## 📚 Documentation

- **API Documentation**: Available at `/docs` when running
- **Architecture Guide**: See `docs/architecture.md`
- **Deployment Guide**: See `docs/deployment.md`
- **Security Guide**: See `docs/security.md`

## 🆘 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions  
- **Documentation**: `/docs` endpoint
- **Health Check**: `/api/v2/health`

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- LangGraph team for the excellent workflow framework
- FastAPI for the high-performance web framework
- Contributors and community members

---

**Version**: 2.0.0-langgraph  
**Last Updated**: June 2025  
**Status**: Production Ready
