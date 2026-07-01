output "streamlit_url" {
  description = "Public URL of the Streamlit dashboard"
  value       = module.ecs_app.streamlit_url
}

output "dagster_url" {
  description = "Internal URL of the Dagster webserver"
  value       = module.ecs_app.dagster_url
}

output "timescale_endpoint" {
  description = "TimescaleDB RDS endpoint"
  value       = module.timescale.endpoint
  sensitive   = true
}

output "kafka_bootstrap_brokers" {
  description = "MSK bootstrap brokers (TLS)"
  value       = module.streaming.bootstrap_brokers
  sensitive   = true
}

output "s3_bucket" {
  description = "S3 bucket for protocols and ML artefacts"
  value       = module.storage.bucket_name
}

output "grafana_url" {
  description = "Amazon Managed Grafana workspace URL"
  value       = module.observability.grafana_url
}
