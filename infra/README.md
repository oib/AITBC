# AITBC Infrastructure Templates

This directory contains Terraform and Helm templates for deploying AITBC services across dev, staging, and production environments.

## Directory Structure

```
infra/
├── terraform/                 # Infrastructure as Code
│   ├── modules/              # Reusable Terraform modules
│   │   └── kubernetes/       # EKS cluster module
│   └── environments/         # Environment-specific configurations
│       ├── dev/
│       ├── staging/
│       └── prod/
└── helm/                     # Helm Charts
    ├── charts/               # Application charts
    │   ├── coordinator/      # Coordinator API chart
    │   ├── blockchain-node/  # Blockchain node chart
    │   └── monitoring/       # Monitoring stack (Prometheus, Grafana)
    └── values/               # Environment-specific values
        ├── dev.yaml
        ├── staging.yaml
        └── prod.yaml
```

## Quick Start

### Prerequisites

- Terraform >= 1.0
- Helm >= 3.0
- kubectl configured for your cluster
- AWS CLI configured (for EKS)

### Deploy Development Environment

1. **Provision Infrastructure with Terraform:**
   ```bash
   cd infra/terraform/environments/dev
   terraform init
   terraform apply
   ```

2. **Configure kubectl:**
   ```bash
   aws eks update-kubeconfig --name aitbc-dev --region us-west-2
   ```

3. **Deploy Applications with Helm:**
   ```bash
   # Add required Helm repositories
   helm repo add bitnami https://charts.bitnami.com/bitnami
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo add grafana https://grafana.github.io/helm-charts
   helm repo update
   
   # Deploy monitoring stack
   helm install monitoring ../../helm/charts/monitoring -f ../../helm/values/dev.yaml
   
   # Deploy coordinator API
   helm install coordinator ../../helm/charts/coordinator -f ../../helm/values/dev.yaml
   ```

### Environment Configurations

#### Development
- 1 replica per service
- Minimal resource allocation
- Public EKS endpoint enabled
- 7-day metrics retention

#### Staging
- 2-3 replicas per service
- Moderate resource allocation
- Autoscaling enabled
- 30-day metrics retention
- TLS with staging certificates

#### Production
- 3+ replicas per service
- High resource allocation
- Full autoscaling configuration
- 90-day metrics retention
- TLS with production certificates
- Network policies enabled
- Backup configuration enabled

## Monitoring

The monitoring stack includes:
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization dashboards
- **AlertManager**: Alert routing and notification

Access Grafana:
```bash
kubectl port-forward svc/monitoring-grafana 3000:3000
# Open http://localhost:3000
# Default credentials: admin/admin (check values files for environment-specific passwords)
```

## Scaling Guidelines

Based on benchmark results (`apps/blockchain-node/scripts/benchmark_throughput.py`):

- **Coordinator API**: Scale horizontally at ~500 TPS per node
- **Blockchain Node**: Scale horizontally at ~1000 TPS per node
- **Wallet Daemon**: Scale based on concurrent users

## Security Considerations

- Private subnets for all application workloads
- Network policies restrict traffic between services
- Secrets managed via Kubernetes Secrets
- TLS termination at ingress level
- Pod Security Policies enforced in production

## Backup and Recovery

- Automated daily backups of PostgreSQL databases
- EBS snapshots for persistent volumes
- Cross-region replication for production data
- Restore procedures documented in runbooks

## Cost Optimization

- Use Spot instances for non-critical workloads
- Implement cluster autoscaling
- Right-size resources based on metrics
- Schedule non-production environments to run only during business hours

## Troubleshooting

Common issues and solutions:

1. **Helm chart fails to install:**
   - Check if all dependencies are added
   - Verify kubectl context is correct
   - Review values files for syntax errors

2. **Prometheus not scraping metrics:**
   - Verify ServiceMonitor CRDs are installed
   - Check service annotations
   - Review network policies

3. **High memory usage:**
   - Review resource limits in values files
   - Check for memory leaks in applications
   - Consider increasing node size

## Contributing

When adding new services:
1. Create a new Helm chart in `helm/charts/`
2. Add environment-specific values in `helm/values/`
3. Update monitoring configuration to include new service metrics
4. Document any special requirements in this README
