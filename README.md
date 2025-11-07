# FormBot OCR Stack (Docker Compose + OpenAI Q&A)

## Quickstart (Local with LocalStack)

1. Copy env:
   - See `ENV_EXAMPLE.md` and create `.env` in repo root.
   - For LocalStack dev, set `S3_ENDPOINT_URL=http://localstack:4566` and a `FORMS_QUEUE_URL` pointing to LocalStack.

2. Start stack (with LocalStack profile):

```bash
docker compose --profile dev up -d --build
```

3. Verify services:
- API: http://localhost:8000/healthz
- Frontend: http://localhost:3000

4. Seed sample form:
- The `crawler` uploads a sample PDF to S3.
- LocalStack notification sends SQS message.
- `worker` consumes, OCRs minimally, and writes a form record to Mongo.

5. Use the app:
- Open frontend, select a form, answer questions, generate PDF.

## Production Notes (AWS)
- Use real S3/SQS and remove `S3_ENDPOINT_URL`.
- Provide `AWS_ACCESS_KEY_ID/SECRET/REGION`.
- Consider deploying services to ECS/EKS and MongoDB Atlas.

## Terraform (AWS)
- See `infra/terraform/` for S3 bucket, SQS queue, S3->SQS notification, and basic IAM.


