#!/bin/bash

# AITBC Automated Deployment Script
# This script handles automated deployment of AITBC services

set -e

# Configuration
ENVIRONMENT=${1:-staging}
VERSION=${2:-latest}
REGION=${3:-us-east-1}
NAMESPACE="aitbc-${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
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

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if required tools are installed
    command -v docker >/dev/null 2>&1 || error "Docker is not installed"
    command -v docker-compose >/dev/null 2>&1 || error "Docker Compose is not installed"
    command -v kubectl >/dev/null 2>&1 || error "kubectl is not installed"
    command -v helm >/dev/null 2>&1 || error "Helm is not installed"
    
    # Check if Docker daemon is running
    docker info >/dev/null 2>&1 || error "Docker daemon is not running"
    
    # Check if kubectl can connect to cluster
    kubectl cluster-info >/dev/null 2>&1 || error "Cannot connect to Kubernetes cluster"
    
    success "Prerequisites check passed"
}

# Build Docker images
build_images() {
    log "Building Docker images..."
    
    # Build CLI image
    log "Building CLI image..."
    docker build -t aitbc/cli:${VERSION} -f Dockerfile . || error "Failed to build CLI image"
    
    # Build service images
    for service_dir in apps/*/; do
        if [ -f "$service_dir/Dockerfile" ]; then
            service_name=$(basename "$service_dir")
            log "Building ${service_name} image..."
            docker build -t aitbc/${service_name}:${VERSION} -f "$service_dir/Dockerfile" "$service_dir" || error "Failed to build ${service_name} image"
        fi
    done
    
    success "All Docker images built successfully"
}

# Run tests
run_tests() {
    log "Running tests..."
    
    # Run unit tests
    log "Running unit tests..."
    pytest tests/unit/ -v --cov=aitbc_cli --cov-report=term || error "Unit tests failed"
    
    # Run integration tests
    log "Running integration tests..."
    pytest tests/integration/ -v || error "Integration tests failed"
    
    # Run security tests
    log "Running security tests..."
    pytest tests/security/ -v || error "Security tests failed"
    
    # Run performance tests
    log "Running performance tests..."
    pytest tests/performance/test_performance_lightweight.py::TestPerformance::test_cli_performance -v || error "Performance tests failed"
    
    success "All tests passed"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log "Deploying to Kubernetes namespace: ${NAMESPACE}"
    
    # Create namespace if it doesn't exist
    kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply secrets
    log "Applying secrets..."
    kubectl apply -f k8s/secrets/ -n ${NAMESPACE} || error "Failed to apply secrets"
    
    # Apply configmaps
    log "Applying configmaps..."
    kubectl apply -f k8s/configmaps/ -n ${NAMESPACE} || error "Failed to apply configmaps"
    
    # Deploy database
    log "Deploying database..."
    helm repo add bitnami https://charts.bitnami.com/bitnami
    helm upgrade --install postgres bitnami/postgresql \
        --namespace ${NAMESPACE} \
        --set auth.postgresPassword=${POSTGRES_PASSWORD} \
        --set auth.database=aitbc \
        --set primary.persistence.size=20Gi \
        --set primary.resources.requests.memory=2Gi \
        --set primary.resources.requests.cpu=1000m \
        --wait || error "Failed to deploy database"
    
    # Deploy Redis
    log "Deploying Redis..."
    helm upgrade --install redis bitnami/redis \
        --namespace ${NAMESPACE} \
        --set auth.password=${REDIS_PASSWORD} \
        --set master.persistence.size=8Gi \
        --set master.resources.requests.memory=512Mi \
        --set master.resources.requests.cpu=500m \
        --wait || error "Failed to deploy Redis"
    
    # Deploy core services
    log "Deploying core services..."
    
    # Deploy blockchain services
    for service in blockchain-node consensus-node network-node; do
        log "Deploying ${service}..."
        envsubst < k8s/deployments/${service}.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy ${service}"
        kubectl rollout status deployment/${service} -n ${NAMESPACE} --timeout=300s || error "Failed to rollout ${service}"
    done
    
    # Deploy coordinator
    log "Deploying coordinator-api..."
    envsubst < k8s/deployments/coordinator-api.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy coordinator-api"
    kubectl rollout status deployment/coordinator-api -n ${NAMESPACE} --timeout=300s || error "Failed to rollout coordinator-api"
    
    # Deploy production services
    for service in exchange-integration compliance-service trading-engine; do
        log "Deploying ${service}..."
        envsubst < k8s/deployments/${service}.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy ${service}"
        kubectl rollout status deployment/${service} -n ${NAMESPACE} --timeout=300s || error "Failed to rollout ${service}"
    done
    
    # Deploy plugin ecosystem
    for service in plugin-registry plugin-marketplace plugin-security plugin-analytics; do
        log "Deploying ${service}..."
        envsubst < k8s/deployments/${service}.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy ${service}"
        kubectl rollout status deployment/${service} -n ${NAMESPACE} --timeout=300s || error "Failed to rollout ${service}"
    done
    
    # Deploy global infrastructure
    for service in global-infrastructure global-ai-agents multi-region-load-balancer; do
        log "Deploying ${service}..."
        envsubst < k8s/deployments/${service}.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy ${service}"
        kubectl rollout status deployment/${service} -n ${NAMESPACE} --timeout=300s || error "Failed to rollout ${service}"
    done
    
    # Deploy explorer
    log "Deploying explorer..."
    envsubst < k8s/deployments/explorer.yaml | kubectl apply -f - -n ${NAMESPACE} || error "Failed to deploy explorer"
    kubectl rollout status deployment/explorer -n ${NAMESPACE} --timeout=300s || error "Failed to rollout explorer"
    
    success "Kubernetes deployment completed"
}

# Deploy with Docker Compose
deploy_docker_compose() {
    log "Deploying with Docker Compose..."
    
    # Set environment variables
    export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-aitbc123}
    export REDIS_PASSWORD=${REDIS_PASSWORD:-aitbc123}
    export GRAFANA_PASSWORD=${GRAFANA_PASSWORD:-admin}
    
    # Stop existing services
    log "Stopping existing services..."
    docker-compose down || true
    
    # Start services
    log "Starting services..."
    docker-compose up -d || error "Failed to start services"
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 30
    
    # Check service health
    for service in postgres redis blockchain-node coordinator-api exchange-integration; do
        log "Checking ${service} health..."
        if ! docker-compose ps ${service} | grep -q "Up"; then
            error "Service ${service} is not running"
        fi
    done
    
    success "Docker Compose deployment completed"
}

# Run health checks
run_health_checks() {
    log "Running health checks..."
    
    if command -v kubectl >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
        # Kubernetes health checks
        log "Checking Kubernetes deployment health..."
        
        # Check pod status
        kubectl get pods -n ${NAMESPACE} || error "Failed to get pod status"
        
        # Check service health
        services=("coordinator-api" "exchange-integration" "trading-engine" "plugin-registry")
        for service in "${services[@]}"; do
            log "Checking ${service} health..."
            kubectl get pods -n ${NAMESPACE} -l app=${service} -o jsonpath='{.items[0].status.phase}' | grep -q "Running" || error "${service} pods are not running"
            
            # Check service endpoint
            service_url=$(kubectl get svc ${service} -n ${NAMESPACE} -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
            if [ -n "$service_url" ]; then
                curl -f http://${service_url}/health >/dev/null 2>&1 || error "${service} health check failed"
            fi
        done
        
    else
        # Docker Compose health checks
        log "Checking Docker Compose deployment health..."
        
        services=("coordinator-api" "exchange-integration" "trading-engine" "plugin-registry")
        for service in "${services[@]}"; do
            log "Checking ${service} health..."
            if ! docker-compose ps ${service} | grep -q "Up"; then
                error "Service ${service} is not running"
            fi
            
            # Check health endpoint
            port=$(docker-compose port ${service} | cut -d: -f2)
            curl -f http://localhost:${port}/health >/dev/null 2>&1 || error "${service} health check failed"
        done
    fi
    
    success "All health checks passed"
}

# Run smoke tests
run_smoke_tests() {
    log "Running smoke tests..."
    
    # Test CLI functionality
    log "Testing CLI functionality..."
    docker-compose exec aitbc-cli python -m aitbc_cli.main --help >/dev/null || error "CLI smoke test failed"
    
    # Test API endpoints
    log "Testing API endpoints..."
    
    # Test coordinator API
    coordinator_port=$(docker-compose port coordinator-api | cut -d: -f2)
    curl -f http://localhost:${coordinator_port}/health >/dev/null || error "Coordinator API smoke test failed"
    
    # Test exchange API
    exchange_port=$(docker-compose port exchange-integration | cut -d: -f2)
    curl -f http://localhost:${exchange_port}/health >/dev/null || error "Exchange API smoke test failed"
    
    # Test plugin registry
    plugin_port=$(docker-compose port plugin-registry | cut -d: -f2)
    curl -f http://localhost:${plugin_port}/health >/dev/null || error "Plugin registry smoke test failed"
    
    success "Smoke tests passed"
}

# Rollback deployment
rollback() {
    log "Rolling back deployment..."
    
    if command -v kubectl >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
        # Kubernetes rollback
        log "Rolling back Kubernetes deployment..."
        
        services=("coordinator-api" "exchange-integration" "trading-engine" "plugin-registry")
        for service in "${services[@]}"; do
            log "Rolling back ${service}..."
            kubectl rollout undo deployment/${service} -n ${NAMESPACE} || error "Failed to rollback ${service}"
            kubectl rollout status deployment/${service} -n ${NAMESPACE} --timeout=300s || error "Failed to rollback ${service}"
        done
        
    else
        # Docker Compose rollback
        log "Rolling back Docker Compose deployment..."
        docker-compose down || error "Failed to stop services"
        
        # Restart with previous version (assuming it's tagged as 'previous')
        export VERSION=previous
        deploy_docker_compose
    fi
    
    success "Rollback completed"
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    
    # Remove unused Docker images
    docker image prune -f || true
    
    # Remove unused Docker volumes
    docker volume prune -f || true
    
    success "Cleanup completed"
}

# Main deployment function
main() {
    log "Starting AITBC deployment..."
    log "Environment: ${ENVIRONMENT}"
    log "Version: ${VERSION}"
    log "Region: ${REGION}"
    
    case "${ENVIRONMENT}" in
        "local"|"docker")
            check_prerequisites
            build_images
            run_tests
            deploy_docker_compose
            run_health_checks
            run_smoke_tests
            ;;
        "staging"|"production")
            check_prerequisites
            build_images
            run_tests
            deploy_kubernetes
            run_health_checks
            run_smoke_tests
            ;;
        "rollback")
            rollback
            ;;
        "cleanup")
            cleanup
            ;;
        *)
            error "Unknown environment: ${ENVIRONMENT}. Use 'local', 'docker', 'staging', 'production', 'rollback', or 'cleanup'"
            ;;
    esac
    
    success "Deployment completed successfully!"
    
    # Display deployment information
    log "Deployment Information:"
    log "Environment: ${ENVIRONMENT}"
    log "Version: ${VERSION}"
    log "Namespace: ${NAMESPACE}"
    
    if [ "${ENVIRONMENT}" = "docker" ]; then
        log "Services are running on:"
        log "  Coordinator API: http://localhost:8001"
        log "  Exchange Integration: http://localhost:8010"
        log "  Trading Engine: http://localhost:8012"
        log "  Plugin Registry: http://localhost:8013"
        log "  Plugin Marketplace: http://localhost:8014"
        log "  Explorer: http://localhost:8020"
        log "  Grafana: http://localhost:3000 (admin/admin)"
        log "  Prometheus: http://localhost:9090"
    fi
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Export environment variables for envsubst
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-aitbc123}
export REDIS_PASSWORD=${REDIS_PASSWORD:-aitbc123}
export GRAFANA_PASSWORD=${GRAFANA_PASSWORD:-admin}
export VERSION=${VERSION}
export NAMESPACE=${NAMESPACE}

# Run main function
main "$@"
