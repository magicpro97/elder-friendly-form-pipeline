terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_s3_bucket" "forms" {
  bucket = var.bucket_name
}

resource "aws_sqs_queue" "forms" {
  name = var.queue_name
}

resource "aws_s3_bucket_notification" "forms_to_sqs" {
  bucket = aws_s3_bucket.forms.id

  queue {
    queue_arn     = aws_sqs_queue.forms.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = ""
  }
}

output "bucket_name" { value = aws_s3_bucket.forms.bucket }
output "queue_url"   { value = aws_sqs_queue.forms.id }

