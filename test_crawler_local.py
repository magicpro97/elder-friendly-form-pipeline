#!/usr/bin/env python
"""
Quick local test script for Vietnamese Form Crawler
Run this to test crawler before deploying to cloud

Usage:
    source .venv/bin/activate  # Activate virtual environment first
    python test_crawler_local.py
"""

import os
import sys

# Set up environment for testing
# Test với URL dễ hơn, không có anti-bot quá mạnh
os.environ["CRAWLER_TARGETS"] = (
    "https://luatsubaoho.com/phapluat/mau-don-dang-ky-bien-dong-dat-dai-co-huong-dan-cach-viet/"
)
os.environ["DB_DATE"] = "2020-01-01"  # Lower cutoff for testing
os.environ["SAVE_CSV"] = "true"
os.environ["SAVE_JSON"] = "true"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["DELAY_BETWEEN_REQUESTS"] = "2.0"  # Be respectful

# Import after setting env vars
from src.vietnamese_form_crawler import main

if __name__ == "__main__":
    print("=" * 60)
    print("VIETNAMESE FORM CRAWLER - LOCAL TEST")
    print("=" * 60)
    print("\nTest Configuration:")
    print(f"  Target: {os.environ['CRAWLER_TARGETS']}")
    print(f"  Date cutoff: {os.environ['DB_DATE']}")
    print("  Output dir: crawler_output/")
    print("\nStarting test crawl...")
    print("=" * 60 + "\n")

    try:
        main()

        print("\n" + "=" * 60)
        print("TEST COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nCheck results:")
        print("  - crawler_output/downloaded_files.csv")
        print("  - crawler_output/crawler.log")
        print("  - crawler_output/*.pdf, *.doc, *.xlsx")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
