module "network" {
  source       = "./modules/network"
  project_name = var.project_name
  environment  = var.environment
  vpc_cidr     = var.vpc_cidr
}

module "storage" {
  source       = "./modules/storage"
  project_name = var.project_name
  environment  = var.environment
}

module "timescale" {
  source               = "./modules/timescale"
  project_name         = var.project_name
  environment          = var.environment
  subnet_ids           = module.network.private_subnet_ids
  vpc_id               = module.network.vpc_id
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  db_password          = var.db_password
}

module "streaming" {
  source              = "./modules/streaming"
  project_name        = var.project_name
  environment         = var.environment
  subnet_ids          = module.network.private_subnet_ids
  vpc_id              = module.network.vpc_id
  kafka_instance_type = var.kafka_instance_type
  broker_count        = var.kafka_broker_count
}

module "ecs_app" {
  source           = "./modules/ecs_app"
  project_name     = var.project_name
  environment      = var.environment
  vpc_id           = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  private_subnet_ids = module.network.private_subnet_ids
  streamlit_cpu    = var.streamlit_cpu
  streamlit_memory = var.streamlit_memory
  dagster_cpu      = var.dagster_cpu
  dagster_memory   = var.dagster_memory
  db_host          = module.timescale.endpoint
  kafka_brokers    = module.streaming.bootstrap_brokers
  s3_bucket        = module.storage.bucket_name
}

module "observability" {
  source       = "./modules/observability"
  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.network.vpc_id
  subnet_ids   = module.network.private_subnet_ids
}
