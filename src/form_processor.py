#!/usr/bin/env python3
"""
Form Processor - Convert crawled files to structured forms

Features:
- OCR text extraction from PDF/DOC/DOCX
- AI-powered field extraction using OpenAI
- Vietnamese form structure detection
- Automatic form_id generation
- Metadata preservation
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from openai import OpenAI  # noqa: E402
from tenacity import retry, stop_after_attempt, wait_exponential  # noqa: E402

from src.ocr_validator import OCRValidator  # noqa: E402

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormProcessor:
    """Process crawled files into structured form definitions"""

    def __init__(self, output_dir: str = "forms/crawled_forms"):
        self.ocr = OCRValidator()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Get OpenAI settings from environment
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Initialize OpenAI client
        self.client: OpenAI | None = None
        if self.openai_api_key:
            try:
                self.client = OpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.warning(f"OpenAI initialization failed: {e}")
                self.client = None
        else:
            logger.warning("No OpenAI API key, AI features disabled")

    def _generate_form_id(self, title: str) -> str:
        """
        Generate form_id from Vietnamese title
        Examples:
        - "Đơn xin việc" → "don_xin_viec"
        - "Giấy ủy quyền" → "giay_uy_quyen"
        """
        # Remove diacritics and convert to lowercase
        replacements = {
            "đ": "d",
            "Đ": "d",
            "à": "a",
            "á": "a",
            "ả": "a",
            "ã": "a",
            "ạ": "a",
            "ă": "a",
            "ằ": "a",
            "ắ": "a",
            "ẳ": "a",
            "ẵ": "a",
            "ặ": "a",
            "â": "a",
            "ầ": "a",
            "ấ": "a",
            "ẩ": "a",
            "ẫ": "a",
            "ậ": "a",
            "è": "e",
            "é": "e",
            "ẻ": "e",
            "ẽ": "e",
            "ẹ": "e",
            "ê": "e",
            "ề": "e",
            "ế": "e",
            "ể": "e",
            "ễ": "e",
            "ệ": "e",
            "ì": "i",
            "í": "i",
            "ỉ": "i",
            "ĩ": "i",
            "ị": "i",
            "ò": "o",
            "ó": "o",
            "ỏ": "o",
            "õ": "o",
            "ọ": "o",
            "ô": "o",
            "ồ": "o",
            "ố": "o",
            "ổ": "o",
            "ỗ": "o",
            "ộ": "o",
            "ơ": "o",
            "ờ": "o",
            "ớ": "o",
            "ở": "o",
            "ỡ": "o",
            "ợ": "o",
            "ù": "u",
            "ú": "u",
            "ủ": "u",
            "ũ": "u",
            "ụ": "u",
            "ư": "u",
            "ừ": "u",
            "ứ": "u",
            "ử": "u",
            "ữ": "u",
            "ự": "u",
            "ỳ": "y",
            "ý": "y",
            "ỷ": "y",
            "ỹ": "y",
            "ỵ": "y",
        }

        normalized = title.lower()
        for viet, ascii_char in replacements.items():
            normalized = normalized.replace(viet, ascii_char)

        # Remove special characters, keep only alphanumeric and spaces
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)

        # Replace spaces with underscores
        form_id = "_".join(normalized.split())

        return form_id

    def _extract_aliases(self, title: str, text: str) -> list[str]:
        """
        Extract potential aliases from title and text
        """
        aliases = []

        # Add simplified title
        simplified = title.lower().strip()
        if simplified not in aliases:
            aliases.append(simplified)

        # Extract common Vietnamese form keywords
        keywords = [
            "mẫu",
            "đơn",
            "giấy",
            "tờ khai",
            "biểu mẫu",
            "phiếu",
            "bản khai",
            "giấy chứng nhận",
        ]

        for keyword in keywords:
            if keyword in title.lower():
                # Add keyword-based alias
                alias = title.lower().replace(keyword, "").strip()
                if alias and len(alias) > 3:
                    aliases.append(alias)

        # Limit to top 3 most relevant
        return aliases[:3]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _extract_fields_with_ai(self, text: str, title: str) -> list[dict[str, Any]]:
        """
        Use OpenAI to extract form fields from Vietnamese text

        Returns:
            List of field definitions matching form_samples.json schema
        """
        if not self.client:
            logger.warning("No OpenAI client, returning empty fields")
            return []

        prompt = f"""Bạn là chuyên gia phân tích biểu mẫu tiếng Việt.

Tiêu đề: {title}

Nội dung biểu mẫu:
{text[:3000]}  # Limit text to avoid token overflow

Nhiệm vụ: Phân tích văn bản và trích xuất các trường thông tin (fields) trong biểu mẫu.

Yêu cầu output JSON:
{{
  "fields": [
    {{
      "name": "field_name_in_english",
      "label": "Nhãn tiếng Việt",
      "type": "string|date|phone|email|address|multiline",
      "required": true/false,
      "example": "Ví dụ giá trị (nếu có)"
    }}
  ]
}}

Quy tắc:
1. `name`: Tên trường bằng tiếng Anh, snake_case (vd: full_name, id_number)
2. `label`: Giữ nguyên tiếng Việt từ biểu mẫu
3. `type`: Chọn đúng loại dữ liệu
   - "string": Văn bản thường
   - "date": Ngày tháng
   - "phone": Số điện thoại
   - "email": Email
   - "address": Địa chỉ
   - "multiline": Văn bản nhiều dòng
4. `required`: true nếu trường bắt buộc, false nếu tùy chọn
5. `example`: Ví dụ nếu có trong văn bản

Các trường phổ biến:
- Họ và tên (full_name)
- Ngày sinh (dob)
- Số CCCD/CMND (id_number)
- Địa chỉ (address)
- Số điện thoại (phone)
- Email (email)

CHỈ trả về JSON, không giải thích thêm."""

        try:
            response = self.client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Bạn là chuyên gia phân tích biểu mẫu tiếng Việt. Chỉ trả về JSON hợp lệ.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            content = response.choices[0].message.content
            if content is None:
                logger.warning("OpenAI returned empty response")
                return []

            content = content.strip()

            # Try to extract JSON from markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            fields = result.get("fields", [])

            logger.info(f"AI extracted {len(fields)} fields from '{title}'")
            return fields

        except Exception as e:
            logger.error(f"AI field extraction failed: {e}")
            return []

    def _create_basic_fields(self, text: str) -> list[dict[str, Any]]:
        """
        Fallback: Create basic fields if AI extraction fails
        Based on common Vietnamese form patterns
        """
        fields = []

        # Detect common field patterns using regex
        patterns = {
            "full_name": r"(?:họ\s+(?:và\s+)?tên|họ\s*tên|tên)",
            "dob": r"(?:ngày\s+sinh|sinh\s+ngày)",
            "id_number": r"(?:số\s+)?(?:cccd|cmnd|chứng\s+minh)",
            "address": r"(?:địa\s+chỉ|nơi\s+ở)",
            "phone": r"(?:số\s+)?(?:điện\s+thoại|liên\s+hệ)",
            "email": r"email|e-mail|thư\s+điện\s+tử",
        }

        text_lower = text.lower()

        for field_name, pattern in patterns.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                field_type = "string"
                if field_name == "dob":
                    field_type = "date"
                elif field_name == "phone":
                    field_type = "phone"
                elif field_name == "email":
                    field_type = "email"
                elif field_name == "address":
                    field_type = "address"

                # Map field_name to Vietnamese label
                labels = {
                    "full_name": "Họ và tên",
                    "dob": "Ngày sinh",
                    "id_number": "Số CCCD/CMND",
                    "address": "Địa chỉ",
                    "phone": "Số điện thoại",
                    "email": "Email",
                }

                fields.append(
                    {
                        "name": field_name,
                        "label": labels.get(field_name, field_name),
                        "type": field_type,
                        "required": True,
                    }
                )

        logger.info(f"Created {len(fields)} basic fields from pattern matching")
        return fields

    def process_file(self, file_path: Path, source_url: str = "") -> dict[str, Any] | None:
        """
        Process a single crawled file into structured form

        Args:
            file_path: Path to the file (.pdf, .doc, .docx, etc.)
            source_url: Original URL where file was downloaded

        Returns:
            Form definition dict or None if processing fails
        """
        logger.info(f"Processing: {file_path.name}")

        # Step 1: OCR validation
        ocr_result = self.ocr.validate_file(file_path)

        if not ocr_result["is_valid"]:
            logger.warning(f"OCR validation failed for {file_path.name}")
            return None

        text = ocr_result.get("text", "")
        if len(text) < 50:
            logger.warning(f"Insufficient text extracted from {file_path.name}")
            return None

        # Step 2: Extract title from filename or text
        title = self._extract_title(file_path.name, text)

        # Step 3: Generate form_id
        form_id = self._generate_form_id(title)

        # Step 4: Extract fields using AI
        fields = self._extract_fields_with_ai(text, title)

        # Fallback to basic field extraction if AI fails
        if not fields:
            logger.info("Using basic field extraction as fallback")
            fields = self._create_basic_fields(text)

        if not fields:
            logger.warning(f"No fields extracted from {file_path.name}")
            return None

        # Step 5: Generate aliases
        aliases = self._extract_aliases(title, text)

        # Step 6: Create form definition
        form_def = {
            "form_id": form_id,
            "title": title,
            "aliases": aliases,
            "source": "crawler",
            "metadata": {
                "source_file": file_path.name,
                "source_url": source_url,
                "processed_at": datetime.now().isoformat(),
                "ocr_confidence": ocr_result.get("confidence", 0.0),
                "ocr_method": ocr_result.get("method", "unknown"),
                "ocr_keywords": ocr_result.get("keywords_found", []),
            },
            "fields": fields,
        }

        logger.info(f"✓ Processed '{title}' with {len(fields)} fields")
        return form_def

    def _extract_title(self, filename: str, text: str) -> str:
        """
        Extract form title from filename or text

        Priority:
        1. Extract from text (first line or heading pattern)
        2. Clean filename
        """
        # Try to find title pattern in text
        lines = text.split("\n")
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                # Check if line contains form keywords
                keywords = ["đơn", "giấy", "mẫu", "tờ khai", "biểu mẫu", "phiếu"]
                if any(kw in line.lower() for kw in keywords):
                    return line

        # Fallback: Clean filename
        title = filename.replace(".pdf", "").replace(".doc", "").replace(".docx", "")
        title = title.replace("-", " ").replace("_", " ")
        title = " ".join(title.split())  # Normalize spaces

        # Capitalize first letter of each word
        return title.title()

    def process_directory(self, input_dir: str = "crawler_output") -> list[dict[str, Any]]:
        """
        Process all files in crawler output directory

        Args:
            input_dir: Directory containing crawled files

        Returns:
            List of processed form definitions
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            logger.error(f"Input directory not found: {input_dir}")
            return []

        # Load CSV to get source URLs
        csv_file = input_path / "downloaded_files.csv"
        source_urls = {}
        if csv_file.exists():
            import csv

            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    filename = row.get("Ten_file", "")
                    url = row.get("Link_file", "")
                    if filename and url:
                        source_urls[filename] = url

        # Process all files
        forms = []
        supported_exts = [".pdf", ".doc", ".docx", ".xls", ".xlsx"]

        for file_path in input_path.iterdir():
            if file_path.suffix.lower() in supported_exts:
                source_url = source_urls.get(file_path.name, "")
                form_def = self.process_file(file_path, source_url)

                if form_def:
                    forms.append(form_def)

                    # Save individual form
                    form_id = form_def["form_id"]
                    output_file = self.output_dir / f"{form_id}.json"
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(form_def, f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved: {output_file.name}")

        logger.info(f"Processed {len(forms)} forms from {input_dir}")
        return forms

    def save_index(self, forms: list[dict[str, Any]]) -> None:
        """
        Save forms index (all forms in one file)

        Args:
            forms: List of form definitions
        """
        index_file = self.output_dir / "_index.json"
        index = {
            "forms": forms,
            "count": len(forms),
            "generated_at": datetime.now().isoformat(),
        }

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved index: {index_file} ({len(forms)} forms)")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Process crawled forms into structured JSON")
    parser.add_argument("--input", "-i", default="crawler_output", help="Input directory (default: crawler_output)")
    parser.add_argument(
        "--output", "-o", default="forms/crawled_forms", help="Output directory (default: forms/crawled_forms)"
    )
    parser.add_argument("--file", "-f", help="Process single file instead of directory")

    args = parser.parse_args()

    processor = FormProcessor(output_dir=args.output)

    if args.file:
        # Process single file
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File not found: {args.file}")
            return

        form_def = processor.process_file(file_path)
        if form_def:
            print(json.dumps(form_def, ensure_ascii=False, indent=2))
        else:
            print("Processing failed")
    else:
        # Process directory
        forms = processor.process_directory(args.input)
        processor.save_index(forms)

        print(f"\n{'='*60}")
        print("Processing complete!")
        print(f"{'='*60}")
        print(f"Total forms: {len(forms)}")
        print(f"Output: {args.output}")
        print(f"Index: {args.output}/_index.json")


if __name__ == "__main__":
    main()
