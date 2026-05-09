# Terraform outputs for AITBC infrastructure

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}

output "ecs_cluster_id" {
  description = "ECS Cluster ID"
  value       = aws_ecs_cluster.this.id
}

output "ecs_cluster_arn" {
  description = "ECS Cluster ARN"
  value       = aws_ecs_cluster.this.arn
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "ALB zone ID"
  value       = aws_lb.this.zone_id
}

output "db_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.this.endpoint
  sensitive   = true
}

output "db_instance_id" {
  description = "RDS instance ID"
  value       = aws_db_instance.this.id
}

output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = aws_elasticache_replication_this.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = aws_elasticache_replication_this.port
}

output "s3_bucket_name" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.data.id
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.data.arn
}

output "security_group_blockchain_rpc_id" {
  description = "Blockchain RPC security group ID"
  value       = aws_security_group.blockchain_rpc.id
}

output "security_group_api_gateway_id" {
  description = "API gateway security group ID"
  value       = aws_security_group.api_gateway.id
}
