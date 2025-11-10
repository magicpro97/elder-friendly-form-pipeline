"""
Airflow DAG cho worker service
Worker vẫn dùng SQS để handle messages, nhưng có thể trigger processing từ Airflow nếu cần
"""
from datetime import datetime, timedelta
import os
import sys
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

# Add worker app to path
# Try multiple paths (local development and Docker mount)
worker_paths = [
    Path("/opt/airflow/worker/app"),  # Docker mount path
    Path(__file__).parent.parent.parent / "worker" / "app",  # Local development
]
for worker_path in worker_paths:
    if worker_path.exists():
        sys.path.insert(0, str(worker_path))
        break

# Import worker functions
try:
    # When mounted as /opt/airflow/worker/app, we can import directly
    from main import (
        get_sqs_client,
        get_s3_client,
        mongo_client,
        parse_s3_event,
        run_once,
    )
    from ocr import ocr_extract_fields
    import boto3
    from botocore.exceptions import ClientError
    WORKER_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import worker modules: {e}")
    WORKER_IMPORTED = False


def check_worker_health(**context):
    """Task để kiểm tra health của worker (SQS queue status)"""
    import logging
    task_logger = logging.getLogger(__name__)
    
    if not WORKER_IMPORTED:
        raise ImportError("Worker modules not available. Check path configuration.")
    
    queue_url = os.getenv("FORMS_QUEUE_URL")
    if not queue_url:
        msg = "FORMS_QUEUE_URL not set, skipping health check"
        task_logger.warning(msg)
        print(msg)
        return {"status": "skipped", "reason": "FORMS_QUEUE_URL not set"}
    
    try:
        sqs = get_sqs_client()
        
        # Get queue attributes
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        
        messages = int(attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
        in_flight = int(attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0))
        
        status_msg = f"SQS Queue Status:\n  Queue URL: {queue_url}\n  Pending messages: {messages}\n  In-flight messages: {in_flight}"
        task_logger.info(status_msg)
        print(status_msg)
        
        return {
            "status": "healthy",
            "pending_messages": messages,
            "in_flight_messages": in_flight
        }
    except Exception as e:
        error_msg = f"Error checking worker health: {e}"
        task_logger.error(error_msg, exc_info=True)
        print(error_msg)
        return {"status": "error", "error": str(e)}


def process_single_message(**context):
    """Task để process một message từ SQS queue (nếu có)"""
    import logging
    
    task_logger = logging.getLogger(__name__)
    
    if not WORKER_IMPORTED:
        raise ImportError("Worker modules not available. Check path configuration.")
    
    queue_url = os.getenv("FORMS_QUEUE_URL")
    if not queue_url:
        msg = "FORMS_QUEUE_URL not set, skipping message processing"
        task_logger.warning(msg)
        print(msg)
        return {"status": "skipped", "reason": "FORMS_QUEUE_URL not set"}
    
    try:
        task_logger.info("=" * 60)
        task_logger.info(f"Starting worker message processing")
        task_logger.info(f"  Queue URL: {queue_url}")
        task_logger.info("=" * 60)
        print("=" * 60)
        print(f"Starting worker message processing")
        print(f"  Queue URL: {queue_url}")
        print("=" * 60)
        
        # Capture stdout to ensure all print statements from run_once() are visible
        # Note: run_once() uses print() statements, which should be captured by Airflow
        # But we'll also log explicitly to ensure visibility
        
        # Run worker once to process a single message
        task_logger.info("Calling run_once() to process message from SQS...")
        print("Calling run_once() to process message from SQS...")
        
        result = run_once()
        
        # Log completion
        task_logger.info("=" * 60)
        task_logger.info("Worker message processing completed")
        if result:
            task_logger.info(f"  Result: {result}")
        else:
            task_logger.info("  No message was available to process (or processing completed)")
        task_logger.info("=" * 60)
        print("=" * 60)
        print("Worker message processing completed")
        if result:
            print(f"  Result: {result}")
        else:
            print("  No message was available to process (or processing completed)")
        print("=" * 60)
        
        return {"status": "completed", "result": result}
    except Exception as e:
        error_msg = f"Error processing message: {e}"
        task_logger.error("=" * 60)
        task_logger.error("ERROR in worker message processing")
        task_logger.error(error_msg, exc_info=True)
        task_logger.error("=" * 60)
        print("=" * 60)
        print("ERROR in worker message processing")
        print(error_msg)
        print("=" * 60)
        return {"status": "error", "error": str(e)}


def process_s3_file(bucket: str, key: str, **context):
    """Task để process một file cụ thể từ S3 (bypass SQS)"""
    if not WORKER_IMPORTED:
        raise ImportError("Worker modules not available. Check path configuration.")
    
    print(f"Processing file: s3://{bucket}/{key}")
    
    try:
        s3 = get_s3_client()
        mongo = mongo_client()
        db = (
            mongo.get_default_database()
            if "/" in os.getenv("MONGODB_URI", "")
            else mongo["forms"]
        )
        
        # Download file from S3
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read()
        
        # Process with OCR
        schema = ocr_extract_fields(content, key)
        
        # Handle conversion if needed
        if schema.get("was_converted") and schema.get("converted_pdf_bytes"):
            original_key = key
            if original_key.endswith(".doc") or original_key.endswith(".docx"):
                pdf_key = original_key.rsplit(".", 1)[0] + ".pdf"
            else:
                pdf_key = original_key + ".pdf"
            
            print(f"Uploading converted PDF to s3://{bucket}/{pdf_key}")
            s3.put_object(
                Bucket=bucket,
                Key=pdf_key,
                Body=schema["converted_pdf_bytes"],
                ContentType="application/pdf",
            )
            
            schema["source"] = {"bucket": bucket, "key": pdf_key}
            schema["id"] = pdf_key
            schema["original_key"] = original_key
            
            del schema["converted_pdf_bytes"]
            del schema["was_converted"]
        else:
            schema["id"] = key
            schema["source"] = {"bucket": bucket, "key": key}
        
        # Save to MongoDB
        import time
        title = schema.get("extracted_title") or os.path.basename(schema["id"])
        schema.update({"title": title, "createdAt": int(time.time())})
        db.forms.update_one({"id": schema["id"]}, {"$set": schema}, upsert=True)
        
        print(f"Successfully processed: {schema['id']}, title: {title}")
        return {"status": "success", "form_id": schema["id"], "title": title}
        
    except Exception as e:
        print(f"Error processing file: {e}")
        raise


# Default arguments
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# DAG definition - Worker health check
worker_health_dag = DAG(
    "worker_health_check",
    default_args=default_args,
    description="DAG để kiểm tra health của worker và SQS queue",
    schedule_interval="*/30 * * * *",  # Chạy mỗi 30 phút
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["worker", "health", "sqs"],
)

# Task: Check worker health
worker_health_task = PythonOperator(
    task_id="check_worker_health",
    python_callable=check_worker_health,
    dag=worker_health_dag,
)

# DAG definition - Process messages from queue
worker_process_dag = DAG(
    "worker_process_queue",
    default_args=default_args,
    description="DAG để process messages từ SQS queue (backup nếu worker service down)",
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["worker", "sqs", "processing"],
)

# Task: Process single message
worker_process_task = PythonOperator(
    task_id="process_single_message",
    python_callable=process_single_message,
    dag=worker_process_dag,
)

