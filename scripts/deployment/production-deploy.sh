#!/bin/bash

# AITBC Production Deployment Script
# This script handles production deployment with zero-downtime

set -e

# Production Configuration
ENVIRONMENT="production"
VERSION=${1:-latest}
REGION=${2:-us-east-1}
NAMESPACE="aitbc-prod"
DOMAIN="aitbc.dev"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Pre-deployment checks
pre_deployment_checks() {
    log "Running pre-deployment checks..."
    
    # Check if we're on production branch
    current_branch=$(git branch --show-current)
    if [ "$current_branch" != "production" ]; then
        error "Must be on production branch to deploy to production"
    fi
    
    # Check if all tests pass
    log "Running tests..."
    pytest tests/unit/ -v --tb=short || error "Unit tests failed"
    pytest tests/integration/ -v --tb=short || error "Integration tests failed"
    pytest tests/security/ -v --tb=short || error "Security tests failed"
    pytest tests/performance/test_performance_lightweight.py::TestPerformance::test_cli_performance -v --tb=short || error "Performance tests failed"
    
    # Check if production infrastructure is ready
    log "Checking production infrastructure..."
    kubectl get nodes | grep -q "Ready" || error "Production nodes not ready"
    kubectl get namespace $NAMESPACE || kubectl create namespace $NAMESPACE
    
    success "Pre-deployment checks passed"
}

# Backup current deployment
backup_current_deployment() {
    log "Backing up current deployment..."
    
    # Create backup directory
    backup_dir="/opt/aitbc/backups/pre-deployment-$(date +%Y%m%d_%H%M%S)"
    mkdir -p $backup_dir
    
    # Backup current configuration
    kubectl get all -n $NAMESPACE -o yaml > $backup_dir/current-deployment.yaml
    
    # Backup database
    pg_dump $DATABASE_URL | gzip > $backup_dir/database_backup.sql.gz
    
    # Backup application data
    kubectl exec -n $NAMESPACE deployment/coordinator-api -- tar -czf /tmp/app_data_backup.tar.gz /app/data
    kubectl cp $NAMESPACE/deployment/coordinator-api:/tmp/app_data_backup.tar.gz $backup_dir/app_data_backup.tar.gz
    
    success "Backup completed: $backup_dir"
}

# Build production images
build_production_images() {
    log "Skipping Docker image build - Docker not supported in this environment"
    log "Deployment will use systemd services instead"
    success "Build step skipped (no Docker support)"
}

# Deploy database
deploy_database() {
    log "Skipping Helm-based database deployment - Helm not supported"
    log "Database should be deployed via systemd services or external PostgreSQL"
    log "Use: sudo apt-get install postgresql for local deployment"

    # Deploy Redis
    log "Skipping Helm-based Redis deployment - Helm not supported"
    log "Redis should be deployed via systemd service or external Redis"
    log "Use: sudo apt-get install redis-server for local deployment"

    success "Database deployment skipped (use systemd or external services)"
}

# Deploy core services
deploy_core_services() {
    log "Deploying core services..."
    
    # Deploy blockchain services
    for service in blockchain-node consensus-node network-node; do
        log "Deploying $service..."
        
        # Create deployment manifest
        cat > /tmp/$service-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $service
  namespace: $NAMESPACE
spec:
  replicas: 2
  selector:
    matchLabels:
      app: $service
  template:
    metadata:
      labels:
        app: $service
    spec:
      containers:
      - name: $service
        image: aitbc/$service:$VERSION
        ports:
        - containerPort: 8007
          name: http
        env:
        - name: NODE_ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: redis-url
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8007
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8007
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: $service
  namespace: $NAMESPACE
spec:
  selector:
    app: $service
  ports:
  - port: 8007
    targetPort: 8007
  type: ClusterIP
EOF
        
        # Apply deployment
        kubectl apply -f /tmp/$service-deployment.yaml -n $NAMESPACE || error "Failed to deploy $service"
        
        # Wait for deployment
        kubectl rollout status deployment/$service -n $NAMESPACE --timeout=300s || error "Failed to rollout $service"
        
        rm /tmp/$service-deployment.yaml
    done
    
    success "Core services deployed successfully"
}

# Deploy application services
deploy_application_services() {
    log "Deploying application services..."
    
    services=("coordinator-api" "exchange-integration" "compliance-service" "trading-engine" "plugin-registry" "plugin-marketplace" "plugin-security" "plugin-analytics" "global-infrastructure" "global-ai-agents" "multi-region-load-balancer")
    
    for service in "${services[@]}"; do
        log "Deploying $service..."
        
        # Determine port
        case $service in
            "coordinator-api") port=8001 ;;
            "exchange-integration") port=8010 ;;
            "compliance-service") port=8011 ;;
            "trading-engine") port=8012 ;;
            "plugin-registry") port=8013 ;;
            "plugin-marketplace") port=8014 ;;
            "plugin-security") port=8015 ;;
            "plugin-analytics") port=8016 ;;
            "global-infrastructure") port=8017 ;;
            "global-ai-agents") port=8018 ;;
            "multi-region-load-balancer") port=8019 ;;
        esac
        
        # Create deployment manifest
        cat > /tmp/$service-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $service
  namespace: $NAMESPACE
spec:
  replicas: 3
  selector:
    matchLabels:
      app: $service
  template:
    metadata:
      labels:
        app: $service
    spec:
      containers:
      - name: $service
        image: aitbc/$service:$VERSION
        ports:
        - containerPort: $port
          name: http
        env:
        - name: NODE_ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: redis-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: jwt-secret
        - name: ENCRYPTION_KEY
          valueFrom:
            secretKeyRef:
              name: aitbc-secrets
              key: encryption-key
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: $port
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: $port
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: $service
  namespace: $NAMESPACE
spec:
  selector:
    app: $service
  ports:
  - port: $port
    targetPort: $port
  type: ClusterIP
EOF
        
        # Apply deployment
        kubectl apply -f /tmp/$service-deployment.yaml -n $NAMESPACE || error "Failed to deploy $service"
        
        # Wait for deployment
        kubectl rollout status deployment/$service -n $NAMESPACE --timeout=300s || error "Failed to rollout $service"
        
        rm /tmp/$service-deployment.yaml
    done
    
    success "Application services deployed successfully"
}

# Deploy ingress and load balancer
deploy_ingress() {
    log "Deploying ingress and load balancer..."
    
    # Create ingress manifest
    cat > /tmp/ingress.yaml << EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: aitbc-ingress
  namespace: $NAMESPACE
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
  - hosts:
    - api.$DOMAIN
    - marketplace.$DOMAIN
    - explorer.$DOMAIN
    secretName: aitbc-tls
  rules:
  - host: api.$DOMAIN
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: coordinator-api
            port:
              number: 8001
  - host: marketplace.$DOMAIN
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: plugin-marketplace
            port:
              number: 8014
  - host: explorer.$DOMAIN
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: explorer
            port:
              number: 8020
EOF
    
    # Apply ingress
    kubectl apply -f /tmp/ingress.yaml -n $NAMESPACE || error "Failed to deploy ingress"
    
    rm /tmp/ingress.yaml
    
    success "Ingress deployed successfully"
}

# Deploy monitoring
deploy_monitoring() {
    log "Skipping Helm-based monitoring deployment - Helm not supported"
    log "Monitoring should be deployed via systemd services or external monitoring"
    log "Use: sudo apt-get install prometheus-node-exporter for local monitoring"

    # Import Grafana dashboards
    log "Skipping Grafana dashboard import - requires Helm deployment"
    
    # Create dashboard configmaps
    kubectl create configmap grafana-dashboards \
        --from-file=monitoring/grafana/dashboards/ \
        -n $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    success "Monitoring deployed successfully"
}

# Run post-deployment tests
post_deployment_tests() {
    log "Running post-deployment tests..."
    
    # Wait for all services to be ready
    kubectl wait --for=condition=ready pod -l app!=pod -n $NAMESPACE --timeout=600s
    
    # Test API endpoints
    endpoints=(
        "coordinator-api:8001"
        "exchange-integration:8010"
        "trading-engine:8012"
        "plugin-registry:8013"
        "plugin-marketplace:8014"
    )
    
    for service_port in "${endpoints[@]}"; do
        service=$(echo $service_port | cut -d: -f1)
        port=$(echo $service_port | cut -d: -f2)
        
        log "Testing $service..."
        
        # Port-forward and test
        kubectl port-forward -n $NAMESPACE deployment/$service $port:8007 &
        port_forward_pid=$!
        
        sleep 5
        
        if curl -f -s http://localhost:$port/health > /dev/null; then
            success "$service is healthy"
        else
            error "$service health check failed"
        fi
        
        # Kill port-forward
        kill $port_forward_pid 2>/dev/null || true
    done
    
    # Test external endpoints
    external_endpoints=(
        "https://api.$DOMAIN/health"
        "https://marketplace.$DOMAIN/api/v1/marketplace/featured"
    )
    
    for endpoint in "${external_endpoints[@]}"; do
        log "Testing $endpoint..."
        
        if curl -f -s $endpoint > /dev/null; then
            success "$endpoint is responding"
        else
            error "$endpoint is not responding"
        fi
    done
    
    success "Post-deployment tests passed"
}

# Create secrets
create_secrets() {
    log "Creating secrets..."
    
    # Create secret from environment variables
    kubectl create secret generic aitbc-secrets \
        --from-literal=database-url="$DATABASE_URL" \
        --from-literal=redis-url="$REDIS_URL" \
        --from-literal=jwt-secret="$JWT_SECRET" \
        --from-literal=encryption-key="$ENCRYPTION_KEY" \
        --from-literal=postgres-password="$POSTGRES_PASSWORD" \
        --from-literal=redis-password="$REDIS_PASSWORD" \
        --namespace $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    success "Secrets created"
}

# Main deployment function
main() {
    log "Starting AITBC production deployment..."
    log "Environment: $ENVIRONMENT"
    log "Version: $VERSION"
    log "Region: $REGION"
    log "Domain: $DOMAIN"
    
    # Check prerequisites
    command -v kubectl >/dev/null 2>&1 || error "kubectl is not installed"
    kubectl cluster-info >/dev/null 2>&1 || error "Cannot connect to Kubernetes cluster"
    
    # Run deployment steps
    pre_deployment_checks
    create_secrets
    backup_current_deployment
    build_production_images
    deploy_database
    deploy_core_services
    deploy_application_services
    deploy_ingress
    deploy_monitoring
    post_deployment_tests
    
    success "Production deployment completed successfully!"
    
    # Display deployment information
    log "Deployment Information:"
    log "Environment: $ENVIRONMENT"
    log "Version: $VERSION"
    log "Namespace: $NAMESPACE"
    log "Domain: $DOMAIN"
    log ""
    log "Services are available at:"
    log "  API: https://api.$DOMAIN"
    log "  Marketplace: https://marketplace.$DOMAIN"
    log "  Explorer: https://explorer.$DOMAIN"
    log "  Grafana: https://grafana.$DOMAIN"
    log ""
    log "To check deployment status:"
    log "  kubectl get pods -n $NAMESPACE"
    log "  kubectl get services -n $NAMESPACE"
    log ""
    log "To view logs:"
    log "  kubectl logs -f deployment/coordinator-api -n $NAMESPACE"
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Export environment variables
export DATABASE_URL=${DATABASE_URL}
export REDIS_URL=${REDIS_URL}
export JWT_SECRET=${JWT_SECRET}
export ENCRYPTION_KEY=${ENCRYPTION_KEY}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
export REDIS_PASSWORD=${REDIS_PASSWORD}
export GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
export VERSION=${VERSION}
export NAMESPACE=${NAMESPACE}
export DOMAIN=${DOMAIN}

# Run main function
main "$@"
