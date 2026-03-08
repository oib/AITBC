# Staging environment configuration

terraform {
  source = "../../modules/kubernetes"
}

include "root" {
  path = find_in_parent_folders()
}

inputs = {
  cluster_name               = "aitbc-staging"
  environment               = "staging"
  aws_region                = "us-west-2"
  vpc_cidr                  = "10.1.0.0/16"
  private_subnet_cidrs      = ["10.1.1.0/24", "10.1.2.0/24", "10.1.3.0/24"]
  public_subnet_cidrs       = ["10.1.101.0/24", "10.1.102.0/24", "10.1.103.0/24"]
  availability_zones        = ["us-west-2a", "us-west-2b", "us-west-2c"]
  kubernetes_version        = "1.28"
  enable_public_endpoint    = false
  desired_node_count        = 3
  min_node_count            = 2
  max_node_count            = 6
  instance_types            = ["t3.large", "t3.xlarge"]
  
  # Staging-specific settings
  enable_monitoring         = true
  enable_logging            = true
  log_retention_days        = 30
  backup_retention_days     = 7
  
  # Resource limits
  coordinator_replicas      = 2
  explorer_replicas         = 2
  marketplace_replicas      = 2
  
  # Database
  db_instance_class         = "db.t3.medium"
  db_allocated_storage      = 50
  db_multi_az               = false
}
