# Terraform state backend configuration
# Uses S3 for state storage and DynamoDB for locking

terraform {
  backend "s3" {
    bucket         = "aitbc-terraform-state"
    key            = "environments/${var.environment}/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "aitbc-terraform-locks"
    
    # Enable versioning for state history
    # Configured at bucket level
  }
  
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }
}

# Provider configuration
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = merge(var.tags, {
      Environment = var.environment
      Project     = "aitbc"
      ManagedBy   = "terraform"
    })
  }
}

# Kubernetes provider - configured after cluster creation
provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
  
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
  }
}

provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.cluster.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
    
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name]
    }
  }
}

# Data sources for EKS cluster
data "aws_eks_cluster" "cluster" {
  name = var.cluster_name
  
  depends_on = [module.eks]
}

data "aws_eks_cluster_auth" "cluster" {
  name = var.cluster_name
  
  depends_on = [module.eks]
}
