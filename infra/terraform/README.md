# Terraform - Cloud Deployment (OPTIONAL)

> **Statut : blueprint indicatif, jamais appliqué en production.**
> Ce module n'est **pas nécessaire** pour faire tourner le projet en local (`docker compose up`).
> Il documente la cible AWS du projet (la table de portabilité du README racine) et il est
> validé en CI (`terraform fmt -check` + `terraform validate`, sans credentials).
>
> État par module : `network`, `timescale`, `streaming`, `storage` et `observability` sont
> complets et appliquables. `ecs_app` est volontairement esquissé : les task definitions
> détaillées, les rôles IAM fins et l'ALB restent à écrire avant un vrai déploiement.
> C'est un choix assumé : le périmètre du projet est la stack locale 100 % open source.

## Ce que ça déploie

| Module | Équivalent local | AWS |
|--------|-----------------|-----|
| `network` | - | VPC, subnets publics/privés, NAT gateway |
| `ecs_app` | docker-compose services | ECS Fargate (Streamlit, Dagster, ChromaDB) |
| `streaming` | Redpanda container | Amazon MSK (Kafka-compatible) |
| `timescale` | TimescaleDB container | RDS PostgreSQL 16 + TimescaleDB extension |
| `storage` | MinIO container | S3 buckets (protocoles, artefacts ML) |
| `observability` | Grafana container | Amazon Managed Grafana + CloudWatch |

## Prérequis

```bash
terraform >= 1.7
aws-cli >= 2.x   # configuré avec les bons credentials
```

## Usage

```bash
cd infra/terraform

# Init
terraform init

# Plan (env dev)
terraform plan -var-file=env/dev.tfvars

# Apply
terraform apply -var-file=env/prod.tfvars
```

## Environnements

- `env/dev.tfvars` : instance types réduits, single-AZ, coût minimal
- `env/prod.tfvars` : multi-AZ, auto-scaling, backup activé

## Secrets et state

- `db_password` : ne jamais le poser dans un tfvars commité ; l'injecter via
  `TF_VAR_db_password` ou AWS Secrets Manager (voir `terraform.tfvars.example`).
- State distant : bloc backend S3 + verrou DynamoDB prêt à décommenter dans
  `versions.tf` dès que le projet n'est plus mono-développeur.
