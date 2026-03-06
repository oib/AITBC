# Development environment configuration

terraform {
  source = "../../modules/kubernetes"
}

include "root" {
  path = find_in_parent_folders()
}

inputs = {
  cluster_name               = "aitbc-dev"
  environment               = "dev"
  aws_region                = "us-west-2"
  vpc_cidr                  = "10.0.0.0/16"
  private_subnet_cidrs      = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnet_cidrs       = ["10.0.101.0/24", "10.0.102.0/24"]
  availability_zones        = ["us-west-2a", "us-west-2b"]
  kubernetes_version        = "1.28"
  enable_public_endpoint    = true
  desired_node_count        = 2
  min_node_count            = 1
  max_node_count            = 3
  instance_types            = ["t3.medium"]
}
