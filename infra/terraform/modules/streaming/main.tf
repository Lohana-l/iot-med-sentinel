variable "project_name"        { type = string }
variable "environment"         { type = string }
variable "vpc_id"              { type = string }
variable "subnet_ids"          { type = list(string) }
variable "kafka_instance_type" { type = string }
variable "broker_count"        { type = number }

resource "aws_security_group" "msk" {
  name   = "${var.project_name}-${var.environment}-msk-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 9094
    to_port     = 9094
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.project_name}-${var.environment}"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type   = var.kafka_instance_type
    client_subnets  = slice(var.subnet_ids, 0, var.broker_count)
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info { volume_size = 20 }
    }
  }

  encryption_info {
    encryption_in_transit { client_broker = "TLS" }
  }

  tags = { Name = "${var.project_name}-${var.environment}-msk" }
}

output "bootstrap_brokers" { value = aws_msk_cluster.main.bootstrap_brokers_tls }
