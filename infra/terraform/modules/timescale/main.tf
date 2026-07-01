variable "project_name"      { type = string }
variable "environment"       { type = string }
variable "vpc_id"            { type = string }
variable "subnet_ids"        { type = list(string) }
variable "instance_class"    { type = string }
variable "allocated_storage" { type = number }
variable "db_password" {
  type      = string
  sensitive = true
}

locals {
  db_name     = "vigistock"
  db_username = "vigistock"
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  name   = "${var.project_name}-${var.environment}-db-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "timescale" {
  identifier        = "${var.project_name}-${var.environment}-timescale"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage

  db_name  = local.db_name
  username = local.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]

  # TimescaleDB is installed via the init script / Dagster asset on first boot.
  # In production, consider using Timescale Cloud instead of self-managed RDS.
  parameter_group_name = "default.postgres16"

  # Chiffrement au repos : non negociable pour un projet sante, meme sans
  # donnee patient. Cle KMS geree par AWS (alias/aws/rds) par defaut.
  storage_encrypted = true

  # Journaux PostgreSQL vers CloudWatch : indispensable pour l'audit.
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  skip_final_snapshot     = var.environment == "dev"
  backup_retention_period = var.environment == "prod" ? 7 : 0
  multi_az                = var.environment == "prod"
  deletion_protection     = var.environment == "prod"

  tags = { Name = "${var.project_name}-${var.environment}-timescale" }
}

output "endpoint" { value = aws_db_instance.timescale.endpoint }
