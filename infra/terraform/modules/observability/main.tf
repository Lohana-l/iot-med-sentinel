variable "project_name" { type = string }
variable "environment"  { type = string }
variable "vpc_id"       { type = string }
variable "subnet_ids"   { type = list(string) }

resource "aws_cloudwatch_log_group" "streamlit" {
  name              = "/ecs/${var.project_name}-${var.environment}/streamlit"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "dagster" {
  name              = "/ecs/${var.project_name}-${var.environment}/dagster"
  retention_in_days = 14
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${var.project_name}-${var.environment}-ecs-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "ECS CPU utilisation > 80% for 2 consecutive minutes"
}

resource "aws_grafana_workspace" "main" {
  name                     = "${var.project_name}-${var.environment}"
  account_access_type      = "CURRENT_ACCOUNT"
  authentication_providers = ["AWS_SSO"]
  permission_type          = "SERVICE_MANAGED"
  data_sources             = ["CLOUDWATCH", "PROMETHEUS"]
  description              = "Vigistock: operational dashboards"
}

output "grafana_url" { value = "https://${aws_grafana_workspace.main.endpoint}" }
