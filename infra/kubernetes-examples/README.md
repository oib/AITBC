# Kubernetes Example Manifests

This directory contains reference Kubernetes manifests for AITBC infrastructure components.

## Purpose

These manifests are provided as **reference implementations** and examples for Kubernetes deployment. They are **not** production-ready deployment specifications for the core AITBC services.

## Current Manifests

- `backup-configmap.yaml` - Configuration for backup operations
- `backup-cronjob.yaml` - CronJob for automated backups
- `cert-manager.yaml` - Cert-manager configuration for TLS certificates
- `default-deny-netpol.yaml` - Default deny network policy for security
- `sealed-secrets.yaml` - Sealed Secrets configuration for secret management

## Production Deployment

AITBC currently uses systemd-based orchestration for production deployments. See `docs/testing/e2e-test-plan.md` for systemd-based service orchestration details.

## Usage

To use these examples in a Kubernetes environment:

1. Review and customize the manifests for your environment
2. Apply the manifests: `kubectl apply -f <manifest>.yaml`
3. Modify as needed for your specific Kubernetes setup

## Future Work

These manifests may be expanded to include full deployment specifications for core services (blockchain-node, coordinator-api, exchange) if Kubernetes deployment becomes a priority.
