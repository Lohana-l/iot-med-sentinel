variable "project_name"       { type = string }
variable "environment"        { type = string }
variable "vpc_id"             { type = string }
variable "public_subnet_ids"  { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "streamlit_cpu"      { type = number }
variable "streamlit_memory"   { type = number }
variable "dagster_cpu"        { type = number }
variable "dagster_memory"     { type = number }
variable "db_host"            { type = string }
variable "kafka_brokers"      { type = string }
variable "s3_bucket"          { type = string }

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-ecs-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_security_group" "streamlit_alb" {
  name   = "${var.project_name}-${var.environment}-streamlit-alb-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "streamlit" {
  name               = "${var.project_name}-${var.environment}-streamlit"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.streamlit_alb.id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "streamlit" {
  name        = "${var.project_name}-${var.environment}-streamlit"
  port        = 8501
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/_stcore/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "streamlit" {
  load_balancer_arn = aws_lb.streamlit.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.streamlit.arn
  }
}

resource "aws_ecs_task_definition" "streamlit" {
  family                   = "${var.project_name}-${var.environment}-streamlit"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.streamlit_cpu
  memory                   = var.streamlit_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name      = "streamlit"
    image     = "ghcr.io/vigistock/streamlit:latest"
    essential = true
    portMappings = [{ containerPort = 8501, protocol = "tcp" }]
    environment = [
      { name = "USE_MOCK_DATA", value = "false" },
      { name = "TIMESCALE_HOST", value = var.db_host },
      { name = "KAFKA_BROKERS",  value = var.kafka_brokers },
      { name = "S3_BUCKET",      value = var.s3_bucket },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${var.project_name}-${var.environment}/streamlit"
        "awslogs-region"        = "eu-west-3"
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_security_group" "ecs_tasks" {
  name   = "${var.project_name}-${var.environment}-ecs-tasks-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.streamlit_alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_service" "streamlit" {
  name            = "${var.project_name}-${var.environment}-streamlit"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.streamlit.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.streamlit.arn
    container_name   = "streamlit"
    container_port   = 8501
  }
}

resource "aws_ecs_task_definition" "dagster" {
  family                   = "${var.project_name}-${var.environment}-dagster"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.dagster_cpu
  memory                   = var.dagster_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name      = "dagster"
    image     = "ghcr.io/vigistock/dagster:latest"
    essential = true
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]
    environment = [
      { name = "TIMESCALE_HOST", value = var.db_host },
      { name = "KAFKA_BROKERS",  value = var.kafka_brokers },
      { name = "S3_BUCKET",      value = var.s3_bucket },
    ]
    command = ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", "/app/orchestration/dagster/workspace.yaml"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${var.project_name}-${var.environment}/dagster"
        "awslogs-region"        = "eu-west-3"
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "dagster" {
  name            = "${var.project_name}-${var.environment}-dagster"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.dagster.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.ecs_tasks.id]
  }
}

output "streamlit_url" { value = "http://${aws_lb.streamlit.dns_name}" }
output "dagster_url"   { value = "internal: access via VPN or bastion" }
