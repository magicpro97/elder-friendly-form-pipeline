#!/usr/bin/env python3
"""
Vietnamese Form Crawler
Specialized crawler for scraping Vietnamese government forms, legal documents, and templates

Features:
- 2-level crawling (main page → sub-pages → files)
- Vietnamese date parsing (dd/mm/yyyy, yyyy-mm-dd)
- Keyword-based filtering (mẫu, đơn, biểu mẫu, etc.)
- Date-based filtering (only crawl recent forms)
- CSV export for downloaded files
- Cloudscraper support for anti-bot sites
"""

import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from src.settings import (  # noqa: E402
    ALL_KEYWORDS,
    CRAWLER_TARGETS,
    CRITICAL_KEYWORDS,
    CSV_FILE,
    DB_DATE,
    LOG_FILE,
    LOG_LEVEL,
    OUTPUT_DIR,
    REQUEST_TIMEOUT,
    SAVE_CSV,
    USER_AGENT,
)

# Import OCR validator
try:
    from src.ocr_validator import OCRValidator  # noqa: E402

    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logging.warning("OCR validator not available, file validation disabled")

# Try to import cloudscraper for anti-bot protection
try:
    import cloudscraper

    USE_CLOUDSCRAPER = True
except ImportError:
    USE_CLOUDSCRAPER = False

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class VietnameseFormCrawler:
    """
    Specialized crawler for Vietnamese government forms and legal documents
    """

    # Vietnamese date patterns
    DATE_PATTERNS = [
        r"(Thứ Hai|Thứ Ba|Thứ Tư|Thứ Năm|Thứ Sáu|Thứ Bảy|Chủ Nhật)[,]\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{4}-\d{1,2}-\d{1,2})",
    ]

    # Supported file extensions (documents only, no images)
    FILE_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx"]

    def __init__(self, enable_ocr: bool = True):
        """
        Initialize crawler with session and results tracking

        Args:
            enable_ocr: Enable OCR validation of downloaded files
        """
        if USE_CLOUDSCRAPER:
            self.session = cloudscraper.create_scraper()
            logger.info("Using cloudscraper for anti-bot protection")
        else:
            self.session = requests.Session()
            logger.warning("Cloudscraper not available, using standard requests")

        self.session.headers.update({"User-Agent": USER_AGENT})
        self.results: list[dict[str, Any]] = []
        self.total_downloaded = 0
        self.total_validated = 0
        self.total_failed_validation = 0

        # Initialize OCR validator
        self.enable_ocr = enable_ocr and HAS_OCR
        if self.enable_ocr:
            self.ocr_validator = OCRValidator(verbose=False)
            logger.info("OCR validation enabled")
        else:
            self.ocr_validator = None
            if enable_ocr and not HAS_OCR:
                logger.warning("OCR requested but dependencies not available")

        # Initialize CSV file
        if SAVE_CSV:
            self._init_csv()

    def _init_csv(self):
        """Initialize CSV file with headers"""
        if not CSV_FILE.exists():
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = ["Tieu_de_trang", "Link_file", "Ten_file", "Dang_tep", "Ngay_dang"]
                if self.enable_ocr:
                    headers.extend(["OCR_Valid", "OCR_Confidence", "OCR_Keywords", "OCR_Method"])
                writer.writerow(headers)
            logger.info(f"Initialized CSV file: {CSV_FILE}")

    def _save_csv_row(
        self,
        page_title: str,
        file_url: str,
        file_name: str,
        file_extension: str,
        page_date: datetime | None,
        validation_result: dict[str, Any] | None = None,
    ):
        """Save downloaded file info to CSV"""
        if not SAVE_CSV:
            return

        date_str = page_date.strftime("%Y-%m-%d") if page_date else ""

        row = [page_title, file_url, file_name, file_extension, date_str]

        # Add validation results if OCR is enabled
        if self.enable_ocr and validation_result:
            row.extend(
                [
                    "Yes" if validation_result.get("is_valid") else "No",
                    f"{validation_result.get('confidence', 0):.2f}",
                    ", ".join(validation_result.get("keywords_found", [])[:3]),  # Top 3 keywords
                    validation_result.get("method", "unknown"),
                ]
            )
        elif self.enable_ocr:
            row.extend(["No", "0.00", "", "not_validated"])

        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def _parse_date_str(self, date_str: str) -> datetime | None:
        """Parse Vietnamese date string to datetime object"""
        date_str = date_str.strip()

        # Remove day of week prefix
        date_str = re.sub(
            r"(Thứ Hai|Thứ Ba|Thứ Tư|Thứ Năm|Thứ Sáu|Thứ Bảy|Chủ Nhật)[,]\s*", "", date_str, flags=re.IGNORECASE
        ).strip()

        try:
            if "/" in date_str:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
            elif "-" in date_str:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                return None

            # Only accept dates from year 2000 onwards
            if dt.year >= 2000:
                return dt
            else:
                return None
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
            return None

    def extract_date(self, html_text: str) -> datetime | None:
        """Extract the most recent date from HTML text"""
        if not html_text:
            return None

        valid_dates = []

        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, html_text, flags=re.IGNORECASE)
            for match in matches:
                # Extract date string from match
                if isinstance(match, tuple):
                    date_str = match[-1]
                else:
                    date_str = match

                dt = self._parse_date_str(date_str)
                if dt:
                    valid_dates.append(dt)

        # Return the most recent date found
        if valid_dates:
            return max(valid_dates)

        return None

    def download_file(self, url: str, page_title: str, page_date: datetime | None) -> tuple[bool, str | None]:
        """Download file from URL, validate with OCR, and save to disk"""
        # Extract filename from URL
        url_base = url.split("?")[0]
        filename = url_base.split("/")[-1]

        # Clean filename
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)

        # Check file extension
        file_ext = next((ext for ext in self.FILE_EXTENSIONS if filename.lower().endswith(ext)), None)

        if not file_ext or not filename:
            logger.debug(f"Invalid filename or extension: {filename}")
            return False, None

        try:
            logger.info(f"Downloading: {filename}")
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            # Save file
            file_path = OUTPUT_DIR / filename
            with open(file_path, "wb") as f:
                f.write(response.content)

            logger.info(f"✓ Downloaded successfully: {filename}")

            # Validate file with OCR if enabled
            validation_result = None
            if self.enable_ocr and self.ocr_validator:
                logger.debug(f"Validating {filename} with OCR...")
                validation_result = self.ocr_validator.validate_file(file_path)

                if validation_result.get("is_valid"):
                    self.total_validated += 1
                    logger.info(
                        f"✓ Validation passed: {filename} "
                        f"(confidence: {validation_result.get('confidence', 0):.2f}, "
                        f"method: {validation_result.get('method')})"
                    )
                else:
                    self.total_failed_validation += 1
                    logger.warning(
                        f"✗ Validation failed: {filename} - {validation_result.get('error', 'unknown error')}"
                    )
                    # Optionally delete invalid files
                    # file_path.unlink()
                    # return False, None

            # Save to CSV with validation results
            self._save_csv_row(page_title, url, filename, file_ext, page_date, validation_result)

            return True, filename

        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False, None

    def extract_form_links(self, url: str) -> tuple[list[str], datetime | None, str]:
        """
        Extract form-related links from a page

        Returns:
            - List of links (both file links and sub-page links)
            - Page date (if found)
            - Page title
        """
        logger.info(f"Scanning page: {url}")

        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Cannot open page {url}: {e}")
            return [], None, "No Title"

        soup = BeautifulSoup(response.text, "lxml")

        # Extract page title
        page_title = soup.find("title")
        page_title = page_title.get_text(strip=True) if page_title else "No Title"

        # Extract date
        page_date = self.extract_date(response.text)
        if not page_date:
            logger.warning(f"No date found on page: {url}")
            return [], None, page_title

        logger.info(f"📅 Page date: {page_date.strftime('%Y-%m-%d')}")

        # Extract links
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]

            # Skip non-http links
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            # Convert to absolute URL
            href = urljoin(url, href)

            # Get link text
            text = a.get_text(strip=True).lower()

            # Check if it's a file link
            is_file_link = any(href.lower().endswith(ext) for ext in self.FILE_EXTENSIONS)

            # Check for critical keywords
            has_critical_keyword = any(k in text or k in href.lower() for k in CRITICAL_KEYWORDS)

            # Accept link if:
            # 1. File link with critical keywords (ensure it's a form)
            if is_file_link and has_critical_keyword:
                links.append(href)
                continue

            # 2. Not a file link but has keywords (sub-page to crawl)
            if not is_file_link and any(k in text or k in href.lower() for k in ALL_KEYWORDS):
                links.append(href)

        return list(set(links)), page_date, page_title

    def crawl_all(self) -> list[dict[str, Any]]:
        """Crawl all configured targets"""
        logger.info("=" * 50)
        logger.info("Vietnamese Form Crawler - Starting")
        logger.info(f"Targets: {len(CRAWLER_TARGETS)}")
        logger.info(f"Date cutoff: {DB_DATE.strftime('%Y-%m-%d')}")
        logger.info("=" * 50)

        for base_url in CRAWLER_TARGETS:
            base_url = base_url.strip()
            if not base_url:
                continue

            logger.info(f"\n🌐 Crawling: {base_url}")

            # Level 1: Scan main page
            level1_links, date1, title1 = self.extract_form_links(base_url)

            if not date1 or date1 <= DB_DATE:
                logger.warning(f"⛔ Page too old or no date ({date1}) - skipping")
                continue

            # Process Level 1 links
            for link in level1_links:
                # Download files directly at Level 1
                if any(link.lower().endswith(ext) for ext in self.FILE_EXTENSIONS):
                    success, filename = self.download_file(link, title1, date1)
                    if success:
                        self.total_downloaded += 1
                    continue

                # Crawl Level 2 (sub-pages)
                try:
                    # Only crawl same domain
                    if urlparse(link).netloc != urlparse(base_url).netloc:
                        logger.debug(f"Skipping external link: {link}")
                        continue

                    sub_links, date2, title2 = self.extract_form_links(link)

                    if not date2 or date2 <= DB_DATE:
                        logger.warning(f"⛔ Sub-page too old ({date2}) - skipping: {link}")
                        continue

                    # Download files from Level 2
                    for sub in sub_links:
                        if any(sub.lower().endswith(ext) for ext in self.FILE_EXTENSIONS):
                            success, filename = self.download_file(sub, title2, date2)
                            if success:
                                self.total_downloaded += 1

                except Exception as e:
                    logger.error(f"Error crawling sub-page {link}: {e}")
                    continue

        return self.results

    def print_summary(self):
        """Print crawl summary"""
        print("\n" + "=" * 50)
        print("VIETNAMESE FORM CRAWLER - SUMMARY")
        print("=" * 50)
        print(f"Total targets: {len(CRAWLER_TARGETS)}")
        print(f"Files downloaded: {self.total_downloaded}")

        if self.enable_ocr:
            print(f"Files validated (OCR): {self.total_validated}")
            print(f"Files failed validation: {self.total_failed_validation}")
            validation_rate = (self.total_validated / self.total_downloaded * 100) if self.total_downloaded > 0 else 0
            print(f"Validation rate: {validation_rate:.1f}%")

        print(f"Output directory: {OUTPUT_DIR}")
        if SAVE_CSV:
            print(f"CSV file: {CSV_FILE}")
        print("=" * 50 + "\n")


def main():
    """Main crawler execution"""
    crawler = VietnameseFormCrawler()

    try:
        crawler.crawl_all()
        crawler.print_summary()

        if crawler.total_downloaded == 0:
            logger.warning("No files downloaded")
            sys.exit(1)

        logger.info("Crawler completed successfully")

    except Exception as e:
        logger.error(f"Crawler failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
