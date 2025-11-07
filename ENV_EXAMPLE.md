# Environment Example

Copy to `.env` and adjust values.

```
MONGODB_URI=mongodb://mongodb:27017/forms

# AWS
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_REGION=ap-southeast-1

# S3
FORMS_BUCKET=form-files
# For LocalStack dev: http://localstack:4566 ; leave empty for prod
S3_ENDPOINT_URL=

# SQS
# For LocalStack dev (assuming default account):
FORMS_QUEUE_URL=http://localstack:4566/000000000000/forms-queue

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# API
API_PORT=8000
CORS_ORIGINS=*
```

