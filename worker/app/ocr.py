import io
import os
import re
import zipfile
from typing import Any, Dict

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

# OpenAI for generating form titles
try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def _detect_file_type(file_bytes: bytes) -> str:
    # Very lightweight magic-bytes based detection
    if file_bytes.startswith(b"%PDF"):
        return "pdf"
    if file_bytes.startswith(b"PK"):
        # Likely DOCX (zip). Could be other OOXML; we will confirm below when extracting
        return "docx_or_zip"
    if file_bytes.startswith(b"\xD0\xCF\x11\xE0"):
        # Old MS OLE Compound Document (DOC, XLS, PPT)
        return "doc_ole"
    # Try image open
    try:
        Image.open(io.BytesIO(file_bytes))
        return "image"
    except Exception:
        return "unknown"


def _get_ocr_langs() -> str:
    return os.getenv("OCR_LANGS", "vie+eng")


def _extract_text_from_pdf_first_page(file_bytes: bytes) -> str:
    try:
        images = convert_from_bytes(file_bytes, fmt="png", first_page=1, last_page=1)
        if images:
            return pytesseract.image_to_string(images[0], lang=_get_ocr_langs())
    except Exception:
        pass
    # Fallback attempt as image
    try:
        return pytesseract.image_to_string(
            Image.open(io.BytesIO(file_bytes)), lang=_get_ocr_langs()
        )
    except Exception:
        return ""


def _extract_text_from_image(file_bytes: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img, lang=_get_ocr_langs())
    except Exception:
        return ""


def _extract_text_from_docx(file_bytes: bytes) -> str:
    # Parse OOXML without external deps: read word/document.xml and strip tags
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            # Confirm it's a Word document by looking for word/document.xml
            if "word/document.xml" not in zf.namelist():
                return ""
            xml_bytes = zf.read("word/document.xml")
            xml_text = xml_bytes.decode("utf-8", errors="ignore")
            # Replace runs/paragraphs with spaces/newlines for readability
            # Remove XML tags
            # Keep simple: replace paragraph boundaries with newlines
            xml_text = re.sub(r"</w:p>", "\n", xml_text)
            # Strip remaining tags
            text = re.sub(r"<[^>]+>", "", xml_text)
            # Collapse whitespace
            text = re.sub(r"\s+", " ", text)
            return text.strip()
    except Exception:
        return ""


def _extract_text_from_doc_ole_best_effort(file_bytes: bytes) -> str:
    # Best-effort for legacy .doc without external tools: extract readable ASCII/UTF-8 sequences
    try:
        # Decode as latin-1 to preserve bytes then filter printable ranges
        data = file_bytes
        # Find sequences of printable characters of length >= 4
        candidates = re.findall(rb"[\x20-\x7E\t\r\n]{4,}", data)
        text = b" ".join(candidates).decode("utf-8", errors="ignore")
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        return ""


def ocr_extract_fields(file_bytes: bytes, key_hint: str) -> Dict[str, Any]:
    # Multi-format text extraction with OCR fallbacks
    file_type = _detect_file_type(file_bytes)

    text = ""
    pages = 1
    if file_type == "pdf":
        # Try first page OCR, also count pages if possible
        try:
            all_images = convert_from_bytes(file_bytes, fmt="png")
            pages = max(1, len(all_images))
            if all_images:
                text = pytesseract.image_to_string(all_images[0], lang=_get_ocr_langs())
            else:
                text = ""
        except Exception:
            text = _extract_text_from_pdf_first_page(file_bytes)
            pages = 1
    elif file_type == "image":
        text = _extract_text_from_image(file_bytes)
        pages = 1
    elif file_type == "docx_or_zip":
        text = _extract_text_from_docx(file_bytes)
        pages = 1
    elif file_type == "doc_ole":
        text = _extract_text_from_doc_ole_best_effort(file_bytes)
        pages = 1
    else:
        # Unknown: try PDF first-page logic then image OCR
        text = _extract_text_from_pdf_first_page(file_bytes)
        if not text:
            text = _extract_text_from_image(file_bytes)

    def _slugify(label: str) -> str:
        s = label.lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s or "field"

    def _infer_fields_from_text(t: str):
        t_lower = (t or "").lower()
        candidates = []
        compound_fields = []  # For grouped fields like CCCD + issue date + place

        # CCCD/CMND compound pattern detection
        # Look for patterns like: "CCCD số: ___ cấp ngày ___ tại ___"
        cccd_patterns = [
            (
                r"(cccd|cmnd|căn cước|can cuoc).*?(số|so).*?"
                r"(cấp ngày|ngày cấp|cap ngay|ngay cap).*?(tại|nơi cấp|tai|noi cap)"
            ),
            r"(cccd|cmnd).*?(cấp ngày|cap ngay).*?(tại|tai)",
        ]

        has_cccd_compound = False
        for pattern in cccd_patterns:
            if re.search(pattern, t_lower):
                has_cccd_compound = True
                compound_fields.append(
                    {
                        "label": "CCCD/CMND",
                        "type": "compound",
                        "subfields": [
                            {
                                "id": "so",
                                "label": "Số",
                                "type": "text",
                                "prompt": "số thẻ",
                            },
                            {
                                "id": "cap_ngay",
                                "label": "Cấp ngày",
                                "type": "date",
                                "prompt": "ngày cấp",
                            },
                            {
                                "id": "cap_tai",
                                "label": "Cấp tại",
                                "type": "text",
                                "prompt": "nơi cấp",
                            },
                        ],
                    }
                )
                break

        # Passport compound pattern
        passport_patterns = [
            r"(passport|hộ chiếu|ho chieu).*?(số|so).*?(cấp ngày|cap ngay).*?(tại|nơi cấp|tai|noi cap)",
        ]

        has_passport_compound = False
        for pattern in passport_patterns:
            if re.search(pattern, t_lower):
                has_passport_compound = True
                compound_fields.append(
                    {
                        "label": "Passport/Hộ chiếu",
                        "type": "compound",
                        "subfields": [
                            {
                                "id": "so",
                                "label": "Số",
                                "type": "text",
                                "prompt": "số hộ chiếu",
                            },
                            {
                                "id": "cap_ngay",
                                "label": "Cấp ngày",
                                "type": "date",
                                "prompt": "ngày cấp",
                            },
                            {
                                "id": "cap_tai",
                                "label": "Cấp tại",
                                "type": "text",
                                "prompt": "nơi cấp",
                            },
                        ],
                    }
                )
                break

        # Address compound pattern (đường, phường, quận, thành phố)
        address_patterns = [
            r"(địa chỉ|dia chi|address).*?(đường|duong|street).*?(phường|phuong|ward).*?(quận|quan|district)",
            r"(địa chỉ|dia chi).*?(số nhà|so nha).*?(phường|phuong).*?(quận|quan)",
        ]

        has_address_compound = False
        for pattern in address_patterns:
            if re.search(pattern, t_lower):
                has_address_compound = True
                compound_fields.append(
                    {
                        "label": "Địa chỉ đầy đủ",
                        "type": "compound",
                        "subfields": [
                            {
                                "id": "so_nha",
                                "label": "Số nhà/Đường",
                                "type": "text",
                                "prompt": "số nhà và tên đường",
                            },
                            {
                                "id": "phuong",
                                "label": "Phường/Xã",
                                "type": "text",
                                "prompt": "phường hoặc xã",
                            },
                            {
                                "id": "quan",
                                "label": "Quận/Huyện",
                                "type": "text",
                                "prompt": "quận hoặc huyện",
                            },
                            {
                                "id": "thanh_pho",
                                "label": "Thành phố/Tỉnh",
                                "type": "text",
                                "prompt": "thành phố hoặc tỉnh",
                            },
                        ],
                    }
                )
                break

        # Simple keyword presence checks (English + Vietnamese)
        # Skip if already detected in compound fields
        if any(
            k in t_lower
            for k in [
                "full name",
                "applicant name",
                "name:",
                "name ",
                "họ và tên",
                "ho va ten",
                "họ tên",
                "ho ten",
            ]
        ):
            candidates.append({"label": "Full name", "type": "text"})
        if any(k in t_lower for k in ["email", "e-mail"]):
            candidates.append({"label": "Email", "type": "email"})
        if any(
            k in t_lower
            for k in [
                "phone",
                "telephone",
                "mobile",
                "số điện thoại",
                "so dien thoai",
                "điện thoại",
                "dien thoai",
            ]
        ):
            candidates.append({"label": "Phone", "type": "tel"})
        if any(
            k in t_lower
            for k in [
                "date of birth",
                "dob",
                "birth date",
                "ngày sinh",
                "ngay sinh",
                "sinh nhật",
                "sinh nhat",
            ]
        ):
            candidates.append({"label": "Date of birth", "type": "date"})
        elif (
            any(k in t_lower for k in ["date:", "date ", "ngày:", "ngay:"])
            and not has_cccd_compound
            and not has_passport_compound
        ):
            # Only add standalone date if not part of CCCD/passport compound
            candidates.append({"label": "Date", "type": "date"})

        # Only add standalone ID number if no compound CCCD/passport detected
        if not has_cccd_compound and not has_passport_compound:
            if any(
                k in t_lower
                for k in [
                    "id number",
                    "id no",
                    "passport",
                    "national id",
                    "cmnd",
                    "cccd",
                    "căn cước",
                    "can cuoc",
                    "hộ chiếu",
                    "ho chieu",
                    "mã số",
                    "ma so",
                ]
            ):
                candidates.append({"label": "ID number", "type": "text"})

        # Only add standalone address if no compound address detected
        if not has_address_compound:
            if any(
                k in t_lower
                for k in [
                    "address",
                    "residential address",
                    "home address",
                    "địa chỉ",
                    "dia chi",
                ]
            ):
                candidates.append({"label": "Address", "type": "text"})

        # de-duplicate by label
        seen = set()
        unique = []
        for c in candidates:
            if c["label"].lower() not in seen:
                seen.add(c["label"].lower())
                unique.append(c)
        if not unique and not compound_fields:
            # fallback generic field representing free-text capture context
            unique = [{"label": "Extracted text", "type": "textarea"}]

        # Map to field schema
        fields = []

        # Add compound fields first
        for c in compound_fields:
            field_id = _slugify(c["label"])
            fields.append(
                {
                    "id": field_id,
                    "label": c["label"],
                    "type": c.get("type", "text"),
                    "required": False,
                    "page": 1,
                    "bbox": None,
                    "subfields": c.get("subfields", []),  # Preserve subfield metadata
                }
            )

        # Add regular fields
        for c in unique:
            fields.append(
                {
                    "id": _slugify(c["label"]),
                    "label": c["label"],
                    "type": c.get("type", "text"),
                    "required": False,
                    "page": 1,
                    "bbox": None,
                }
            )
        return fields

    fields = _infer_fields_from_text(text)

    # Extract title from document content
    def _extract_title_from_text(t: str, filename: str) -> str:
        """Extract meaningful title from document text"""
        if not t or not t.strip():
            # Fallback to filename without extension
            return os.path.splitext(os.path.basename(filename))[0]

        # Get first non-empty line (likely the title/heading)
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        if not lines:
            return os.path.splitext(os.path.basename(filename))[0]

        # Use first line as title, but clean it up
        title = lines[0]

        # If first line is too short, try combining first few words from multiple lines
        if len(title) < 10 and len(lines) > 1:
            # Combine first 2-3 lines up to reasonable length
            combined = " ".join(lines[:3])
            if len(combined) <= 100:
                title = combined

        # Clean up title
        # Remove common form labels/prefixes
        title = re.sub(
            r"^(form|biểu mẫu|mẫu|đơn|application|document)[\s:_-]+",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Limit length
        if len(title) > 100:
            title = title[:97] + "..."

        # If title is still too generic or empty, try using OpenAI
        if not title.strip() or len(title.strip()) < 3:
            openai_title = _generate_title_with_openai(t)
            if openai_title:
                return openai_title
            # Final fallback to filename
            return os.path.splitext(os.path.basename(filename))[0]

        return title.strip()

    def _generate_title_with_openai(content: str) -> str:
        """Use OpenAI to generate a meaningful title from document content"""
        if not OPENAI_AVAILABLE:
            return ""

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return ""

        try:
            client = OpenAI(api_key=api_key)

            # Use first 1000 chars of content to avoid token limits
            content_sample = content[:1000] if len(content) > 1000 else content

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là trợ lý tạo tên biểu mẫu. Dựa trên nội dung văn bản, "
                            "hãy tạo một tên ngắn gọn, rõ ràng cho biểu mẫu (tối đa 100 ký tự). "
                            "Chỉ trả về tên biểu mẫu, không giải thích thêm."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Tạo tên cho biểu mẫu này:\n\n{content_sample}",
                    },
                ],
                temperature=0.3,
                max_tokens=100,
            )

            if not response.choices or not response.choices[0].message.content:
                return ""

            title = response.choices[0].message.content.strip()
            # Remove quotes if OpenAI wrapped the title
            title = title.strip('"').strip("'")

            if len(title) > 100:
                title = title[:97] + "..."

            return title

        except Exception as e:
            print(f"[ocr] OpenAI title generation failed: {e}")
            return ""

    extracted_title = _extract_title_from_text(text, key_hint)

    return {
        "fields": fields,
        "pages": pages,
        "text_sample": text[:500],
        "extracted_title": extracted_title,  # Add extracted title
    }
