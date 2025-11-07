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


def _detect_file_type(file_bytes: bytes) -> str:
    """Detect file type from magic bytes"""
    if file_bytes.startswith(b'%PDF'):
        return 'pdf'
    if file_bytes.startswith(b'PK'):
        return 'docx_or_zip'
    if file_bytes.startswith(b'\xD0\xCF\x11\xE0'):
        return 'doc_ole'
    return 'unknown'


def overlay_pdf(base_pdf_bytes: bytes, annotations: Dict[str, Any]) -> bytes:
    """Overlay annotations on PDF"""
    try:
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        # naive placement: if schema has bbox, respect it; else write top-left
        y_start = 720
        y_offset = 20
        for idx, (field_id, value) in enumerate(annotations.items()):
            # default position with spacing
            x, y = 72, y_start - (idx * y_offset)
            can.drawString(x, y, f"{field_id}: {value}")
        can.save()
        packet.seek(0)

        overlay_reader = PdfReader(packet)
        base_reader = PdfReader(BytesIO(base_pdf_bytes))
        writer = PdfWriter()
        for i, page in enumerate(base_reader.pages):
            page_to_merge = overlay_reader.pages[0] if len(overlay_reader.pages) > 0 else None
            if page_to_merge:
                page.merge_page(page_to_merge)
            writer.add_page(page)
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
    
    # Title
    can.setFont("Helvetica-Bold", 16)
    can.drawString(72, 750, "Biểu mẫu đã điền")
    can.setFont("Helvetica", 12)
    
    # Answers
    y_start = 700
    y_offset = 25
    for idx, (field_id, value) in enumerate(answers.items()):
        y = y_start - (idx * y_offset)
        if y < 50:  # New page if needed
            can.showPage()
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
            filled = overlay_pdf(file_bytes, answers)
            return StreamingResponse(BytesIO(filled), media_type="application/pdf")
        except Exception as e:
            # If PDF overlay fails, create new PDF
            filled = create_pdf_from_answers(answers)
            return StreamingResponse(BytesIO(filled), media_type="application/pdf")
    else:
        # For non-PDF files (DOCX, DOC, images), create a new PDF with answers
        filled = create_pdf_from_answers(answers)
        return StreamingResponse(BytesIO(filled), media_type="application/pdf")


