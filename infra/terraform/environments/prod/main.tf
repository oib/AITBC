# Production environment configuration

terraform {
  source = "../../modules/kubernetes"
}

include "root" {
  path = find_in_parent_folders()
}

inputs = {
  cluster_name               = "aitbc-prod"
  environment               = "prod"
  aws_region                = "us-west-2"
  vpc_cidr                  = "10.2.0.0/16"
  private_subnet_cidrs      = ["10.2.1.0/24", "10.2.2.0/24", "10.2.3.0/24"]
  public_subnet_cidrs       = ["10.2.101.0/24", "10.2.102.0/24", "10.2.103.0/24"]
  availability_zones        = ["us-west-2a", "us-west-2b", "us-west-2c"]
  kubernetes_version        = "1.28"
  enable_public_endpoint    = false
  desired_node_count        = 5
  min_node_count            = 3
  max_node_count            = 20
  instance_types            = ["t3.xlarge", "t3.2xlarge", "m5.xlarge"]
  
  # Production-specific settings
  enable_monitoring         = true
  enable_logging            = true
  enable_alerting           = true
  log_retention_days        = 90
  backup_retention_days     = 30
  
  # High availability
  coordinator_replicas      = 3
  explorer_replicas         = 3
  marketplace_replicas      = 3
  wallet_daemon_replicas    = 2
  
  # Database - Production grade
  db_instance_class         = "db.r5.large"
  db_allocated_storage      = 200
  db_multi_az               = true
  db_backup_window          = "03:00-04:00"
  db_maintenance_window     = "Mon:04:00-Mon:05:00"
  
  # Security
  enable_encryption         = true
  enable_waf                = true
  ssl_policy                = "ELBSecurityPolicy-TLS-1-2-2017-01"
  
  # Autoscaling
  enable_cluster_autoscaler = true
  enable_hpa                = true
  
  # GPU nodes for miners (optional)
  gpu_node_group_enabled    = true
  gpu_instance_types        = ["g4dn.xlarge", "g4dn.2xlarge"]
  gpu_min_nodes             = 0
  gpu_max_nodes             = 10
}
