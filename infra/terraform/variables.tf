variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-3" # Paris
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Must be dev or prod."
  }
}

variable "project_name" {
  description = "Used as a prefix for all resource names"
  type        = string
  default     = "vigistock"
}

# --- Network ---
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

# --- ECS ---
variable "streamlit_cpu" {
  type    = number
  default = 512
}

variable "streamlit_memory" {
  type    = number
  default = 1024
}

variable "dagster_cpu" {
  type    = number
  default = 1024
}

variable "dagster_memory" {
  type    = number
  default = 2048
}

# --- RDS / TimescaleDB ---
variable "db_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_password" {
  description = "TimescaleDB master password: use AWS Secrets Manager in prod"
  type        = string
  sensitive   = true
}

# --- MSK ---
variable "kafka_instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "kafka_broker_count" {
  type    = number
  default = 1
}
