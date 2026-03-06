# Shared variables for all environments

variable "cluster_name" {
  description = "Name of the Kubernetes cluster"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-west-2"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
}

variable "availability_zones" {
  description = "Availability zones to use"
  type        = list(string)
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.28"
}

variable "enable_public_endpoint" {
  description = "Enable public API endpoint"
  type        = bool
  default     = false
}

variable "desired_node_count" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "min_node_count" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 10
}

variable "instance_types" {
  description = "EC2 instance types for worker nodes"
  type        = list(string)
  default     = ["t3.medium"]
}

# Monitoring and logging
variable "enable_monitoring" {
  description = "Enable CloudWatch monitoring"
  type        = bool
  default     = true
}

variable "enable_logging" {
  description = "Enable centralized logging"
  type        = bool
  default     = true
}

variable "enable_alerting" {
  description = "Enable alerting (prod only)"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "Log retention in days"
  type        = number
  default     = 30
}

variable "backup_retention_days" {
  description = "Backup retention in days"
  type        = number
  default     = 7
}

# Application replicas
variable "coordinator_replicas" {
  description = "Number of coordinator API replicas"
  type        = number
  default     = 1
}

variable "explorer_replicas" {
  description = "Number of explorer replicas"
  type        = number
  default     = 1
}

variable "marketplace_replicas" {
  description = "Number of marketplace replicas"
  type        = number
  default     = 1
}

variable "wallet_daemon_replicas" {
  description = "Number of wallet daemon replicas"
  type        = number
  default     = 1
}

# Database
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "db_backup_window" {
  description = "Preferred backup window"
  type        = string
  default     = "03:00-04:00"
}

variable "db_maintenance_window" {
  description = "Preferred maintenance window"
  type        = string
  default     = "Mon:04:00-Mon:05:00"
}

# Security
variable "enable_encryption" {
  description = "Enable encryption at rest"
  type        = bool
  default     = true
}

variable "enable_waf" {
  description = "Enable WAF protection"
  type        = bool
  default     = false
}

variable "ssl_policy" {
  description = "SSL policy for load balancers"
  type        = string
  default     = "ELBSecurityPolicy-TLS-1-2-2017-01"
}

# Autoscaling
variable "enable_cluster_autoscaler" {
  description = "Enable cluster autoscaler"
  type        = bool
  default     = false
}

variable "enable_hpa" {
  description = "Enable horizontal pod autoscaler"
  type        = bool
  default     = false
}

# GPU nodes
variable "gpu_node_group_enabled" {
  description = "Enable GPU node group for miners"
  type        = bool
  default     = false
}

variable "gpu_instance_types" {
  description = "GPU instance types"
  type        = list(string)
  default     = ["g4dn.xlarge"]
}

variable "gpu_min_nodes" {
  description = "Minimum GPU nodes"
  type        = number
  default     = 0
}

variable "gpu_max_nodes" {
  description = "Maximum GPU nodes"
  type        = number
  default     = 5
}

# Tags
variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
