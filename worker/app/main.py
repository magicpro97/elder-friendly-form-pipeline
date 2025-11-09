import json
import logging
import os
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError
from pymongo import MongoClient

try:
    # When executed as a package inside Docker: python -m app.main
    from .ocr import ocr_extract_fields
except ImportError:
    # When executed directly: python main.py
    from ocr import ocr_extract_fields

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def mongo_client():
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/forms")
    return MongoClient(uri)


def get_sqs_client():
    endpoint = os.getenv("AWS_ENDPOINT_URL") or os.getenv("S3_ENDPOINT_URL") or None
    return boto3.client(
        "sqs",
        region_name=os.getenv("AWS_REGION"),
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def get_s3_client():
    endpoint = os.getenv("AWS_ENDPOINT_URL") or os.getenv("S3_ENDPOINT_URL") or None
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def parse_s3_event(body: str) -> Dict[str, Any]:
    data = json.loads(body)
    # S3 via SQS format: handle minimal case
    recs = data.get("Records", [])
    for r in recs:
        if r.get("eventSource") == "aws:s3":
            bucket = r["s3"]["bucket"]["name"]
            key = r["s3"]["object"]["key"]
            return {"bucket": bucket, "key": key}
    # fallback to custom
    return {"bucket": data.get("bucket"), "key": data.get("key")}


def run_once():
    queue_url = os.getenv("FORMS_QUEUE_URL")
    if not queue_url:
        print("[worker] FORMS_QUEUE_URL not set; sleeping 10s")
        time.sleep(10)
        return

    sqs = get_sqs_client()
    s3 = get_s3_client()
    mongo = mongo_client()
    db = (
        mongo.get_default_database()
        if "/" in os.getenv("MONGODB_URI", "")
        else mongo["forms"]
    )

    try:
        print("[worker] Long polling SQS for messages...")
        resp = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=10
        )
    except ClientError as e:
        print("[worker] SQS error", e)
        time.sleep(5)
        return

    messages = resp.get("Messages", [])
    if not messages:
        print("[worker] No messages received")
        return

    msg = messages[0]
    receipt = msg["ReceiptHandle"]
    event = parse_s3_event(msg.get("Body", "{}"))
    if not event.get("bucket") or not event.get("key"):
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
        return

    print(f"[worker] Processing s3://{event['bucket']}/{event['key']}")
    obj = s3.get_object(Bucket=event["bucket"], Key=event["key"])
    content = obj["Body"].read()

    schema = ocr_extract_fields(content, event["key"])  # minimal extraction

    # If DOC/DOCX was converted to PDF, upload the PDF to S3
    if schema.get("was_converted") and schema.get("converted_pdf_bytes"):
        # Upload converted PDF with .pdf extension
        original_key = event["key"]
        # Change extension to .pdf (e.g., raw/file.doc -> raw/file.pdf)
        if original_key.endswith(".doc") or original_key.endswith(".docx"):
            pdf_key = original_key.rsplit(".", 1)[0] + ".pdf"
        else:
            pdf_key = original_key + ".pdf"

        print(f"[worker] Uploading converted PDF to s3://{event['bucket']}/{pdf_key}")
        s3.put_object(
            Bucket=event["bucket"],
            Key=pdf_key,
            Body=schema["converted_pdf_bytes"],
            ContentType="application/pdf",
        )

        # Update schema to point to PDF
        schema["source"] = {"bucket": event["bucket"], "key": pdf_key}
        schema["id"] = pdf_key  # Use PDF key as form ID
        schema["original_key"] = original_key  # Keep reference to original DOC
        print(f"[worker] Converted form will use PDF: {pdf_key}")

        # Remove bytes from schema before MongoDB
        del schema["converted_pdf_bytes"]
        del schema["was_converted"]
    else:
        # Original file (PDF, image, etc.)
        schema["id"] = event["key"]
        schema["source"] = {"bucket": event["bucket"], "key": event["key"]}

    # Use extracted title if available, otherwise fallback to filename
    title = schema.get("extracted_title") or os.path.basename(schema["id"])

    schema.update({"title": title, "createdAt": int(time.time())})
    db.forms.update_one({"id": schema["id"]}, {"$set": schema}, upsert=True)
    print(f"[worker] Upserted form schema: {schema['id']}, title: {title}")

    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
    print("[worker] Deleted SQS message")


def main():
    print("[worker] Started. Waiting for SQS messages...")
    while True:
        run_once()
        time.sleep(1)


if __name__ == "__main__":
    main()
