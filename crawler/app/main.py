import logging
import os
import time
import tempfile
from pathlib import Path

import boto3
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DOC_URL = "https://static.topcv.vn/cms/19d60037982db4e139cd6b99f3adfefa.docx"


def upload_doc_from_url(bucket: str, key: str, endpoint_url: str | None):
    logger.info(f"Downloading file from {DOC_URL}")
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    # Cross-platform temp dir (works on Windows and Linux/Docker)
    tmp_dir = Path(os.getenv("TMP_DIR", tempfile.gettempdir()))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "file.docx"
    resp = requests.get(DOC_URL, timeout=60)
    resp.raise_for_status()
    tmp_path.write_bytes(resp.content)
    logger.info(f"Downloaded {len(resp.content)} bytes")
    
    logger.info(f"Uploading to s3://{bucket}/{key}")
    s3.upload_file(
        str(tmp_path),
        bucket,
        key,
        ExtraArgs={
            "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        },
    )
    logger.info(f"Successfully uploaded to s3://{bucket}/{key}")


def main():
    # Hardcoded daily loop for Docker runtime
    bucket = os.getenv("FORMS_BUCKET", "form-files")
    endpoint = os.getenv("S3_ENDPOINT_URL") or None
    logger.info(f"Starting crawler with bucket={bucket}, endpoint={endpoint}")

    def run():
        try:
            ts = int(time.time())
            key = f"raw/topcv-{ts}.docx"
            upload_doc_from_url(bucket, key, endpoint)
        except Exception as e:
            logger.error(f"Error during run: {e}", exc_info=True)

    # Run immediately, then daily
    while True:
        run()
        logger.info("Sleeping for 24 hours until next run...")
        time.sleep(24 * 3600)


if __name__ == "__main__":
    main()


