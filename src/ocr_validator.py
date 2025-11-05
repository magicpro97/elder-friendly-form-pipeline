#!/usr/bin/env python3
"""
OCR Validator for Downloaded Forms
Validates that downloaded files actually contain form content using OCR

Features:
- OCR for images (JPG, PNG) using pytesseract
- PDF text extraction using PyPDF2 (fallback to OCR if scanned)
- MS Office documents (.doc, .docx) using python-docx
- Vietnamese keyword validation
- Confidence scoring
"""

import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import OCR libraries
try:
    import pytesseract
    from PIL import Image

    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("pytesseract or Pillow not installed, image OCR disabled")

try:
    from PyPDF2 import PdfReader

    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    logger.warning("PyPDF2 not installed, PDF text extraction disabled")

try:
    from docx import Document

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx not installed, DOCX parsing disabled")

try:
    import textract

    HAS_TEXTRACT = True
except ImportError:
    HAS_TEXTRACT = False
    logger.info("textract not installed, .doc parsing limited")


class OCRValidator:
    """Validates downloaded files using OCR and text extraction"""

    # Vietnamese form keywords (similar to crawler keywords)
    FORM_KEYWORDS = [
        "mẫu",
        "đơn",
        "biểu mẫu",
        "tờ khai",
        "phiếu",
        "giấy",
        "bản khai",
        "hồ sơ",
        "văn bản",
        "số",
        "ngày",
        "tháng",
        "năm",  # Date fields
        "họ tên",
        "địa chỉ",
        "cmnd",
        "cccd",  # Personal info fields
        "chức vụ",
        "chữ ký",
        "xác nhận",  # Official fields
    ]

    # Minimum text length to consider valid
    MIN_TEXT_LENGTH = 50

    # Minimum keyword matches for validation
    MIN_KEYWORD_MATCHES = 2

    def __init__(self, verbose: bool = False):
        """
        Initialize OCR validator

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        if verbose:
            logger.setLevel(logging.DEBUG)

    def validate_file(self, file_path: Path) -> dict[str, Any]:
        """
        Validate a downloaded file using OCR/text extraction

        Args:
            file_path: Path to the file to validate

        Returns:
            Dictionary with validation results:
            {
                'is_valid': bool,
                'confidence': float (0-1),
                'text_length': int,
                'keyword_matches': int,
                'keywords_found': list,
                'method': str (ocr, pdf, docx, etc.),
                'error': str (if failed)
            }
        """
        if not file_path.exists():
            return {"is_valid": False, "confidence": 0.0, "error": "File not found"}

        # Determine file type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        suffix = file_path.suffix.lower()

        logger.debug(f"Validating {file_path.name} (type: {mime_type}, suffix: {suffix})")

        # Extract text based on file type
        text, method = self._extract_text(file_path, suffix, mime_type)

        if not text:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "text_length": 0,
                "keyword_matches": 0,
                "method": method,
                "error": "No text extracted",
            }

        # Analyze extracted text
        result = self._analyze_text(text, method)
        # Add extracted text to result for downstream processing
        result["text"] = text
        return result

    def _extract_text(self, file_path: Path, suffix: str, mime_type: str | None) -> tuple[str, str]:
        """
        Extract text from file based on type

        Returns:
            (extracted_text, method_used)
        """
        # Try PDF extraction
        if suffix == ".pdf" or (mime_type and "pdf" in mime_type):
            return self._extract_from_pdf(file_path)

        # Try DOCX extraction
        if suffix == ".docx":
            return self._extract_from_docx(file_path)

        # Try DOC extraction (requires textract or antiword)
        if suffix == ".doc":
            return self._extract_from_doc(file_path)

        # Try image OCR
        if suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
            return self._extract_from_image(file_path)

        # Try Excel (basic check)
        if suffix in [".xls", ".xlsx"]:
            return self._extract_from_excel(file_path)

        logger.warning(f"Unsupported file type: {suffix}")
        return "", "unsupported"

    def _extract_from_pdf(self, file_path: Path) -> tuple[str, str]:
        """Extract text from PDF"""
        if not HAS_PDF:
            return "", "pdf_unavailable"

        try:
            reader = PdfReader(str(file_path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"

            if len(text.strip()) < self.MIN_TEXT_LENGTH:
                # PDF might be scanned image, try OCR
                logger.debug(f"PDF has little text ({len(text)} chars), trying OCR")
                return self._ocr_pdf(file_path)

            return text, "pdf"

        except Exception as e:
            logger.error(f"PDF extraction failed for {file_path.name}: {e}")
            # Fallback to OCR
            return self._ocr_pdf(file_path)

    def _ocr_pdf(self, file_path: Path) -> tuple[str, str]:
        """OCR a PDF file (scanned image PDF)"""
        if not HAS_TESSERACT:
            return "", "pdf_ocr_unavailable"

        try:
            # This requires pdf2image library
            from pdf2image import convert_from_path

            images = convert_from_path(str(file_path), first_page=1, last_page=3)  # First 3 pages
            text = ""

            for i, image in enumerate(images):
                logger.debug(f"OCR page {i+1} of PDF")
                page_text = pytesseract.image_to_string(image, lang="vie")
                text += page_text + "\n"

            return text, "pdf_ocr"

        except ImportError:
            logger.warning("pdf2image not installed, cannot OCR PDF")
            return "", "pdf2image_unavailable"
        except Exception as e:
            logger.error(f"PDF OCR failed for {file_path.name}: {e}")
            return "", "pdf_ocr_error"

    def _extract_from_docx(self, file_path: Path) -> tuple[str, str]:
        """Extract text from DOCX"""
        if not HAS_DOCX:
            return "", "docx_unavailable"

        try:
            doc = Document(str(file_path))
            text = "\n".join([para.text for para in doc.paragraphs])
            return text, "docx"

        except Exception as e:
            logger.error(f"DOCX extraction failed for {file_path.name}: {e}")
            return "", "docx_error"

    def _extract_from_doc(self, file_path: Path) -> tuple[str, str]:
        """Extract text from DOC (old Word format)"""
        if HAS_TEXTRACT:
            try:
                text = textract.process(str(file_path)).decode("utf-8")
                return text, "doc_textract"
            except Exception as e:
                logger.error(f"textract failed for {file_path.name}: {e}")

        # Fallback: .doc files are hard to parse, mark as valid if file exists
        logger.warning(f"Cannot extract text from .doc file {file_path.name}, assuming valid")
        return "doc file (assumed valid)", "doc_assumed"

    def _extract_from_image(self, file_path: Path) -> tuple[str, str]:
        """Extract text from image using OCR"""
        if not HAS_TESSERACT:
            return "", "tesseract_unavailable"

        try:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang="vie")
            return text, "image_ocr"

        except Exception as e:
            logger.error(f"Image OCR failed for {file_path.name}: {e}")
            return "", "image_ocr_error"

    def _extract_from_excel(self, file_path: Path) -> tuple[str, str]:
        """Basic check for Excel files"""
        try:
            import openpyxl

            wb = openpyxl.load_workbook(file_path, data_only=True)
            text = ""
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(max_row=20, max_col=10, values_only=True):
                    text += " ".join([str(cell) for cell in row if cell]) + "\n"
            return text, "excel"

        except ImportError:
            logger.warning("openpyxl not installed, cannot read Excel")
            return "excel file (assumed valid)", "excel_assumed"
        except Exception as e:
            logger.error(f"Excel extraction failed for {file_path.name}: {e}")
            return "", "excel_error"

    def _analyze_text(self, text: str, method: str) -> dict[str, Any]:
        """
        Analyze extracted text for form content

        Args:
            text: Extracted text
            method: Extraction method used

        Returns:
            Validation result dictionary
        """
        text_lower = text.lower()
        text_length = len(text.strip())

        # Find keyword matches
        keywords_found = []
        for keyword in self.FORM_KEYWORDS:
            if keyword.lower() in text_lower:
                keywords_found.append(keyword)

        keyword_matches = len(keywords_found)

        # Calculate confidence score
        # Based on: text length, keyword matches, method reliability
        confidence = 0.0

        if text_length >= self.MIN_TEXT_LENGTH:
            confidence += 0.3

        # Keyword score (max 0.5)
        keyword_score = min(keyword_matches / 5.0, 0.5)
        confidence += keyword_score

        # Method reliability bonus
        method_bonus = {
            "pdf": 0.2,
            "docx": 0.2,
            "doc_textract": 0.15,
            "image_ocr": 0.1,
            "pdf_ocr": 0.1,
            "excel": 0.15,
            "doc_assumed": 0.1,
            "excel_assumed": 0.1,
        }.get(method, 0.0)
        confidence += method_bonus

        confidence = min(confidence, 1.0)

        # Determine if valid
        is_valid = (
            text_length >= self.MIN_TEXT_LENGTH and keyword_matches >= self.MIN_KEYWORD_MATCHES
        ) or method.endswith("_assumed")  # Trust assumed files

        logger.debug(
            f"Analysis: {text_length} chars, {keyword_matches} keywords, "
            f"confidence {confidence:.2f}, valid: {is_valid}"
        )

        return {
            "is_valid": is_valid,
            "confidence": confidence,
            "text_length": text_length,
            "keyword_matches": keyword_matches,
            "keywords_found": keywords_found[:5],  # Top 5
            "method": method,
        }


def validate_file(file_path: Path, verbose: bool = False) -> dict[str, Any]:
    """
    Convenience function to validate a single file

    Args:
        file_path: Path to file
        verbose: Enable verbose logging

    Returns:
        Validation result dictionary
    """
    validator = OCRValidator(verbose=verbose)
    return validator.validate_file(file_path)


if __name__ == "__main__":
    # Test OCR validator
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    if len(sys.argv) < 2:
        sys.exit(1)

    file_path = Path(sys.argv[1])
    result = validate_file(file_path, verbose=True)

    for _key, _value in result.items():
        pass
