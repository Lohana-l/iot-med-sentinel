terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State distant : a activer des qu'on n'est plus seul sur le projet.
  # Pre-requis : bucket S3 versionne + table DynamoDB pour le verrou.
  # backend "s3" {
  #   bucket         = "vigistock-tfstate"
  #   key            = "vigistock/terraform.tfstate"
  #   region         = "eu-west-3"
  #   dynamodb_table = "vigistock-tf-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "vigistock"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
