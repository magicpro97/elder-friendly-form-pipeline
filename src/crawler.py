#!/usr/bin/env python3
"""
Daily Crawler for Elder-Friendly Form Pipeline

This crawler can be configured for multiple purposes:
1. Scrape government form websites for updates
2. Monitor form-related resources
3. Collect data for analysis
4. Health check external services

Configure targets via CRAWLER_TARGETS environment variable.
Example: CRAWLER_TARGETS="https://example.com,https://another.com"
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Add parent directory to path for settings import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.settings import (
    CRAWLER_TARGETS,
    DELAY_BETWEEN_REQUESTS,
    LOG_FILE,
    LOG_LEVEL,
    MAX_RETRIES,
    OUTPUT_DIR,
    REQUEST_TIMEOUT,
    SAVE_HTML,
    SAVE_JSON,
    USER_AGENT,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class Crawler:
    """Generic web crawler with retry logic and error handling"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.results: List[Dict[str, Any]] = []

    def fetch_page(self, url: str, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
        """Fetch a page with retry logic"""
        for attempt in range(retries):
            try:
                logger.info(f"Fetching {url} (attempt {attempt + 1}/{retries})")
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logger.error(f"All retries failed for {url}")
                    return None
        return None

    def parse_page(self, url: str, html: str) -> Dict[str, Any]:
        """
        Parse HTML page and extract relevant data

        Override this method to customize extraction logic for specific sites
        """
        soup = BeautifulSoup(html, "lxml")

        # Generic extraction - customize based on target site structure
        data = {
            "url": url,
            "title": soup.title.string if soup.title else "No title",
            "crawled_at": datetime.now().isoformat(),
            "status": "success",
        }

        # Example: Extract all links
        links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            absolute_url = urljoin(url, href)
            links.append({"text": link.get_text(strip=True), "href": absolute_url})
        data["links"] = links[:20]  # Limit to first 20 links

        # Example: Extract all forms (relevant for elder-friendly form app)
        forms = []
        for form in soup.find_all("form"):
            form_data = {"action": form.get("action", ""), "method": form.get("method", "get").upper(), "inputs": []}
            for input_tag in form.find_all("input"):
                form_data["inputs"].append(
                    {
                        "name": input_tag.get("name", ""),
                        "type": input_tag.get("type", "text"),
                        "required": input_tag.has_attr("required"),
                    }
                )
            forms.append(form_data)
        data["forms"] = forms

        # Example: Extract meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            data["description"] = meta_desc.get("content", "")

        return data

    def crawl_target(self, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a single target URL"""
        logger.info(f"Starting crawl for: {url}")

        response = self.fetch_page(url)
        if not response:
            return {
                "url": url,
                "status": "failed",
                "error": "Failed to fetch page",
                "crawled_at": datetime.now().isoformat(),
            }

        # Save HTML if configured
        if SAVE_HTML:
            html_path = OUTPUT_DIR / f"{urlparse(url).netloc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            html_path.write_text(response.text, encoding="utf-8")
            logger.info(f"Saved HTML to {html_path}")

        # Parse the page
        data = self.parse_page(url, response.text)
        self.results.append(data)

        return data

    def crawl_all(self) -> List[Dict[str, Any]]:
        """Crawl all configured targets"""
        logger.info(f"Starting crawl for {len(CRAWLER_TARGETS)} targets")

        for i, target in enumerate(CRAWLER_TARGETS):
            target = target.strip()
            if not target:
                continue

            self.crawl_target(target)

            # Delay between requests to be respectful
            if i < len(CRAWLER_TARGETS) - 1:
                logger.debug(f"Waiting {DELAY_BETWEEN_REQUESTS}s before next request")
                time.sleep(DELAY_BETWEEN_REQUESTS)

        return self.results

    def save_results(self):
        """Save crawl results to file"""
        if not self.results:
            logger.warning("No results to save")
            return

        if SAVE_JSON:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = OUTPUT_DIR / f"crawl_results_{timestamp}.json"

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "crawled_at": datetime.now().isoformat(),
                        "total_targets": len(CRAWLER_TARGETS),
                        "successful": len([r for r in self.results if r.get("status") == "success"]),
                        "failed": len([r for r in self.results if r.get("status") == "failed"]),
                        "results": self.results,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            logger.info(f"Saved results to {json_path}")

    def print_summary(self):
        """Print crawl summary"""
        successful = len([r for r in self.results if r.get("status") == "success"])
        failed = len([r for r in self.results if r.get("status") == "failed"])

        print("\n" + "=" * 50)
        print("CRAWL SUMMARY")
        print("=" * 50)
        print(f"Total targets: {len(CRAWLER_TARGETS)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Output directory: {OUTPUT_DIR}")
        print("=" * 50 + "\n")


def main():
    """Main crawler execution"""
    logger.info("=" * 50)
    logger.info("Elder-Friendly Form Pipeline - Daily Crawler")
    logger.info("=" * 50)

    # Validate configuration
    if not CRAWLER_TARGETS or CRAWLER_TARGETS == ["https://example.com/forms"]:
        logger.warning("No custom targets configured. Using default example.com")
        logger.warning("Set CRAWLER_TARGETS environment variable to customize")

    # Run crawler
    crawler = Crawler()

    try:
        crawler.crawl_all()
        crawler.save_results()
        crawler.print_summary()

        # Exit with error code if all crawls failed
        successful = len([r for r in crawler.results if r.get("status") == "success"])
        if successful == 0 and len(crawler.results) > 0:
            logger.error("All crawl attempts failed")
            sys.exit(1)

        logger.info("Crawler completed successfully")

    except Exception as e:
        logger.error(f"Crawler failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
