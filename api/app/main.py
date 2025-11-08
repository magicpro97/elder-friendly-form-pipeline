import os
from typing import Any, Dict, List, Optional
from bson import ObjectId

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient


MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/forms")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


app = FastAPI(title="FormBot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Question(BaseModel):
    id: str
    text: str
    type: str = Field(default="text")
    options: Optional[List[str]] = None
    required: bool = True


class NextQuestionResponse(BaseModel):
    nextQuestion: Optional[Question] = None
    missingFields: List[str] = []
    done: bool = False


class StartSessionRequest(BaseModel):
    formId: str


class LastAnswer(BaseModel):
    fieldId: str
    value: Any


class NextQuestionRequest(BaseModel):
    lastAnswer: Optional[LastAnswer] = None


class FillRequest(BaseModel):
    answers: Dict[str, Any]


async def get_db():
    client = AsyncIOMotorClient(MONGODB_URI)
    try:
        db = client.get_default_database() if "/" in MONGODB_URI.split("mongodb://")[-1] else client["forms"]
        yield db
    finally:
        client.close()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/forms")
async def list_forms(db=Depends(get_db)):
    forms = []
    async for doc in db.forms.find({}, {"_id": 0}).limit(200):
        forms.append(doc)
    return {"items": forms}


@app.get("/forms/{form_id:path}")
async def get_form(form_id: str, db=Depends(get_db)):
    doc = await db.forms.find_one({"id": form_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Form not found")
    return doc


# Gold layer endpoints
try:
    from .gold_aggregator import (
        aggregate_form_statistics,
        aggregate_all_forms_statistics,
        get_timeseries_data,
        upsert_gold_data
    )
except ImportError:
    from gold_aggregator import (
        aggregate_form_statistics,
        aggregate_all_forms_statistics,
        get_timeseries_data,
        upsert_gold_data
    )


@app.get("/gold/overview")
async def get_gold_overview(db=Depends(get_db)):
    """Get overall gold layer statistics"""
    stats = await aggregate_all_forms_statistics(db)
    return stats


@app.get("/gold/forms/{form_id:path}")
async def get_gold_form_stats(form_id: str, db=Depends(get_db)):
    """Get gold layer statistics for a specific form"""
    stats = await aggregate_form_statistics(db, form_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Form not found")
    return stats


@app.get("/gold/timeseries")
async def get_gold_timeseries(days: int = 7, db=Depends(get_db)):
    """Get time series data"""
    data = await get_timeseries_data(db, days)
    return data


@app.post("/gold/refresh")
async def refresh_gold_data(form_id: Optional[str] = None, db=Depends(get_db)):
    """Refresh gold layer data"""
    await upsert_gold_data(db, form_id)
    return {"status": "success", "message": f"Gold data refreshed for {form_id or 'all forms'}"}


# Minimal OpenAI integration (JSON response) — logic placed inline for MVP
from openai import OpenAI  # type: ignore


def _openai_client() -> Optional[OpenAI]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


async def generate_next_question(form_schema: Dict[str, Any], answers: Dict[str, Any]) -> NextQuestionResponse:
    # If no OpenAI key, fallback to deterministic next unanswered field
    unanswered = [f for f in form_schema.get("fields", []) if f.get("id") not in answers]
    if not unanswered:
        return NextQuestionResponse(done=True)

    client = _openai_client()
    if client is None:
        field = unanswered[0]
        return NextQuestionResponse(
            nextQuestion=Question(id=field["id"], text=field.get("label", field["id"]), type=field.get("type", "text"), required=field.get("required", True)),
            missingFields=[f["id"] for f in unanswered],
            done=False,
        )

    # With OpenAI: request JSON-structured next question
    system = "You are a helpful assistant generating the next single question for a form filling flow. Always return JSON only."
    user = {
        "form_schema": form_schema,
        "answers": answers,
    }
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": str(user)},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        import json

        data = json.loads(content)
        # ensure minimal shape
        if data.get("done"):
            return NextQuestionResponse(done=True)
        nq = data.get("nextQuestion") or {}
        return NextQuestionResponse(
            nextQuestion=Question(
                id=str(nq.get("id")),
                text=str(nq.get("text")),
                type=str(nq.get("type", "text")),
                options=nq.get("options"),
                required=bool(nq.get("required", True)),
            ),
            missingFields=[str(x) for x in data.get("missingFields", [])],
            done=bool(data.get("done", False)),
        )
    except Exception:
        # Fallback on any OpenAI issue
        field = unanswered[0]
        return NextQuestionResponse(
            nextQuestion=Question(id=field["id"], text=field.get("label", field["id"]), type=field.get("type", "text"), required=field.get("required", True)),
            missingFields=[f["id"] for f in unanswered],
            done=False,
        )


def _detect_device_type(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if any(k in ua for k in ["mobile", "iphone", "android", "ipad"]):
        return "mobile"
    if any(k in ua for k in ["tablet", "ipad"]):
        return "tablet"
    return "desktop"


@app.post("/sessions")
async def start_session(payload: StartSessionRequest, request: Request, db=Depends(get_db)):
    form = await db.forms.find_one({"id": payload.formId})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    # capture client info
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else None
    session = {
        "formId": payload.formId,
        "answers": {},
        "status": "active",
        "createdAt": int(os.getenv("CURRENT_TIME", str(int(__import__('time').time())))),
        "client": {
            "userAgent": user_agent,
            "ip": client_ip,
            "deviceType": _detect_device_type(user_agent),
            "referer": request.headers.get("referer"),
            "acceptLanguage": request.headers.get("accept-language"),
        },
        "answerCount": 0,
    }
    result = await db.sessions.insert_one(session)
    return {"sessionId": str(result.inserted_id)}


@app.post("/sessions/{session_id}/next-question")
async def next_question(session_id: str, payload: NextQuestionRequest, request: Request, db=Depends(get_db)):
    # Try to find by ObjectId first
    try:
        session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        session = None
    
    # Fallback: try to find by string id field
    if not session:
        session = await db.sessions.find_one({"sessionId": session_id})
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if payload.lastAnswer is not None:
        session.setdefault("answers", {})[payload.lastAnswer.fieldId] = payload.lastAnswer.value
        # update session metadata
        updates = {
            "answers": session["answers"],
            "lastActiveAt": int(__import__('time').time()),
        }
        await db.sessions.update_one(
            {"_id": session.get("_id")},
            {"$set": updates, "$inc": {"answerCount": 1}}
        )

    form = await db.forms.find_one({"id": session["formId"]}, {"_id": 0})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    resp = await generate_next_question(form_schema=form, answers=session["answers"])
    return resp


# Minimal fill implementation (overlay stub)
from io import BytesIO
from fastapi.responses import StreamingResponse
import boto3
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# Register Unicode font for Vietnamese support
def _register_unicode_font():
    """Register a Unicode-compatible font for Vietnamese text"""
    import os
    import glob
    
    # List of font paths to try (macOS, Linux, Windows)
    font_candidates = [
        # Linux (Debian/Ubuntu) - most common in Docker
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
        '/usr/share/fonts/TTF/DejaVuSans.ttf',
        # macOS
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/Library/Fonts/Arial Unicode.ttf',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        # Windows
        'C:/Windows/Fonts/Arial.ttf',
        'C:/Windows/Fonts/arialuni.ttf',
    ]
    
    # Try each font
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                font_name = 'UnicodeFont'
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                print(f"✅ Registered font: {font_path}")
                return font_name
            except Exception as e:
                print(f"⚠️  Failed to register {font_path}: {e}")
                continue
    
    # Ultimate fallback: use Helvetica
    print("⚠️  No Unicode font found, using Helvetica (Vietnamese may show as boxes)")
    return 'Helvetica'


# Try to register Unicode font at startup
UNICODE_FONT = _register_unicode_font()


def _detect_file_type(file_bytes: bytes) -> str:
    """Detect file type from magic bytes"""
    if file_bytes.startswith(b'%PDF'):
        return 'pdf'
    if file_bytes.startswith(b'PK'):
        return 'docx_or_zip'
    if file_bytes.startswith(b'\xD0\xCF\x11\xE0'):
        return 'doc_ole'
    return 'unknown'


def overlay_pdf(base_pdf_bytes: bytes, annotations: Dict[str, Any], form_schema: Optional[Dict[str, Any]] = None) -> bytes:
    """Overlay annotations on PDF with smart positioning"""
    try:
        base_reader = PdfReader(BytesIO(base_pdf_bytes))
        writer = PdfWriter()
        
        # Get page dimensions from first page
        first_page = base_reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Create field position mapping from schema
        field_positions = {}
        if form_schema:
            for field in form_schema.get("fields", []):
                field_id = field.get("id")
                bbox = field.get("bbox")
                page_num = field.get("page", 1)
                if field_id and bbox:
                    field_positions[field_id] = {
                        "bbox": bbox,
                        "page": page_num
                    }
        
        # Create overlay for each page
        pages_with_overlays = {}
        
        for field_id, value in annotations.items():
            # Get field position if available
            if field_id in field_positions:
                pos = field_positions[field_id]
                page_num = pos["page"]
                bbox = pos["bbox"]  # [x, y, width, height]
                x, y = bbox[0], bbox[1]
            else:
                # Smart fallback: distribute fields vertically on first page
                page_num = 1
                idx = list(annotations.keys()).index(field_id)
                # Position from top with better spacing
                margin = 50
                y_start = page_height - margin - 60  # Leave space for header
                y_offset = 30  # Better spacing
                x = margin
                y = y_start - (idx * y_offset)
            
            # Ensure page overlay exists
            if page_num not in pages_with_overlays:
                pages_with_overlays[page_num] = BytesIO()
                pages_with_overlays[page_num].canvas = canvas.Canvas(
                    pages_with_overlays[page_num], 
                    pagesize=(page_width, page_height)
                )
            
            can = pages_with_overlays[page_num].canvas
            
            # Format value based on type (remove field_id prefix for cleaner output)
            display_value = str(value) if value else ""
            
            # Set font with Vietnamese support
            can.setFont(UNICODE_FONT, 10)
            
            # Word wrap for long text
            max_width = page_width - x - 50
            if can.stringWidth(display_value, UNICODE_FONT, 10) > max_width:
                # Simple word wrap
                words = display_value.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if can.stringWidth(test_line, UNICODE_FONT, 10) <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                
                # Draw wrapped lines
                for i, line in enumerate(lines):
                    can.drawString(x, y - (i * 12), line)
            else:
                # Draw single line
                can.drawString(x, y, display_value)
        
        # Finalize all overlays
        for page_num, overlay_io in pages_with_overlays.items():
            overlay_io.canvas.save()
            overlay_io.seek(0)
        
        # Merge overlays with base PDF pages
        for i, page in enumerate(base_reader.pages):
            page_num = i + 1
            if page_num in pages_with_overlays:
                overlay_reader = PdfReader(pages_with_overlays[page_num])
                if len(overlay_reader.pages) > 0:
                    page.merge_page(overlay_reader.pages[0])
            writer.add_page(page)
        
        # Write output
        out_stream = BytesIO()
        writer.write(out_stream)
        out_stream.seek(0)
        return out_stream.read()
    except Exception as e:
        # If PDF overlay fails, create a new PDF with answers
        return create_pdf_from_answers(annotations)


def create_pdf_from_answers(answers: Dict[str, Any]) -> bytes:
    """Create a new PDF with filled answers"""
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    
    # Title with Vietnamese support
    can.setFont(UNICODE_FONT, 16)
    can.drawString(72, 750, "Biểu mẫu đã điền")
    can.setFont(UNICODE_FONT, 12)
    
    # Answers
    y_start = 700
    y_offset = 25
    for idx, (field_id, value) in enumerate(answers.items()):
        y = y_start - (idx * y_offset)
        if y < 50:  # New page if needed
            can.showPage()
            can.setFont(UNICODE_FONT, 12)
            y = 750 - (idx * y_offset)
        can.drawString(72, y, f"{field_id}: {str(value)}")
    
    can.save()
    packet.seek(0)
    return packet.read()


@app.post("/sessions/{session_id}/fill")
async def fill_pdf(session_id: str, payload: FillRequest, db=Depends(get_db)):
    # Try to find by ObjectId first
    try:
        session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    except Exception:
        session = None
    
    # Fallback: try to find by string id field
    if not session:
        session = await db.sessions.find_one({"sessionId": session_id})
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    form = await db.forms.find_one({"id": session["formId"]}, {"_id": 0})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    bucket = form.get("source", {}).get("bucket") or os.getenv("FORMS_BUCKET")
    key = form.get("source", {}).get("key")
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="Form source not configured")

    obj = s3.get_object(Bucket=bucket, Key=key)
    file_bytes = obj["Body"].read()
    
    # Get answers from session if not provided
    answers = payload.answers if payload.answers else session.get("answers", {})
    
    # Detect file type
    file_type = _detect_file_type(file_bytes)
    
    if file_type == 'pdf':
        try:
            filled = overlay_pdf(file_bytes, answers, form)
            return StreamingResponse(BytesIO(filled), media_type="application/pdf")
        except Exception as e:
            # If PDF overlay fails, create new PDF
            filled = create_pdf_from_answers(answers)
            return StreamingResponse(BytesIO(filled), media_type="application/pdf")
    else:
        # For non-PDF files (DOCX, DOC, images), create a new PDF with answers
        filled = create_pdf_from_answers(answers)
        return StreamingResponse(BytesIO(filled), media_type="application/pdf")


