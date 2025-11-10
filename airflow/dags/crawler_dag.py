"""
Airflow DAG cho crawler service
Chạy crawler để tải các form từ các nguồn và upload lên S3
"""
from datetime import datetime, timedelta
import os
import sys
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
import logging

# Configure logging for Airflow
logger = logging.getLogger(__name__)

# Add crawler app to path
# Try multiple paths (local development and Docker mount)
crawler_paths = [
    Path("/opt/airflow/crawler/app"),  # Docker mount path
    Path(__file__).parent.parent.parent / "crawler" / "app",  # Local development
]
for crawler_path in crawler_paths:
    if crawler_path.exists():
        sys.path.insert(0, str(crawler_path))
        break

# Import crawler functions
try:
    from main import (
        get_mongo_client,
        crawl_form_source,
        FORM_SOURCES,
        get_content_type,
    )
    import boto3
    CRAWLER_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import crawler modules: {e}")
    CRAWLER_IMPORTED = False
    FORM_SOURCES = []


def run_crawler_task(**context):
    """Task để chạy crawler"""
    if not CRAWLER_IMPORTED:
        raise ImportError("Crawler modules not available. Check path configuration.")
    
    bucket = os.getenv("FORMS_BUCKET", "form-files")
    endpoint = os.getenv("S3_ENDPOINT_URL") or None

    logger.info(f"Starting crawler task")
    logger.info(f"  Bucket: {bucket}")
    logger.info(f"  Endpoint: {endpoint}")
    logger.info(f"  Sources: {len(FORM_SOURCES)}")
    print(f"Starting crawler task")
    print(f"  Bucket: {bucket}")
    print(f"  Endpoint: {endpoint}")
    print(f"  Sources: {len(FORM_SOURCES)}")

    # Initialize clients
    s3_client = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    mongo_client = get_mongo_client()
    db = mongo_client.get_default_database()

    # Create index for fast lookups
    db.crawled_forms.create_index([("url", 1), ("content_hash", 1)], unique=True)
    db.crawled_forms.create_index([("crawled_at", -1)])

    stats = {"new": 0, "skipped": 0, "failed": 0}

    for source in FORM_SOURCES:
        try:
            is_new = crawl_form_source(source, s3_client, bucket, db)
            if is_new:
                stats["new"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            error_msg = f"Failed to crawl {source['name']}: {e}"
            logger.error(error_msg, exc_info=True)
            print(error_msg)
            stats["failed"] += 1

    summary = "=" * 60 + "\n"
    summary += "Crawl run completed:\n"
    summary += f"  ✓ New forms: {stats['new']}\n"
    summary += f"  ⊘ Skipped (duplicates): {stats['skipped']}\n"
    summary += f"  ✗ Failed: {stats['failed']}\n"
    summary += "=" * 60
    
    logger.info(summary)
    print(summary)

    return stats


# Default arguments
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# DAG definition
dag = DAG(
    "crawler_dag",
    default_args=default_args,
    description="DAG để crawl các form từ các nguồn và upload lên S3. Có thể trigger manual hoặc chạy theo schedule.",
    schedule_interval="0 3 * * *",  # Chạy hàng ngày lúc 3h sáng (có thể trigger manual bất cứ lúc nào)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["crawler", "forms"],
)

# Task
crawler_task = PythonOperator(
    task_id="run_crawler",
    python_callable=run_crawler_task,
    dag=dag,
)

