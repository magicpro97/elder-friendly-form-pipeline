"""
Crawler configuration settings
Load from environment variables or use defaults
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "crawler_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Crawler settings
# Crawler settings
CRAWLER_TARGETS = os.getenv(
    "CRAWLER_TARGETS", "https://thuvienphapluat.vn,https://luatsubaoho.com"  # Default Vietnamese form sites
).split(",")

# Vietnamese form-specific settings
CRITICAL_KEYWORDS = os.getenv(
    "CRITICAL_KEYWORDS",
    "mẫu,đơn,biểu mẫu,tờ khai,don,phieu,phieu dang ky,bieu mau,phieu-dang-ky,mau-bien-ban,bang-ke-to-khai,bang-ke,to-khai",
).split(",")

ALL_KEYWORDS = CRITICAL_KEYWORDS + ["file", "tải", "download", ".doc", ".pdf", ".jpg", ".png", ".xls", ".xlsx"]

# Date filtering (only crawl forms published after this date)
DB_DATE_STR = os.getenv("DB_DATE", "2024-01-01")  # Format: YYYY-MM-DD
try:
    from datetime import datetime

    DB_DATE = datetime.strptime(DB_DATE_STR, "%Y-%m-%d")
except:
    DB_DATE = datetime(2024, 1, 1)

# Request settings
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; ElderFormCrawler/1.0)")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
DELAY_BETWEEN_REQUESTS = float(os.getenv("DELAY_BETWEEN_REQUESTS", "1.0"))

# Output settings
SAVE_HTML = os.getenv("SAVE_HTML", "false").lower() == "true"
SAVE_JSON = os.getenv("SAVE_JSON", "true").lower() == "true"
SAVE_CSV = os.getenv("SAVE_CSV", "true").lower() == "true"
OUTPUT_FORMAT = os.getenv("OUTPUT_FORMAT", "json")  # json, csv, or both
CSV_FILE = OUTPUT_DIR / "downloaded_files.csv"

# Notification settings (optional)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", None)  # For Discord/Slack notifications
EMAIL_NOTIFICATION = os.getenv("EMAIL_NOTIFICATION", "false").lower() == "true"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = OUTPUT_DIR / "crawler.log"
