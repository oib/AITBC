# Secrets management configuration
# Uses AWS Secrets Manager for sensitive values

# Database credentials
data "aws_secretsmanager_secret" "db_credentials" {
  name = "aitbc/${var.environment}/db-credentials"
}

data "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = data.aws_secretsmanager_secret.db_credentials.id
}

locals {
  db_credentials = jsondecode(data.aws_secretsmanager_secret_version.db_credentials.secret_string)
}

# API keys
data "aws_secretsmanager_secret" "api_keys" {
  name = "aitbc/${var.environment}/api-keys"
}

data "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = data.aws_secretsmanager_secret.api_keys.id
}

locals {
  api_keys = jsondecode(data.aws_secretsmanager_secret_version.api_keys.secret_string)
}

# Wallet encryption keys
data "aws_secretsmanager_secret" "wallet_keys" {
  name = "aitbc/${var.environment}/wallet-keys"
}

data "aws_secretsmanager_secret_version" "wallet_keys" {
  secret_id = data.aws_secretsmanager_secret.wallet_keys.id
}

locals {
  wallet_keys = jsondecode(data.aws_secretsmanager_secret_version.wallet_keys.secret_string)
}

# Create Kubernetes secrets from AWS Secrets Manager
resource "kubernetes_secret" "db_credentials" {
  metadata {
    name      = "db-credentials"
    namespace = "aitbc"
  }

  data = {
    username = local.db_credentials.username
    password = local.db_credentials.password
    host     = local.db_credentials.host
    port     = local.db_credentials.port
    database = local.db_credentials.database
  }

  type = "Opaque"
}

resource "kubernetes_secret" "api_keys" {
  metadata {
    name      = "api-keys"
    namespace = "aitbc"
  }

  data = {
    coordinator_api_key = local.api_keys.coordinator
    explorer_api_key    = local.api_keys.explorer
    admin_api_key       = local.api_keys.admin
  }

  type = "Opaque"
}

resource "kubernetes_secret" "wallet_keys" {
  metadata {
    name      = "wallet-keys"
    namespace = "aitbc"
  }

  data = {
    encryption_key = local.wallet_keys.encryption_key
    signing_key    = local.wallet_keys.signing_key
  }

  type = "Opaque"
}

# External Secrets Operator (alternative approach)
# Uncomment if using external-secrets operator
#
# resource "kubernetes_manifest" "external_secret_db" {
#   manifest = {
#     apiVersion = "external-secrets.io/v1beta1"
#     kind       = "ExternalSecret"
#     metadata = {
#       name      = "db-credentials"
#       namespace = "aitbc"
#     }
#     spec = {
#       refreshInterval = "1h"
#       secretStoreRef = {
#         name = "aws-secrets-manager"
#         kind = "ClusterSecretStore"
#       }
#       target = {
#         name = "db-credentials"
#       }
#       data = [
#         {
#           secretKey = "username"
#           remoteRef = {
#             key      = "aitbc/${var.environment}/db-credentials"
#             property = "username"
#           }
#         },
#         {
#           secretKey = "password"
#           remoteRef = {
#             key      = "aitbc/${var.environment}/db-credentials"
#             property = "password"
#           }
#         }
#       ]
#     }
#   }
# }
