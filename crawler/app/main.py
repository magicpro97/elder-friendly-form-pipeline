import hashlib
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import urllib3

import boto3
import requests
from pymongo import MongoClient

# Disable SSL warnings when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Multi-source URLs for diverse forms
FORM_SOURCES = [
    {
        "url": "https://csdl.dichvucong.gov.vn/web/jsp/download_file.jsp?ma=3fe8b5e4d7f9fe86",
        "name": "gov_mau9_don_xin_viec",
        "source": "gov.vn",
        "format": "doc",
    },
    {
        "url": "https://static.topcv.vn/cms/19d60037982db4e139cd6b99f3adfefa.docx",
        "name": "topcv_don_xin_viec",
        "source": "topcv.vn",
        "format": "docx",
    },
    {
        "url": "https://thanhpho.laichau.gov.vn/upload/103883/20231117/MAU_PHIEU_DANG_KY_DU_TUYEN_02_3783a.pdf",
        "name": "laichau_phieu_dang_ky",
        "source": "gov.vn",
        "format": "pdf",
    },
]


def get_mongo_client():
    """Get MongoDB client for tracking crawled forms"""
    uri = os.getenv("MONGODB_URI", "mongodb://mongodb:27017/forms")
    return MongoClient(uri)


def compute_file_hash(content: bytes) -> str:
    """Compute SHA256 hash of file content"""
    return hashlib.sha256(content).hexdigest()


def is_form_already_crawled(db, url: str, content_hash: str) -> Optional[Dict]:
    """
    Check if form with same URL and content hash already exists

    Returns:
        Existing form document if found, None otherwise
    """
    return db.crawled_forms.find_one({"url": url, "content_hash": content_hash})


def download_form(url: str, timeout: int = 60) -> bytes:
    """Download form content from URL"""
    logger.info(f"Downloading from {url}")
    try:
        # Try with SSL verification first
        resp = requests.get(url, timeout=timeout, verify=True)
        resp.raise_for_status()
        logger.info(f"Downloaded {len(resp.content)} bytes")
        return resp.content
    except requests.exceptions.SSLError as e:
        # If SSL certificate verification fails (expired cert, etc.), try without verification
        logger.warning(f"SSL verification failed for {url}: {e}")
        logger.warning("Retrying without SSL verification...")
        resp = requests.get(url, timeout=timeout, verify=False)
        resp.raise_for_status()
        logger.info(f"Downloaded {len(resp.content)} bytes (without SSL verification)")
        return resp.content


def upload_to_s3(
    s3_client, bucket: str, key: str, content: bytes, content_type: str
) -> None:
    """Upload file content to S3"""
    tmp_dir = Path(os.getenv("TMP_DIR", tempfile.gettempdir()))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "temp_form"

    tmp_path.write_bytes(content)
    logger.info(f"Uploading to s3://{bucket}/{key}")

    s3_client.upload_file(
        str(tmp_path),
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )

    tmp_path.unlink()  # Clean up temp file
    logger.info(f"Successfully uploaded to s3://{bucket}/{key}")


def get_content_type(format: str) -> str:
    """Get MIME type for file format"""
    types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return types.get(format, "application/octet-stream")


def crawl_form_source(source: Dict, s3_client, bucket: str, db) -> bool:
    """
    Crawl a single form source

    Returns:
        True if form was newly uploaded, False if skipped (duplicate)
    """
    url = source["url"]
    name = source["name"]
    source_name = source["source"]
    format = source["format"]

    try:
        # Download form content
        content = download_form(url)
        content_hash = compute_file_hash(content)

        # Check if already crawled
        existing = is_form_already_crawled(db, url, content_hash)
        if existing:
            logger.info(
                f"✓ Skipping {name} - already crawled on "
                f"{existing['crawled_at']} (hash: {content_hash[:8]}...)"
            )
            # Update last_checked timestamp
            db.crawled_forms.update_one(
                {"_id": existing["_id"]}, {"$set": {"last_checked": datetime.utcnow()}}
            )
            return False

        # Generate S3 key with timestamp
        ts = int(time.time())
        s3_key = f"raw/{name}-{ts}.{format}"

        # Upload to S3
        content_type = get_content_type(format)
        logger.info(f"Uploading to S3: s3://{bucket}/{s3_key}")
        upload_to_s3(s3_client, bucket, s3_key, content, content_type)
        logger.info(f"✓ Successfully uploaded to S3: s3://{bucket}/{s3_key}")

        # Track in MongoDB
        db.crawled_forms.insert_one(
            {
                "url": url,
                "name": name,
                "source": source_name,
                "format": format,
                "content_hash": content_hash,
                "s3_key": s3_key,
                "s3_bucket": bucket,
                "crawled_at": datetime.utcnow(),
                "last_checked": datetime.utcnow(),
                "file_size": len(content),
            }
        )

        logger.info(f"✓ Successfully crawled new form: {name} → s3://{bucket}/{s3_key}")
        return True

    except Exception as e:
        logger.error(f"✗ Failed to crawl {name} from {url}: {e}", exc_info=True)
        return False


def upload_doc_from_url(bucket: str, key: str, endpoint_url: str | None):
    """Legacy function - kept for backward compatibility"""
    logger.warning("upload_doc_from_url is deprecated, use crawl_form_source instead")
    # This function is no longer used, but kept to avoid breaking imports


def main():
    """
    Smart crawler with deduplication and multi-source support

    Strategy:
    1. Connect to MongoDB for tracking
    2. For each source URL:
       - Download content
       - Compute SHA256 hash
       - Skip if already crawled (same hash)
       - Upload to S3 if new/changed
       - Track in MongoDB
    3. Sleep 24h and repeat
    """
    bucket = os.getenv("FORMS_BUCKET", "form-files")
    endpoint = os.getenv("S3_ENDPOINT_URL") or None

    logger.info("Starting smart crawler")
    logger.info(f"  Bucket: {bucket}")
    logger.info(f"  Endpoint: {endpoint}")
    logger.info(f"  Sources: {len(FORM_SOURCES)}")

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

    def run_crawl():
        """Execute one crawl iteration"""
        logger.info("=" * 60)
        logger.info(f"Starting crawl run at {datetime.utcnow()}")
        logger.info("=" * 60)

        stats = {"new": 0, "skipped": 0, "failed": 0}

        for source in FORM_SOURCES:
            try:
                is_new = crawl_form_source(source, s3_client, bucket, db)
                if is_new:
                    stats["new"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"Failed to crawl {source['name']}: {e}")
                stats["failed"] += 1

        logger.info("=" * 60)
        logger.info("Crawl run completed:")
        logger.info(f"  ✓ New forms: {stats['new']}")
        logger.info(f"  ⊘ Skipped (duplicates): {stats['skipped']}")
        logger.info(f"  ✗ Failed: {stats['failed']}")
        logger.info("=" * 60)

    # Run immediately, then daily
    while True:
        try:
            run_crawl()
        except Exception as e:
            logger.error(f"Error during crawl run: {e}", exc_info=True)

        logger.info("Sleeping for 24 hours until next run...")
        time.sleep(24 * 3600)


if __name__ == "__main__":
    main()
