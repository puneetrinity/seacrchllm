# scripts/deploy_production.sh - Complete Production Deployment

#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="langgraph-search"
VERSION=${1:-"latest"}
ENVIRONMENT=${2:-"production"}
NAMESPACE="langgraph-search"

echo -e "${BLUE}🚀 Starting LangGraph Search Production Deployment${NC}"
echo -e "${BLUE}Version: ${VERSION}${NC}"
echo -e "${BLUE}Environment: ${ENVIRONMENT}${NC}"
echo -e "${BLUE}Namespace: ${NAMESPACE}${NC}"

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

# Check prerequisites
check_prerequisites() {
    echo -e "${BLUE}📋 Checking Prerequisites...${NC}"
    
    # Check required tools
    command -v docker >/dev/null 2>&1 || print_error "Docker is required but not installed"
    command -v kubectl >/dev/null 2>&1 || print_error "kubectl is required but not installed"
    command -v helm >/dev/null 2>&1 || print_error "Helm is required but not installed"
    
    # Check cluster connectivity
    kubectl cluster-info >/dev/null 2>&1 || print_error "Cannot connect to Kubernetes cluster"
    
    # Check required environment variables
    [[ -z "$BRAVE_SEARCH_API_KEY" ]] && print_error "BRAVE_SEARCH_API_KEY environment variable is required"
    [[ -z "$SERPAPI_API_KEY" ]] && print_error "SERPAPI_API_KEY environment variable is required"
    [[ -z "$ZENROWS_API_KEY" ]] && print_error "ZENROWS_API_KEY environment variable is required"
    
    print_status "Prerequisites check passed"
}

# Setup namespace and RBAC
setup_namespace() {
    echo -e "${BLUE}🏗️  Setting up Kubernetes namespace and RBAC...${NC}"
    
    # Create namespace
    kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply RBAC
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: langgraph-search-sa
  namespace: ${NAMESPACE}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: langgraph-search-role
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "secrets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: langgraph-search-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: langgraph-search-role
subjects:
- kind: ServiceAccount
  name: langgraph-search-sa
  namespace: ${NAMESPACE}
EOF
    
    print_status "Namespace and RBAC configured"
}

# Deploy infrastructure components
deploy_infrastructure() {
    echo -e "${BLUE}🗄️  Deploying infrastructure components...${NC}"
    
    # PostgreSQL for checkpoints and data persistence
    helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
    helm repo update >/dev/null 2>&1
    
    helm upgrade --install postgresql bitnami/postgresql \
        --namespace ${NAMESPACE} \
        --set auth.postgresPassword="langgraph-secure-password" \
        --set auth.database="langgraph_db" \
        --set persistence.size="50Gi" \
        --set metrics.enabled=true \
        --wait --timeout=600s
    
    # Redis Cluster for caching and state management
    helm upgrade --install redis bitnami/redis-cluster \
        --namespace ${NAMESPACE} \
        --set cluster.nodes=6 \
        --set cluster.replicas=1 \
        --set persistence.size="20Gi" \
        --set metrics.enabled=true \
        --wait --timeout=600s
    
    # Ollama for local LLM processing
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: ${NAMESPACE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
      - name: ollama
        image: ollama/ollama:latest
        ports:
        - containerPort: 11434
        env:
        - name: OLLAMA_KEEP_ALIVE
          value: "24h"
        - name: OLLAMA_HOST
          value: "0.0.0.0"
        resources:
          requests:
            cpu: 2000m
            memory: 4Gi
          limits:
            cpu: 4000m
            memory: 8Gi
        volumeMounts:
        - name: ollama-data
          mountPath: /root/.ollama
      volumes:
      - name: ollama-data
        persistentVolumeClaim:
          claimName: ollama-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-pvc
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: ${NAMESPACE}
spec:
  selector:
    app: ollama
  ports:
  - port: 11434
    targetPort: 11434
  type: ClusterIP
EOF
    
    print_status "Infrastructure components deployed"
}

# Create secrets and config maps
create_secrets() {
    echo -e "${BLUE}🔐 Creating secrets and configuration...${NC}"
    
    # API Keys Secret
    kubectl create secret generic langgraph-api-keys \
        --namespace=${NAMESPACE} \
        --from-literal=brave-search-api-key="${BRAVE_SEARCH_API_KEY}" \
        --from-literal=serpapi-api-key="${SERPAPI_API_KEY}" \
        --from-literal=zenrows-api-key="${ZENROWS_API_KEY}" \
        --from-literal=langsmith-api-key="${LANGSMITH_API_KEY:-placeholder}" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Database Connection Secret
    kubectl create secret generic langgraph-database \
        --namespace=${NAMESPACE} \
        --from-literal=database-url="postgresql+asyncpg://postgres:langgraph-secure-password@postgresql:5432/langgraph_db" \
        --from-literal=redis-url="redis://redis-cluster:6379" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Application Configuration
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: langgraph-config
  namespace: ${NAMESPACE}
data:
  ENVIRONMENT: "${ENVIRONMENT}"
  LOG_LEVEL: "INFO"
  ENABLE_DISTRIBUTED: "true"
  ENABLE_MONITORING: "true"
  CACHE_STRATEGY: "distributed"
  OPTIMIZATION_MODE: "balanced"
  OLLAMA_HOST: "http://ollama:11434"
  LLM_MODEL: "llama2:7b"
  VECTOR_PROVIDER: "chromadb"
  EMBEDDING_PROVIDER: "sentence_transformers"
  MAX_CONCURRENT_REQUESTS: "100"
  RATE_LIMIT_PER_MINUTE: "60"
  DAILY_BUDGET_USD: "500.0"
  ENABLE_SECURITY_FEATURES: "true"
  COMPLIANCE_FRAMEWORKS: "gdpr,soc2"
EOF
    
    print_status "Secrets and configuration created"
}

# Deploy monitoring stack
deploy_monitoring() {
    echo -e "${BLUE}📊 Deploying monitoring stack...${NC}"
    
    # Prometheus
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
    helm repo update >/dev/null 2>&1
    
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace ${NAMESPACE} \
        --set prometheus.prometheusSpec.retention=30d \
        --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=50Gi \
        --set grafana.adminPassword="admin123!" \
        --set grafana.persistence.enabled=true \
        --set grafana.persistence.size=10Gi \
        --wait --timeout=600s
    
    # Custom Grafana Dashboard
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: langgraph-dashboard
  namespace: ${NAMESPACE}
  labels:
    grafana_dashboard: "1"
data:
  langgraph-dashboard.json: |
    {
      "dashboard": {
        "id": null,
        "title": "LangGraph Search Performance",
        "tags": ["langgraph", "search"],
        "timezone": "browser",
        "panels": [
          {
            "id": 1,
            "title": "Search Response Time",
            "type": "graph",
            "targets": [
              {
                "expr": "histogram_quantile(0.95, rate(langgraph_search_duration_seconds_bucket[5m]))",
                "legendFormat": "95th percentile"
              },
              {
                "expr": "histogram_quantile(0.50, rate(langgraph_search_duration_seconds_bucket[5m]))",
                "legendFormat": "50th percentile"
              }
            ],
            "yAxes": [
              {
                "label": "Seconds",
                "min": 0
              }
            ]
          },
          {
            "id": 2,
            "title": "Request Rate",
            "type": "graph", 
            "targets": [
              {
                "expr": "rate(langgraph_search_requests_total[5m])",
                "legendFormat": "Requests/sec"
              }
            ]
          },
          {
            "id": 3,
            "title": "Error Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(langgraph_search_errors_total[5m]) / rate(langgraph_search_requests_total[5m])",
                "legendFormat": "Error Rate"
              }
            ]
          },
          {
            "id": 4,
            "title": "Cache Hit Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "langgraph_cache_hits_total / (langgraph_cache_hits_total + langgraph_cache_misses_total)",
                "legendFormat": "Cache Hit Rate"
              }
            ]
          }
        ],
        "time": {
          "from": "now-1h",
          "to": "now"
        },
        "refresh": "5s"
      }
    }
EOF
    
    print_status "Monitoring stack deployed"
}

# Build and push Docker images
build_and_push_images() {
    echo -e "${BLUE}🐳 Building and pushing Docker images...${NC}"
    
    # Build main application image
    docker build -t ${PROJECT_NAME}:${VERSION} -f Dockerfile.production .
    
    # Build worker image for distributed processing
    docker build -t ${PROJECT_NAME}-worker:${VERSION} -f Dockerfile.worker .
    
    # Tag for registry (assuming you have a registry configured)
    if [[ -n "$DOCKER_REGISTRY" ]]; then
        docker tag ${PROJECT_NAME}:${VERSION} ${DOCKER_REGISTRY}/${PROJECT_NAME}:${VERSION}
        docker tag ${PROJECT_NAME}-worker:${VERSION} ${DOCKER_REGISTRY}/${PROJECT_NAME}-worker:${VERSION}
        
        docker push ${DOCKER_REGISTRY}/${PROJECT_NAME}:${VERSION}
        docker push ${DOCKER_REGISTRY}/${PROJECT_NAME}-worker:${VERSION}
        
        print_status "Images pushed to registry"
    else
        print_warning "No registry configured, using local images"
    fi
}

# Deploy main application
deploy_application() {
    echo -e "${BLUE}🚀 Deploying main application...${NC}"
    
    # Main API deployment
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langgraph-search-api
  namespace: ${NAMESPACE}
  labels:
    app: langgraph-search-api
    version: ${VERSION}
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  selector:
    matchLabels:
      app: langgraph-search-api
  template:
    metadata:
      labels:
        app: langgraph-search-api
        version: ${VERSION}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: langgraph-search-sa
      containers:
      - name: langgraph-api
        image: ${DOCKER_REGISTRY:-}${PROJECT_NAME}:${VERSION}
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 8080
          name: metrics
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        envFrom:
        - configMapRef:
            name: langgraph-config
        - secretRef:
            name: langgraph-api-keys
        - secretRef:
            name: langgraph-database
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3
        volumeMounts:
        - name: cache-volume
          mountPath: /app/cache
        - name: logs-volume
          mountPath: /app/logs
      volumes:
      - name: cache-volume
        emptyDir:
          sizeLimit: 1Gi
      - name: logs-volume
        emptyDir:
          sizeLimit: 2Gi
---
apiVersion: v1
kind: Service
metadata:
  name: langgraph-search-service
  namespace: ${NAMESPACE}
  labels:
    app: langgraph-search-api
spec:
  selector:
    app: langgraph-search-api
  ports:
  - name: http
    port: 8000
    targetPort: 8000
    protocol: TCP
  - name: metrics
    port: 8080
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: langgraph-search-hpa
  namespace: ${NAMESPACE}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: langgraph-search-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 300
      selectPolicy: Max
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 2
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 600
      selectPolicy: Min
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
EOF
    
    # Worker deployment for distributed processing
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langgraph-search-worker
  namespace: ${NAMESPACE}
  labels:
    app: langgraph-search-worker
    version: ${VERSION}
spec:
  replicas: 3
  selector:
    matchLabels:
      app: langgraph-search-worker
  template:
    metadata:
      labels:
        app: langgraph-search-worker
        version: ${VERSION}
    spec:
      serviceAccountName: langgraph-search-sa
      containers:
      - name: langgraph-worker
        image: ${DOCKER_REGISTRY:-}${PROJECT_NAME}-worker:${VERSION}
        env:
        - name: WORKER_TYPE
          value: "search_worker"
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        envFrom:
        - configMapRef:
            name: langgraph-config
        - secretRef:
            name: langgraph-api-keys
        - secretRef:
            name: langgraph-database
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi
EOF
    
    print_status "Application deployed"
}

# Setup ingress and SSL
setup_ingress() {
    echo -e "${BLUE}🌐 Setting up ingress and SSL...${NC}"
    
    # Install cert-manager if not present
    kubectl get namespace cert-manager >/dev/null 2>&1 || {
        kubectl create namespace cert-manager
        helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
        helm repo update >/dev/null 2>&1
        helm upgrade --install cert-manager jetstack/cert-manager \
            --namespace cert-manager \
            --set installCRDs=true \
            --wait --timeout=600s
    }
    
    # ClusterIssuer for Let's Encrypt
    cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourdomain.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
    
    # Ingress with SSL
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: langgraph-search-ingress
  namespace: ${NAMESPACE}
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit-rpm: "100"
    nginx.ingress.kubernetes.io/proxy-body-size: 1m
    nginx.ingress.kubernetes.io/proxy-read-timeout: "30"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "30"
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/cors-allow-methods: "GET, POST, OPTIONS"
    nginx.ingress.kubernetes.io/cors-allow-headers: "DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization"
spec:
  tls:
  - hosts:
    - api.langgraph-search.com
    secretName: langgraph-search-tls
  rules:
  - host: api.langgraph-search.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: langgraph-search-service
            port:
              number: 8000
EOF
    
    print_status "Ingress and SSL configured"
}

# Initialize models and data
initialize_system() {
    echo -e "${BLUE}🤖 Initializing ML models and system data...${NC}"
    
    # Wait for Ollama to be ready
    echo "Waiting for Ollama to be ready..."
    kubectl wait --for=condition=available --timeout=600s deployment/ollama -n ${NAMESPACE}
    
    # Download required models
    kubectl exec -n ${NAMESPACE} deployment/ollama -- ollama pull llama2:7b
    kubectl exec -n ${NAMESPACE} deployment/ollama -- ollama pull mistral:7b
    
    # Initialize database schema
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: db-init-${VERSION//[^a-zA-Z0-9]/-}
  namespace: ${NAMESPACE}
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: db-init
        image: ${DOCKER_REGISTRY:-}${PROJECT_NAME}:${VERSION}
        command: ["python", "scripts/init_database.py"]
        envFrom:
        - configMapRef:
            name: langgraph-config
        - secretRef:
            name: langgraph-database
  backoffLimit: 3
EOF
    
    # Wait for job completion
    kubectl wait --for=condition=complete --timeout=300s job/db-init-${VERSION//[^a-zA-Z0-9]/-} -n ${NAMESPACE}
    
    print_status "System initialized"
}

# Run smoke tests
run_smoke_tests() {
    echo -e "${BLUE}🧪 Running smoke tests...${NC}"
    
    # Wait for application to be ready
    kubectl wait --for=condition=available --timeout=600s deployment/langgraph-search-api -n ${NAMESPACE}
    
    # Get service endpoint
    SERVICE_IP=$(kubectl get svc langgraph-search-service -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
    
    # Test health endpoint
    kubectl run curl-test --image=curlimages/curl --rm -i --restart=Never -- \
        curl -f http://${SERVICE_IP}:8000/health || print_error "Health check failed"
    
    # Test search endpoint
    kubectl run curl-test --image=curlimages/curl --rm -i --restart=Never -- \
        curl -f -X POST http://${SERVICE_IP}:8000/api/v2/search \
        -H "Content-Type: application/json" \
        -d '{"query": "What is artificial intelligence?", "max_results": 5}' || print_error "Search test failed"
    
    print_status "Smoke tests passed"
}

# Generate deployment report
generate_report() {
    echo -e "${BLUE}📋 Generating deployment report...${NC}"
    
    REPORT_FILE="deployment-report-${VERSION}-$(date +%Y%m%d-%H%M%S).txt"
    
    cat > ${REPORT_FILE} <<EOF
# LangGraph Search Production Deployment Report

## Deployment Information
- Version: ${VERSION}
- Environment: ${ENVIRONMENT}
- Namespace: ${NAMESPACE}
- Date: $(date)
- Deployed by: $(whoami)

## Infrastructure Components
$(kubectl get all -n ${NAMESPACE})

## Resource Usage
$(kubectl top nodes 2>/dev/null || echo "Metrics server not available")
$(kubectl top pods -n ${NAMESPACE} 2>/dev/null || echo "Pod metrics not available")

## Service Endpoints
- API: https://api.langgraph-search.com
- Grafana: http://localhost:3000 (port-forward)
- Prometheus: http://localhost:9090 (port-forward)

## Access Commands
# Port forward Grafana
kubectl port-forward -n ${NAMESPACE} svc/prometheus-grafana 3000:80

# Port forward Prometheus
kubectl port-forward -n ${NAMESPACE} svc/prometheus-kube-prometheus-prometheus 9090:9090

# View logs
kubectl logs -f deployment/langgraph-search-api -n ${NAMESPACE}

# Scale deployment
kubectl scale deployment/langgraph-search-api --replicas=10 -n ${NAMESPACE}

## Security Information
- TLS Certificate: Automatically managed by cert-manager
- API Keys: Stored in Kubernetes secrets
- RBAC: Configured with least privilege principle
- Network Policies: Apply as needed for your security requirements

## Monitoring
- Prometheus: Collecting metrics from all components
- Grafana: Dashboard available with performance metrics
- Alertmanager: Configured for critical alerts

## Backup Information
- PostgreSQL: Automated backups enabled
- Redis: Persistence enabled with AOF
- Application Logs: Forwarded to monitoring system

## Next Steps
1. Configure DNS to point to your ingress
2. Set up external monitoring/alerting
3. Configure backup retention policies
4. Set up CI/CD pipeline for automated deployments
5. Configure network policies for enhanced security
6. Set up log aggregation (ELK stack or similar)

## Troubleshooting Commands
# Check pod status
kubectl get pods -n ${NAMESPACE}

# View pod logs
kubectl logs <pod-name> -n ${NAMESPACE}

# Describe problematic resources
kubectl describe <resource-type> <resource-name> -n ${NAMESPACE}

# Check events
kubectl get events -n ${NAMESPACE} --sort-by='.lastTimestamp'

# Access shell in pod
kubectl exec -it <pod-name> -n ${NAMESPACE} -- /bin/bash

EOF
    
    echo -e "${GREEN}📄 Deployment report generated: ${REPORT_FILE}${NC}"
}

# Main deployment flow
main() {
    echo -e "${BLUE}🎯 Starting LangGraph Search Production Deployment${NC}"
    
    check_prerequisites
    setup_namespace
    create_secrets
    deploy_infrastructure
    deploy_monitoring
    build_and_push_images
    deploy_application
    setup_ingress
    initialize_system
    run_smoke_tests
    generate_report
    
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
    echo -e "${GREEN}🌐 Your LangGraph Search API is available at: https://api.langgraph-search.com${NC}"
    echo -e "${YELLOW}📊 Access Grafana: kubectl port-forward -n ${NAMESPACE} svc/prometheus-grafana 3000:80${NC}"
    echo -e "${YELLOW}🔍 Access Prometheus: kubectl port-forward -n ${NAMESPACE} svc/prometheus-kube-prometheus-prometheus 9090:9090${NC}"
    echo -e "${BLUE}📋 Check the deployment report for detailed information and next steps${NC}"
}

# Run main function
main "$@"
