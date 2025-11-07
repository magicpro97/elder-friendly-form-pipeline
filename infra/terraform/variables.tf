variable "region" {
  type        = string
  description = "AWS region"
  default     = "ap-southeast-1"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name for form files"
}

variable "queue_name" {
  type        = string
  description = "SQS queue name for S3 events"
}

