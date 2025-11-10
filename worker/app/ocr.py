import io
import logging
import os
import re
import subprocess
import tempfile
import zipfile
from typing import Any, Dict

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from pypdf import PdfReader

# OpenAI for generating form titles
try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)


def _extract_pdf_fonts(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Extract font information from PDF for consistent overlay rendering
    Returns: {primary_font: str, font_size: float, fonts: [font names]}
    """
    try:
        pdf = PdfReader(io.BytesIO(pdf_bytes))
        if not pdf.pages:
            return {"primary_font": "Times-Roman", "font_size": 12, "fonts": []}

        # Get fonts from first page
        page = pdf.pages[0]
        fonts = []

        if "/Resources" in page and "/Font" in page["/Resources"]:
            font_dict = page["/Resources"]["/Font"]
            for font_key in font_dict:
                try:
                    font_obj = font_dict[font_key]
                    if "/BaseFont" in font_obj:
                        font_name = str(font_obj["/BaseFont"]).strip("/")
                        fonts.append(font_name)
                except Exception as e:
                    logger.debug(f"Error reading font {font_key}: {e}")

        # Determine primary font (most common pattern in Vietnamese forms)
        primary_font = "Times-Roman"  # Default
        if fonts:
            # Prefer Times, Arial, or Liberation fonts for Vietnamese
            for font in fonts:
                font_lower = font.lower()
                if "times" in font_lower or "liberation" in font_lower:
                    primary_font = font
                    break
                elif "arial" in font_lower or "helvetica" in font_lower:
                    primary_font = font

        logger.info(f"[PDF Fonts] Detected: {fonts}, primary: {primary_font}")

        return {
            "primary_font": primary_font,
            "font_size": 12,  # Default, could be extracted from content stream
            "fonts": fonts[:5],  # Keep top 5 fonts
        }

    except Exception as e:
        logger.error(f"[PDF Fonts] Extraction error: {e}")
        return {"primary_font": "Times-Roman", "font_size": 12, "fonts": []}


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


def _convert_doc_to_pdf(doc_bytes: bytes, filename: str = "input.doc") -> bytes:
    """Convert DOC/DOCX to PDF using LibreOffice headless"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write DOC to temp file
            input_ext = ".doc" if filename.endswith(".doc") else ".docx"
            input_path = os.path.join(tmpdir, f"input{input_ext}")
            with open(input_path, "wb") as f:
                f.write(doc_bytes)

            # Convert using LibreOffice
            logger.info(f"Converting {filename} to PDF with LibreOffice...")
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmpdir,
                    input_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr}")
                raise Exception(f"Conversion failed: {result.stderr}")

            # Read converted PDF
            output_path = os.path.join(tmpdir, "input.pdf")
            if not os.path.exists(output_path):
                raise Exception("PDF output not found after conversion")

            with open(output_path, "rb") as f:
                pdf_bytes = f.read()

            logger.info(
                f"Successfully converted {filename} to PDF ({len(pdf_bytes)} bytes)"
            )
            return pdf_bytes

    except subprocess.TimeoutExpired:
        logger.error("LibreOffice conversion timeout")
        raise Exception("Document conversion timeout (30s)")
    except Exception as e:
        logger.error(f"DOC/DOCX conversion error: {e}")
        raise


def _detect_all_input_fields_layout(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Layout-based input field detection - detects ALL input boxes regardless of labels.

    Strategy:
    1. Detect ALL horizontal lines (underscores for text input)
    2. Detect ALL rectangles (boxes for input)
    3. OCR ALL text blocks with positions
    4. For each input element, find closest text label above/left
    5. Return all detected input positions with their labels

    This is more robust than keyword matching - works for ANY form.
    """
    try:
        logger.info("[Layout] Starting layout-based bbox detection")

        # Convert PDF first page to image
        images = convert_from_bytes(pdf_bytes, dpi=300, first_page=1, last_page=1)
        if not images:
            logger.warning("[Layout] No images from PDF")
            return {"field_positions": []}

        # Convert PIL to OpenCV format
        img = images[0]
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape

        logger.info(f"[Layout] Image size: {width}x{height}")

        # 1. Detect horizontal lines (underscores) with multiple kernel sizes
        input_elements = []

        # Try smaller kernel first for short underlines
        for kernel_width in [25, 40, 60]:
            horizontal_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT, (kernel_width, 1)
            )
            detect_horizontal = cv2.morphologyEx(
                gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2
            )
            line_cnts = cv2.findContours(
                detect_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            line_cnts = line_cnts[0] if len(line_cnts) == 2 else line_cnts[1]

            for c in line_cnts:
                x, y, w, h = cv2.boundingRect(c)
                if w > 30:  # Lower minimum line width
                    # Check for duplicates
                    is_duplicate = False
                    for elem in input_elements:
                        if (
                            abs(elem["x"] - x) < 30
                            and abs(elem["y"] - y) < 10
                            and abs(elem["width"] - w) < 50
                        ):
                            is_duplicate = True
                            break

                    if not is_duplicate:
                        input_elements.append(
                            {
                                "x": x,
                                "y": y,
                                "width": w,
                                "height": max(h, 20),
                                "type": "line",
                            }
                        )

        logger.info(f"[Layout] Detected {len(input_elements)} input lines")

        # 2. Detect rectangles/boxes (alternative input style)
        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)
        # Find contours
        rect_cnts = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rect_cnts = rect_cnts[0] if len(rect_cnts) == 2 else rect_cnts[1]

        box_count = 0
        for c in rect_cnts:
            x, y, w, h = cv2.boundingRect(c)
            # Looser filter: reasonable size for input box
            if 50 < w < 1000 and 10 < h < 100 and w / h > 2:
                # Check if not overlapping with existing lines
                is_duplicate = False
                for elem in input_elements:
                    if (
                        abs(elem["x"] - x) < 20
                        and abs(elem["y"] - y) < 20
                        and abs(elem["width"] - w) < 50
                    ):
                        is_duplicate = True
                        break

                if not is_duplicate:
                    input_elements.append(
                        {"x": x, "y": y, "width": w, "height": h, "type": "box"}
                    )
                    box_count += 1

        logger.info(f"[Layout] Detected {box_count} input boxes")
        logger.info(
            f"[Layout] Total input elements (lines + boxes): {len(input_elements)}"
        )

        # 3. OCR all text with positions
        ocr_data = pytesseract.image_to_data(
            img, lang="vie+eng", output_type=pytesseract.Output.DICT
        )

        text_blocks = []
        for i in range(len(ocr_data["text"])):
            text = ocr_data["text"][i].strip()
            if not text or len(text) < 2:  # Skip single chars
                continue

            text_blocks.append(
                {
                    "text": text,
                    "x": ocr_data["left"][i],
                    "y": ocr_data["top"][i],
                    "width": ocr_data["width"][i],
                    "height": ocr_data["height"][i],
                    "conf": ocr_data["conf"][i],
                }
            )

        logger.info(f"[Layout] Extracted {len(text_blocks)} text blocks")

        # 3.5. Group nearby text blocks into multi-word labels
        # Field labels are often multiple words: "Tên đầy đủ", "Số điện thoại"
        grouped_labels = []
        used_blocks = set()

        for block in text_blocks:
            if id(block) in used_blocks:
                continue

            # Find nearby text blocks on same line (within 5px vertical, 100px horizontal)
            group = [block]
            used_blocks.add(id(block))

            for other in text_blocks:
                if id(other) in used_blocks:
                    continue

                # Same line if Y positions close
                if abs(block["y"] - other["y"]) < 5:
                    # Check if horizontally nearby (within 100px)
                    x_distance = abs(
                        (block["x"] + block["width"]) - other["x"]
                    )  # Gap between blocks
                    if x_distance < 100:
                        group.append(other)
                        used_blocks.add(id(other))

            # Sort group by X position (left to right)
            group.sort(key=lambda b: b["x"])

            # Combine into single label
            combined_text = " ".join([b["text"] for b in group])
            avg_conf = sum([b["conf"] for b in group]) / len(group)

            grouped_labels.append(
                {
                    "text": combined_text,
                    "x": min([b["x"] for b in group]),
                    "y": min([b["y"] for b in group]),
                    "width": max([b["x"] + b["width"] for b in group])
                    - min([b["x"] for b in group]),
                    "height": max([b["height"] for b in group]),
                    "conf": avg_conf,
                }
            )

        logger.info(
            f"[Layout] Grouped {len(text_blocks)} blocks → {len(grouped_labels)} labels"
        )

        # 4. For each input element, find closest text label
        field_positions = []

        for idx, elem in enumerate(input_elements):
            # Find text blocks near this input element
            # Look for text ABOVE or to the LEFT of input
            elem_center_x = elem["x"] + elem["width"] / 2
            elem_center_y = elem["y"] + elem["height"] / 2

            # Find all candidate labels (above or left)
            candidates = []

            for block in grouped_labels:  # Use grouped labels instead of single blocks
                # Skip very short text (likely not a label)
                if len(block["text"]) < 3:
                    continue

                block_center_x = block["x"] + block["width"] / 2
                block_center_y = block["y"] + block["height"] / 2

                # Check if text is above or left of input
                # Above: same X column, Y is above
                is_above = (
                    abs(block_center_x - elem_center_x) < 300
                    and block_center_y < elem_center_y
                    and elem_center_y - block_center_y < 100
                )

                # Left: same Y row, X is left
                is_left = (
                    abs(block_center_y - elem_center_y) < 30
                    and block_center_x < elem_center_x
                    and elem_center_x - block_center_x < 400
                )

                if is_above or is_left:
                    # Calculate distance
                    distance = (
                        (block_center_x - elem_center_x) ** 2
                        + (block_center_y - elem_center_y) ** 2
                    ) ** 0.5

                    # Prioritize labels:
                    # - Longer text (likely field labels)
                    # - Text ending with ":" (common label pattern)
                    # - Higher confidence
                    priority_score = (
                        len(block["text"]) * 10  # Favor longer text
                        + (50 if block["text"].endswith(":") else 0)  # Label indicator
                        + block["conf"] / 10  # OCR confidence
                    )

                    candidates.append(
                        {
                            "block": block,
                            "distance": distance,
                            "priority": priority_score,
                        }
                    )

            # Choose best candidate: highest priority, then closest distance
            closest_label = None
            if candidates:
                # Sort by priority (high to low), then distance (low to high)
                candidates.sort(key=lambda c: (-c["priority"], c["distance"]))
                closest_label = candidates[0]["block"]

            if closest_label:
                field_positions.append(
                    {
                        "field_id": f"field_{idx}",
                        "label": closest_label["text"],
                        "bbox": {
                            "x": elem["x"],
                            "y": elem["y"],
                            "width": elem["width"],
                            "height": elem["height"],
                            "page": 1,
                        },
                        "confidence": closest_label["conf"],
                        "auto_detected": True,
                        "detection_type": "layout",
                    }
                )
                logger.info(
                    f"[Layout] Field {idx}: '{closest_label['text']}' → "
                    f"input at ({elem['x']}, {elem['y']})"
                )

        logger.info(f"[Layout] Detected {len(field_positions)} labeled input fields")

        return {"field_positions": field_positions}

    except Exception as e:
        logger.error(f"[Layout] Detection failed: {e}", exc_info=True)
        return {"field_positions": []}


def _detect_form_fields_opencv(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Auto-detect form field positions using OpenCV
    Returns: {field_positions: [{label: str, bbox: {x, y, width, height}, page: int}]}

    Strategy:
    1. Convert PDF to image
    2. Detect horizontal lines (form underscores)
    3. OCR text with coordinates
    4. Match text labels (phone, name, etc.) with nearby horizontal lines
    5. Return bbox positions
    """
    try:
        logger.info("[OpenCV] Starting auto bbox detection")

        # Convert PDF first page to image
        images = convert_from_bytes(pdf_bytes, dpi=300, first_page=1, last_page=1)
        if not images:
            logger.warning("[OpenCV] No images from PDF")
            return {"field_positions": []}

        # Convert PIL to OpenCV format
        img = images[0]
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape

        logger.info(f"[OpenCV] Image size: {width}x{height}")

        # Detect horizontal lines (common for form input fields)
        # Create horizontal kernel
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        detect_horizontal = cv2.morphologyEx(
            gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2
        )
        cnts = cv2.findContours(
            detect_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]

        # Extract horizontal line positions
        horizontal_lines = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w > 50:  # Minimum line width
                horizontal_lines.append({"x": x, "y": y, "width": w, "height": h})

        logger.info(f"[OpenCV] Detected {len(horizontal_lines)} horizontal lines")

        # OCR with bbox coordinates
        ocr_data = pytesseract.image_to_data(
            img, lang="vie+eng", output_type=pytesseract.Output.DICT
        )

        # Extract text blocks with positions
        text_blocks = []
        for i in range(len(ocr_data["text"])):
            text = ocr_data["text"][i].strip()
            if not text:
                continue

            text_blocks.append(
                {
                    "text": text,
                    "x": ocr_data["left"][i],
                    "y": ocr_data["top"][i],
                    "width": ocr_data["width"][i],
                    "height": ocr_data["height"][i],
                    "conf": ocr_data["conf"][i],
                }
            )

        logger.info(f"[OpenCV] Extracted {len(text_blocks)} text blocks")

        # Match text labels with nearby horizontal lines
        # Expanded patterns to match more Vietnamese form variants
        # Use word boundaries (\b) to avoid false positives like "học" matching "ho"
        field_patterns = {
            "phone": r"\b(điện thoại|dien thoai|phone|sdt|số điện thoại"
            r"|so dien thoai|di động|di dong|mobile)\b",
            "email": r"\b(email|e-mail|thư điện tử|thu dien tu)\b",
            "name": r"\b(họ tên|ho ten|họ và tên|ho va ten|fullname"
            r"|tên đầy đủ|ten day du)\b",
            "dob": r"\b(ngày sinh|ngay sinh|date of birth|dob"
            r"|ngày tháng năm sinh|ngay thang nam sinh|năm sinh|nam sinh)\b",
            "address": r"\b(địa chỉ|dia chi|address|nơi ở|noi o"
            r"|địa điểm|dia diem)\b",
            "id_number": r"\b(cccd|cmnd|căn cước|can cuoc|số cccd|so cccd"
            r"|số định danh|so dinh danh|hộ chiếu|ho chieu|passport)\b",
            "position": r"\b(vị trí|vi tri|position|chức vụ|chuc vu)\b",
            "department": r"\b(phòng ban|phong ban|department" r"|bộ phận|bo phan)\b",
            "education": r"\b(học vấn|hoc van|trình độ học vấn"
            r"|trinh do hoc van|bằng cấp|bang cap)\b",
            "company": r"\b(công ty|cong ty|company|doanh nghiệp"
            r"|doanh nghiep|nơi làm việc|noi lam viec)\b",
        }

        field_positions = []

        # Debug: Log some text blocks to see what we're working with
        logger.info("[OpenCV] Sample text blocks (first 10):")
        for i, block in enumerate(text_blocks[:10]):
            logger.info(f"  [{i}] '{block['text']}' at ({block['x']}, {block['y']})")

        for field_id, pattern in field_patterns.items():
            # Find text blocks matching this field
            matched_texts = []
            for block in text_blocks:
                if re.search(pattern, block["text"].lower()):
                    matched_texts.append(block)
                    logger.info(
                        f"[OpenCV] Found '{field_id}' candidate: '{block['text']}' at ({block['x']}, {block['y']})"
                    )

            if not matched_texts:
                logger.debug(
                    f"[OpenCV] No text match for pattern '{field_id}': {pattern}"
                )
                continue

            # For each matched text, try to find input field position
            for block in matched_texts:
                # Find nearest horizontal line below this text (within 50px)
                nearest_line = None
                min_distance = float("inf")

                text_bottom = block["y"] + block["height"]

                for line in horizontal_lines:
                    # Check if line is roughly aligned horizontally
                    if abs(line["x"] - block["x"]) < 200:  # Same column
                        # Check if line is below text
                        vertical_distance = line["y"] - text_bottom
                        if 0 < vertical_distance < 80:  # Line is 0-80px below text
                            if vertical_distance < min_distance:
                                min_distance = vertical_distance
                                nearest_line = line

                if nearest_line:
                    # Found input field position!
                    field_positions.append(
                        {
                            "field_id": field_id,
                            "label": block["text"],
                            "bbox": {
                                "x": nearest_line["x"],
                                "y": nearest_line["y"],
                                "width": nearest_line["width"],
                                "height": 20,  # Standard text height
                                "page": 1,
                            },
                            "confidence": block["conf"],
                            "auto_detected": True,
                        }
                    )
                    logger.info(
                        f"[OpenCV] Matched '{field_id}' at ({nearest_line['x']}, {nearest_line['y']})"
                    )
                    break  # Only match once per field type
                else:
                    # No line found - use position next to the text label
                    # Common pattern: "Phone: __________" where input is right of label
                    field_positions.append(
                        {
                            "field_id": field_id,
                            "label": block["text"],
                            "bbox": {
                                "x": block["x"] + block["width"] + 10,  # 10px spacing
                                "y": block["y"],
                                "width": 200,  # Default input width
                                "height": block["height"],
                                "page": 1,
                            },
                            "confidence": block["conf"],
                            "auto_detected": True,
                            "fallback": True,  # Indicates this is fallback positioning
                        }
                    )
                    logger.info(
                        f"[OpenCV] Fallback position for '{field_id}' at "
                        f"({block['x'] + block['width'] + 10}, {block['y']})"
                    )

        logger.info(f"[OpenCV] Auto-detected {len(field_positions)} field positions")

        # Extract font info from PDF for consistent overlay rendering
        font_info = _extract_pdf_fonts(pdf_bytes)

        return {
            "field_positions": field_positions,
            "image_width": width,
            "image_height": height,
            "font_info": font_info,  # Font metadata for overlay
        }

    except Exception as e:
        logger.error(f"[OpenCV] Bbox detection error: {e}")
        return {"field_positions": []}


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


def _extract_fields_with_openai(content: str) -> list:
    """
    Use OpenAI to intelligently extract ALL form fields from document content
    Returns list of fields with proper types and labels
    """
    if not OPENAI_AVAILABLE:
        logger.warning("OpenAI not available, cannot extract fields")
        return []

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not set")
        return []

    try:
        client = OpenAI(api_key=api_key)

        # Use first 3000 chars to capture most form content
        content_sample = content[:3000] if len(content) > 3000 else content

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là trợ lý phân tích biểu mẫu. "
                        "Nhiệm vụ của bạn là phát hiện TẤT CẢ các trường (fields) "
                        "cần điền trong biểu mẫu.\n\n"
                        "Quy tắc:\n"
                        '1. Tìm tất cả các trường có định dạng: "Label:", '
                        '"Label......", "Label:_____", etc.\n'
                        "2. Phân loại field type chính xác:\n"
                        '   - "text": Văn bản thông thường (tên, địa chỉ, mô tả)\n'
                        '   - "tel": Số điện thoại\n'
                        '   - "email": Email\n'
                        '   - "date": Ngày tháng\n'
                        '   - "number": Số\n'
                        '   - "textarea": Văn bản dài (nhiều dòng)\n\n'
                        "3. Sử dụng label gốc trong biểu mẫu "
                        "(giữ nguyên tiếng Việt có dấu)\n"
                        "4. KHÔNG bỏ sót bất kỳ trường nào\n\n"
                        "Trả về JSON với format:\n"
                        "{\n"
                        '  "fields": [\n'
                        '    {"label": "Tên đầy đủ", "type": "text"},\n'
                        '    {"label": "Số điện thoại", "type": "tel"},\n'
                        "    ...\n"
                        "  ]\n"
                        "}\n\n"
                        "CHỈ trả về JSON object, KHÔNG giải thích thêm."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Phân tích biểu mẫu này và liệt kê TẤT CẢ các trường "
                        f"cần điền:\n\n{content_sample}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        logger.info(
            f"OpenAI response object: choices={len(response.choices) if response.choices else 0}"
        )
        if response.choices and response.choices[0].message:
            content_len = (
                len(response.choices[0].message.content)
                if response.choices[0].message.content
                else 0
            )
            logger.info(f"OpenAI content length: {content_len}")

        if not response.choices or not response.choices[0].message.content:
            logger.warning("OpenAI returned empty response for field extraction")
            return []

        result_text = response.choices[0].message.content.strip()
        logger.info(f"OpenAI raw response: {result_text[:500]}")  # Log first 500 chars

        # Parse JSON response
        import json

        result = json.loads(result_text)

        # Handle both {"fields": [...]} and direct array formats
        if isinstance(result, dict) and "fields" in result:
            fields_data = result["fields"]
        elif isinstance(result, list):
            fields_data = result
        else:
            logger.warning(f"Unexpected OpenAI response format: {result}")
            return []

        logger.info(f"OpenAI extracted {len(fields_data)} fields from form")
        if len(fields_data) > 0:
            logger.info(f"Sample fields: {fields_data[:3]}")  # Log first 3 fields

        return fields_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON response: {e}")
        return []
    except Exception as e:
        logger.error(f"OpenAI field extraction failed: {e}")
        return []


def ocr_extract_fields(file_bytes: bytes, key_hint: str) -> Dict[str, Any]:
    # Multi-format text extraction with OCR fallbacks
    file_type = _detect_file_type(file_bytes)

    # Convert DOC/DOCX to PDF first for accurate bbox coordinates
    converted_pdf_bytes = None
    if file_type in ["doc_ole", "docx_or_zip"]:
        logger.info(f"Detected {file_type}, converting to PDF before OCR...")
        try:
            converted_pdf_bytes = _convert_doc_to_pdf(file_bytes, key_hint)
            file_bytes = converted_pdf_bytes  # Use PDF for OCR
            file_type = "pdf"  # Treat as PDF from now on
            logger.info("Conversion successful, will OCR the PDF")
        except Exception as e:
            logger.warning(f"Conversion failed, falling back to original: {e}")
            # Continue with original DOC/DOCX extraction

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

    def _detect_form_fields_from_patterns(text: str) -> list:
        """
        Detect form fields from common patterns like:
        - "Label:" or "Label :"
        - "Label.........."
        - "Label:________"
        Returns list of potential field labels
        """
        if not text:
            return []

        lines = text.split("\n")
        detected_fields = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Pattern 1: "Label:" or "Label :"
            colon_match = re.match(r"^(.+?):\s*$", line)
            if colon_match:
                label = colon_match.group(1).strip()
                # Filter out common non-field labels
                if len(label) > 2 and label.lower() not in [
                    "kính gửi",
                    "dear",
                    "to",
                    "from",
                ]:
                    detected_fields.append(label)
                continue

            # Pattern 2: "Label........" or "Label_______"
            dot_match = re.match(r"^(.+?)(\.{3,}|_{3,})\s*$", line)
            if dot_match:
                label = dot_match.group(1).strip()
                if len(label) > 2:
                    detected_fields.append(label)
                continue

            # Pattern 3: "Label: value_placeholder" (more flexible)
            colon_with_space = re.match(r"^(.+?):\s+(.{0,50})\s*$", line)
            if colon_with_space:
                label = colon_with_space.group(1).strip()
                placeholder = colon_with_space.group(2).strip()
                # If placeholder looks like a blank (dots, underscores, or short)
                if (
                    re.match(r"^[._\s]*$", placeholder)
                    or len(placeholder) < 3
                    and len(label) > 2
                ):
                    detected_fields.append(label)

        return detected_fields

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

    # Try OpenAI-based field extraction first (intelligent detection)
    openai_fields = _extract_fields_with_openai(text)

    if openai_fields:
        logger.info(f"Using OpenAI-extracted {len(openai_fields)} fields")
        fields = []
        for field_data in openai_fields:
            fields.append(
                {
                    "id": _slugify(field_data.get("label", "field")),
                    "label": field_data.get("label", ""),
                    "type": field_data.get("type", "text"),
                    "required": False,
                    "page": 1,
                    "bbox": None,
                }
            )
    else:
        # Fallback to keyword-based detection if OpenAI fails
        logger.warning(
            "OpenAI field extraction failed, using fallback keyword detection"
        )
        fields = _infer_fields_from_text(text)

        # Enhance with pattern-detected fields as additional fallback
        pattern_detected_labels = _detect_form_fields_from_patterns(text)
        existing_labels = {f["label"].lower() for f in fields}

        for label in pattern_detected_labels:
            if label.lower() not in existing_labels:
                # Infer field type from label
                field_type = "text"  # Default
                label_lower = label.lower()

                if any(
                    k in label_lower
                    for k in [
                        "phone",
                        "telephone",
                        "điện thoại",
                        "dien thoai",
                        "số điện thoại",
                    ]
                ):
                    field_type = "tel"
                elif any(
                    k in label_lower
                    for k in [
                        "email",
                        "e-mail",
                        "thư điện tử",
                        "thu dien tu",
                    ]
                ):
                    field_type = "email"
                elif any(
                    k in label_lower
                    for k in [
                        "date",
                        "ngày",
                        "ngay",
                        "sinh",
                        "birth",
                        "dob",
                    ]
                ):
                    field_type = "date"
                elif any(
                    k in label_lower
                    for k in [
                        "địa chỉ",
                        "dia chi",
                        "address",
                        "nơi ở",
                        "noi o",
                    ]
                ):
                    field_type = "text"  # Could be textarea but keep simple

                fields.append(
                    {
                        "id": _slugify(label),
                        "label": label,
                        "type": field_type,
                        "required": False,
                        "page": 1,
                        "bbox": None,
                    }
                )
                existing_labels.add(label.lower())

        logger.info(
            f"Detected {len(fields)} fields using fallback: {len(pattern_detected_labels)} from patterns, "
            f"{len(fields) - len(pattern_detected_labels)} from keywords"
        )

    # Extract title from document content
    def _extract_title_from_text(t: str, filename: str) -> str:
        """Extract meaningful title from document text using OpenAI for Vietnamese forms"""
        if not t or not t.strip():
            # Fallback to filename without extension
            return os.path.splitext(os.path.basename(filename))[0]

        # For Vietnamese text, use OpenAI directly for better quality
        # Detect Vietnamese characters (À-ỹ range covers Vietnamese diacritics)
        if re.search(r"[\u00C0-\u1EF9]", t):
            openai_title = _generate_title_with_openai(t)
            if openai_title:
                logger.info(f"Generated title with OpenAI: {openai_title}")
                return openai_title
            logger.warning(
                "OpenAI title generation failed, falling back to text extraction"
            )

        # Fallback: Extract from text (for non-Vietnamese or if OpenAI fails)
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        if not lines:
            return os.path.splitext(os.path.basename(filename))[0]

        # Skip common Vietnamese government headers
        skip_patterns = [
            r"^CỘNG\s+H[ÒO]A",  # CỘNG HÒA / CỘNG HOA
            r"^Độc\s+lập",  # Độc lập - Tự do - Hạnh phúc
            r"^[0-9]+\s+[0-9/\-TT]+",  # Decree numbers like "9 15/2023/TT-BKHCN"
            r"^[0-9]{10,}",  # Long number sequences
        ]

        filtered_lines = []
        for line in lines:
            # Check if line matches any skip pattern
            should_skip = any(
                re.match(pattern, line, re.IGNORECASE) for pattern in skip_patterns
            )
            if not should_skip:
                filtered_lines.append(line)

        # Use first non-skipped line as title
        if filtered_lines:
            title = filtered_lines[0]
        else:
            # If all lines were filtered, use first line anyway
            title = lines[0]

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

        return (
            title.strip()
            if title.strip()
            else os.path.splitext(os.path.basename(filename))[0]
        )

    def _generate_title_with_openai(content: str) -> str:
        """Use OpenAI to generate a meaningful title from document content"""
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI library not available")
            return ""

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")
            return ""

        try:
            client = OpenAI(api_key=api_key)

            # Use first 1000 chars of content to avoid token limits
            content_sample = content[:1000] if len(content) > 1000 else content

            response = client.chat.completions.create(
                model="gpt-5-mini",
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
                logger.warning("OpenAI returned empty response")
                return ""

            title = response.choices[0].message.content.strip()
            # Remove quotes if OpenAI wrapped the title
            title = title.strip('"').strip("'")

            if len(title) > 100:
                title = title[:97] + "..."

            return title

        except Exception as e:
            logger.error(f"OpenAI title generation exception: {e}", exc_info=True)
            return ""

    extracted_title = _extract_title_from_text(text, key_hint)

    # Auto-detect bbox positions using OpenCV (for PDF files)
    bbox_detection_result = {}
    logger.info(
        f"Checking bbox detection: file_type={file_type}, converted_pdf_bytes={bool(converted_pdf_bytes)}"
    )

    if file_type == "pdf" or converted_pdf_bytes:
        # Use the final PDF bytes (either original or converted)
        pdf_for_bbox = converted_pdf_bytes if converted_pdf_bytes else file_bytes
        logger.info(f"Running bbox detection on PDF ({len(pdf_for_bbox)} bytes)")

        try:
            # Try layout-based detection first (more robust, universal)
            logger.info("[Bbox] Trying layout-based detection...")
            bbox_detection_result = _detect_all_input_fields_layout(pdf_for_bbox)

            # If layout detection found too few fields, fallback to keyword-based
            detected_count = len(bbox_detection_result.get("field_positions", []))
            if detected_count < 3:
                logger.info(
                    f"[Bbox] Layout detection found only {detected_count} fields, "
                    f"trying keyword-based fallback..."
                )
                keyword_result = _detect_form_fields_opencv(pdf_for_bbox)
                if len(keyword_result.get("field_positions", [])) > detected_count:
                    bbox_detection_result = keyword_result
                    logger.info(
                        f"[Bbox] Using keyword-based detection "
                        f"({len(keyword_result.get('field_positions', []))} fields)"
                    )

            logger.info(
                f"Bbox detection result: {len(bbox_detection_result.get('field_positions', []))} positions"
            )
        except Exception as bbox_err:
            logger.error(f"Bbox detection failed: {bbox_err}", exc_info=True)
            bbox_detection_result = {"field_positions": [], "error": str(bbox_err)}

        # Merge detected bbox into fields
        if bbox_detection_result.get("field_positions"):
            # Try to match bbox by label similarity (fuzzy matching)
            # Since OpenCV uses hardcoded field_ids ("phone", "name")
            # but OpenAI generates different IDs ("i_n_tho_i", "t_n_t_i_l")
            import difflib

            for field in fields:
                field_label_lower = field["label"].lower()

                # Find best matching bbox by label similarity
                best_match = None
                best_score = 0

                for fp in bbox_detection_result["field_positions"]:
                    detected_label_lower = fp["label"].lower()

                    # Calculate similarity score
                    score = difflib.SequenceMatcher(
                        None, field_label_lower, detected_label_lower
                    ).ratio()

                    if score > best_score and score > 0.3:  # Minimum 30% match
                        best_score = score
                        best_match = fp

                if best_match:
                    field["bbox"] = best_match["bbox"]
                    logger.info(
                        f"Applied bbox for '{field['label']}' "
                        f"(matched with '{best_match['label']}', "
                        f"score={best_score:.2f})"
                    )
        else:
            logger.warning("No bbox positions detected by OpenCV")

    result = {
        "fields": fields,
        "pages": pages,
        "text_sample": text[:500],
        "extracted_title": extracted_title,  # Add extracted title
        "bbox_detection": bbox_detection_result,  # Include detection metadata
    }

    # If we converted DOC/DOCX to PDF, include the PDF bytes for S3 upload
    if converted_pdf_bytes:
        result["converted_pdf_bytes"] = converted_pdf_bytes
        result["was_converted"] = True
        logger.info(f"Returning converted PDF ({len(converted_pdf_bytes)} bytes)")

    return result
