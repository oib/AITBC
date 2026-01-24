---
name: deploy-production
description: Automated production deployment workflow for AITBC blockchain components
version: 1.0.0
author: Cascade
tags: [deployment, production, blockchain, aitbc]
---

# Production Deployment Skill

This skill provides a standardized workflow for deploying AITBC components to production environments.

## Overview

The production deployment skill ensures safe, consistent, and verifiable deployments of all AITBC stack components including:
- Coordinator services
- Blockchain node
- Miner daemon
- Web applications
- Infrastructure components

## Prerequisites

- Production server access configured
- SSL certificates installed
- Environment variables set
- Backup procedures in place
- Monitoring systems active

## Deployment Steps

### 1. Pre-deployment Checks
- Run health checks on all services
- Verify backup integrity
- Check disk space and resources
- Validate configuration files
- Review recent changes

### 2. Environment Preparation
- Update dependencies
- Build new artifacts
- Run smoke tests
- Prepare rollback plan

### 3. Deployment Execution
- Stop services gracefully
- Deploy new code
- Update configurations
- Restart services
- Verify health status

### 4. Post-deployment Verification
- Run integration tests
- Check API endpoints
- Verify blockchain sync
- Monitor system metrics
- Validate user access

## Supporting Files

- `pre-deploy-checks.sh` - Automated pre-deployment validation
- `environment-template.env` - Production environment template
- `rollback-steps.md` - Emergency rollback procedures
- `health-check.py` - Service health verification script

## Usage

This skill is automatically invoked when you request production deployment. You can also manually invoke it by mentioning "deploy production" or "production deployment".

## Safety Features

- Automatic rollback on failure
- Service health monitoring
- Configuration validation
- Backup verification
- Rollback checkpoint creation
