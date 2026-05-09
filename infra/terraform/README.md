# AITBC Terraform Infrastructure

This directory contains Terraform configurations for deploying AITBC infrastructure on AWS.

## Prerequisites

- Terraform >= 1.0
- AWS CLI configured with appropriate credentials
- S3 bucket for Terraform state (configured in backend)
- DynamoDB table for state locking (configured in backend)

## Directory Structure

```
terraform/
├── main.tf              # Main Terraform configuration
├── provider.tf          # Provider configuration
├── variables.tf         # Infrastructure variables
├── outputs.tf           # Infrastructure outputs
├── ecs.tf               # ECS task definitions and services
├── ecs_variables.tf     # ECS-specific variables
└── README.md            # This file
```

## Usage

### Initialize Terraform

```bash
terraform init
```

### Plan Infrastructure

```bash
terraform plan -var-file=dev.tfvars
```

### Apply Infrastructure

```bash
terraform apply -var-file=dev.tfvars
```

### Destroy Infrastructure

```bash
terraform destroy -var-file=dev.tfvars
```

## Variables

Create a `dev.tfvars`, `staging.tfvars`, or `prod.tfvars` file with environment-specific variables:

```hcl
environment          = "dev"
aws_region           = "us-east-1"
db_username          = "aitbc"
db_password          = "your-secure-password"
database_url         = "postgresql://..."
redis_url           = "redis://..."
jwt_secret           = "your-jwt-secret"
acm_certificate_arn  = "arn:aws:acm:..."
```

## Infrastructure Components

### Networking
- VPC with public and private subnets
- NAT Gateway for private subnet internet access
- Security groups for different services

### Compute
- ECS Fargate cluster
- ECS task definitions for API services
- Application Load Balancer
- Auto-scaling capabilities

### Databases
- RDS PostgreSQL for application data
- ElastiCache Redis for caching

### Storage
- S3 bucket for data storage
- Versioning and encryption enabled

### Monitoring
- CloudWatch Log Groups
- ECS CloudWatch Container Insights

## State Management

Terraform state is stored in S3 with DynamoDB locking:
- State bucket: `aitbc-terraform-state`
- Lock table: `aitbc-terraform-locks`

## Security

- All resources are tagged with project and environment
- Security groups restrict access by CIDR blocks
- RDS and Redis are in private subnets
- Secrets stored in AWS Secrets Manager
- S3 encryption enabled
- RDS encryption enabled

## Cost Optimization

- Use appropriate instance sizes for environment
- Enable auto-scaling for production
- Monitor costs with AWS Cost Explorer
- Use reserved instances for predictable workloads

## Outputs

After applying the configuration, Terraform outputs:
- VPC and subnet IDs
- ECS cluster ID and ARN
- ALB DNS name
- Database and Redis endpoints
- S3 bucket name

## Troubleshooting

### State Lock Issues
If you encounter state lock issues:
```bash
terraform force-unlock <LOCK_ID>
```

### Resource Already Exists
If resources already exist outside Terraform, import them:
```bash
terraform import aws_vpc.this vpc-xxxxx
```

### Permission Errors
Ensure your AWS credentials have the necessary permissions:
- EC2 (VPC, subnets, security groups)
- ECS (clusters, task definitions, services)
- ELB (load balancers, target groups)
- RDS (database instances)
- ElastiCache (Redis clusters)
- S3 (buckets)
- Secrets Manager (secrets)
