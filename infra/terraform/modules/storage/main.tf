variable "project_name" { type = string }
variable "environment"  { type = string }

resource "aws_s3_bucket" "main" {
  bucket = "${var.project_name}-${var.environment}-data"
  tags   = { Name = "${var.project_name}-${var.environment}-data" }
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket                  = aws_s3_bucket.main.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Folders: protocols/ (PDF seed docs) and models/ (ML artefacts)
resource "aws_s3_object" "protocols_prefix" {
  bucket = aws_s3_bucket.main.id
  key    = "protocols/"
}

resource "aws_s3_object" "models_prefix" {
  bucket = aws_s3_bucket.main.id
  key    = "models/"
}

output "bucket_name" { value = aws_s3_bucket.main.bucket }
output "bucket_arn"  { value = aws_s3_bucket.main.arn }
