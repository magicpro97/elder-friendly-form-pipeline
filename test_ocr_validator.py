#!/usr/bin/env python3
"""
Test OCR Validator
Quick test script for OCR validation of downloaded files
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.ocr_validator import validate_file

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def test_ocr_on_downloaded_files():
    """Test OCR validation on all downloaded files"""
    output_dir = Path("crawler_output")

    if not output_dir.exists():
        logger.error(f"Output directory not found: {output_dir}")
        return

    # Get all downloaded files
    file_extensions = [".pdf", ".doc", ".docx", ".jpg", ".png", ".xls", ".xlsx"]
    files = []
    for ext in file_extensions:
        files.extend(output_dir.glob(f"*{ext}"))

    if not files:
        logger.warning("No files found in crawler_output/")
        return

    logger.info(f"Found {len(files)} files to validate")
    print("\n" + "=" * 70)
    print("OCR VALIDATION RESULTS")
    print("=" * 70)

    valid_count = 0
    invalid_count = 0

    for file_path in files:
        logger.info(f"\nValidating: {file_path.name}")
        result = validate_file(file_path, verbose=False)

        is_valid = result.get("is_valid", False)
        confidence = result.get("confidence", 0)
        method = result.get("method", "unknown")
        text_length = result.get("text_length", 0)
        keywords = result.get("keywords_found", [])

        status = "✓ VALID" if is_valid else "✗ INVALID"

        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1

        print(f"\n{status} - {file_path.name}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Method: {method}")
        print(f"  Text length: {text_length} chars")
        print(f"  Keywords found: {', '.join(keywords[:5])}")

        if "error" in result:
            print(f"  Error: {result['error']}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files: {len(files)}")
    print(f"Valid: {valid_count} ({valid_count/len(files)*100:.1f}%)")
    print(f"Invalid: {invalid_count} ({invalid_count/len(files)*100:.1f}%)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_ocr_on_downloaded_files()
