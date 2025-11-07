import io
import os
import re
import zipfile
from typing import Any, Dict

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image


def _detect_file_type(file_bytes: bytes) -> str:
    # Very lightweight magic-bytes based detection
    if file_bytes.startswith(b'%PDF'):
        return 'pdf'
    if file_bytes.startswith(b'PK'):
        # Likely DOCX (zip). Could be other OOXML; we will confirm below when extracting
        return 'docx_or_zip'
    if file_bytes.startswith(b'\xD0\xCF\x11\xE0'):
        # Old MS OLE Compound Document (DOC, XLS, PPT)
        return 'doc_ole'
    # Try image open
    try:
        Image.open(io.BytesIO(file_bytes))
        return 'image'
    except Exception:
        return 'unknown'


def _get_ocr_langs() -> str:
    return os.getenv('OCR_LANGS', 'vie+eng')


def _extract_text_from_pdf_first_page(file_bytes: bytes) -> str:
    try:
        images = convert_from_bytes(file_bytes, fmt='png', first_page=1, last_page=1)
        if images:
            return pytesseract.image_to_string(images[0], lang=_get_ocr_langs())
    except Exception:
        pass
    # Fallback attempt as image
    try:
        return pytesseract.image_to_string(Image.open(io.BytesIO(file_bytes)), lang=_get_ocr_langs())
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
            if 'word/document.xml' not in zf.namelist():
                return ""
            xml_bytes = zf.read('word/document.xml')
            xml_text = xml_bytes.decode('utf-8', errors='ignore')
            # Replace runs/paragraphs with spaces/newlines for readability
            # Remove XML tags
            # Keep simple: replace paragraph boundaries with newlines
            xml_text = re.sub(r'</w:p>', '\n', xml_text)
            # Strip remaining tags
            text = re.sub(r'<[^>]+>', '', xml_text)
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
    except Exception:
        return ""


def _extract_text_from_doc_ole_best_effort(file_bytes: bytes) -> str:
    # Best-effort for legacy .doc without external tools: extract readable ASCII/UTF-8 sequences
    try:
        # Decode as latin-1 to preserve bytes then filter printable ranges
        data = file_bytes
        # Find sequences of printable characters of length >= 4
        candidates = re.findall(rb'[\x20-\x7E\t\r\n]{4,}', data)
        text = b' '.join(candidates).decode('utf-8', errors='ignore')
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    except Exception:
        return ""


def ocr_extract_fields(file_bytes: bytes, key_hint: str) -> Dict[str, Any]:
    # Multi-format text extraction with OCR fallbacks
    file_type = _detect_file_type(file_bytes)

    text = ""
    pages = 1
    if file_type == 'pdf':
        # Try first page OCR, also count pages if possible
        try:
            all_images = convert_from_bytes(file_bytes, fmt='png')
            pages = max(1, len(all_images))
            if all_images:
                text = pytesseract.image_to_string(all_images[0], lang=_get_ocr_langs())
            else:
                text = ""
        except Exception:
            text = _extract_text_from_pdf_first_page(file_bytes)
            pages = 1
    elif file_type == 'image':
        text = _extract_text_from_image(file_bytes)
        pages = 1
    elif file_type == 'docx_or_zip':
        text = _extract_text_from_docx(file_bytes)
        pages = 1
    elif file_type == 'doc_ole':
        text = _extract_text_from_doc_ole_best_effort(file_bytes)
        pages = 1
    else:
        # Unknown: try PDF first-page logic then image OCR
        text = _extract_text_from_pdf_first_page(file_bytes)
        if not text:
            text = _extract_text_from_image(file_bytes)
    
    def _slugify(label: str) -> str:
        s = label.lower()
        s = re.sub(r'[^a-z0-9]+', '_', s)
        s = re.sub(r'_+', '_', s).strip('_')
        return s or 'field'

    def _infer_fields_from_text(t: str):
        t_lower = (t or "").lower()
        candidates = []
        # simple keyword presence checks (English + Vietnamese)
        if any(k in t_lower for k in [
            "full name", "applicant name", "name:", "name ",
            "họ và tên", "ho va ten", "họ tên", "ho ten"
        ]):
            candidates.append({"label": "Full name", "type": "text"})
        if any(k in t_lower for k in [
            "email", "e-mail"
        ]):
            candidates.append({"label": "Email", "type": "email"})
        if any(k in t_lower for k in [
            "phone", "telephone", "mobile",
            "số điện thoại", "so dien thoai", "điện thoại", "dien thoai"
        ]):
            candidates.append({"label": "Phone", "type": "tel"})
        if any(k in t_lower for k in [
            "date of birth", "dob", "birth date",
            "ngày sinh", "ngay sinh", "sinh nhật", "sinh nhat"
        ]):
            candidates.append({"label": "Date of birth", "type": "date"})
        elif any(k in t_lower for k in [
            "date:", "date ", "ngày:", "ngay:"
        ]):
            candidates.append({"label": "Date", "type": "date"})
        if any(k in t_lower for k in [
            "id number", "id no", "passport", "national id",
            "cmnd", "cccd", "căn cước", "can cuoc", "hộ chiếu", "ho chieu", "mã số", "ma so"
        ]):
            candidates.append({"label": "ID number", "type": "text"})
        if any(k in t_lower for k in [
            "address", "residential address", "home address",
            "địa chỉ", "dia chi"
        ]):
            candidates.append({"label": "Address", "type": "text"})

        # de-duplicate by label
        seen = set()
        unique = []
        for c in candidates:
            if c["label"].lower() not in seen:
                seen.add(c["label"].lower())
                unique.append(c)
        if not unique:
            # fallback generic field representing free-text capture context
            unique = [{"label": "Extracted text", "type": "textarea"}]
        # Map to field schema
        fields = []
        for c in unique:
            fields.append({
                "id": _slugify(c["label"]),
                "label": c["label"],
                "type": c.get("type", "text"),
                "required": False,
                "page": 1,
                "bbox": None,
            })
        return fields

    fields = _infer_fields_from_text(text)

    return {
        "fields": fields,
        "pages": pages,
        "text_sample": text[:500],
    }


