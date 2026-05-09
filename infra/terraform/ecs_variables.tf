# ECS API variables

variable "api_cpu" {
  description = "API task CPU units"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "API task memory in MB"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "API desired task count"
  type        = number
  default     = 2
}

variable "api_image" {
  description = "API Docker image"
  type        = string
  default     = "aitbc/api"
}

variable "api_image_tag" {
  description = "API Docker image tag"
  type        = string
  default     = "latest"
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "database_url" {
  description = "Database connection URL"
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "Redis connection URL"
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "JWT secret key"
  type        = string
  sensitive   = true
}
