"""
Airflow DAG cho gold data aggregation
Tổng hợp thống kê từ sessions và forms vào gold layer
"""
from datetime import datetime, timedelta
import os
import sys
from pathlib import Path
import asyncio

from airflow import DAG
from airflow.operators.python import PythonOperator

# Add api app to path
# Try multiple paths (local development and Docker mount)
api_paths = [
    Path("/opt/airflow/api/app"),  # Docker mount path
    Path(__file__).parent.parent.parent / "api" / "app",  # Local development
]
for api_path in api_paths:
    if api_path.exists():
        sys.path.insert(0, str(api_path))
        break

# Import gold aggregator functions
try:
    from gold_aggregator import upsert_gold_data
    from motor.motor_asyncio import AsyncIOMotorClient
    GOLD_AGGREGATOR_IMPORTED = True
except ImportError as e:
    print(f"Warning: Could not import gold aggregator modules: {e}")
    GOLD_AGGREGATOR_IMPORTED = False


def run_gold_aggregation_task(**context):
    """Task để chạy gold data aggregation"""
    if not GOLD_AGGREGATOR_IMPORTED:
        raise ImportError("Gold aggregator modules not available. Check path configuration.")
    
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://mongodb:27017/forms")
    
    print(f"Starting gold data aggregation task")
    print(f"  MongoDB URI: {mongodb_uri}")

    async def aggregate():
        """Async function để chạy aggregation"""
        client = AsyncIOMotorClient(mongodb_uri)
        try:
            # Get database
            if "/" in mongodb_uri.split("mongodb://")[-1]:
                db = client.get_default_database()
            else:
                db = client["forms"]

            # Aggregate all forms statistics
            print("Aggregating all forms statistics...")
            await upsert_gold_data(db, form_id=None)
            
            print("Gold data aggregation completed successfully")
            return {"status": "success"}
        finally:
            client.close()

    # Run async function
    # Try to get existing event loop, or create new one
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    result = loop.run_until_complete(aggregate())
    return result


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
    "gold_data_dag",
    default_args=default_args,
    description="DAG để tổng hợp thống kê vào gold layer",
    schedule_interval="*/5 * * * *",  # Chạy mỗi 5 phút
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gold", "aggregation", "statistics"],
)

# Task
gold_aggregation_task = PythonOperator(
    task_id="run_gold_aggregation",
    python_callable=run_gold_aggregation_task,
    dag=dag,
)

