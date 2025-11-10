import json
import logging
import os
import subprocess
import tempfile
from io import BytesIO
from typing import Any, Dict, List, Optional

import boto3
from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from openai import OpenAI  # type: ignore
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

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


class ValidationResponse(BaseModel):
    isValid: bool
    message: Optional[str] = None
    needsConfirmation: bool = False


class NextQuestionResponse(BaseModel):
    nextQuestion: Optional[Question] = None
    missingFields: List[str] = []
    done: bool = False
    validation: Optional[ValidationResponse] = None  # Validation result for last answer


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
        db = (
            client.get_default_database()
            if "/" in MONGODB_URI.split("mongodb://")[-1]
            else client["forms"]
        )
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
        aggregate_all_forms_statistics,
        aggregate_form_statistics,
        get_timeseries_data,
        upsert_gold_data,
    )
except ImportError:
    from gold_aggregator import (
        aggregate_all_forms_statistics,
        aggregate_form_statistics,
        get_timeseries_data,
        upsert_gold_data,
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
    return {
        "status": "success",
        "message": f"Gold data refreshed for {form_id or 'all forms'}",
    }


# Minimal OpenAI integration (JSON response) — logic placed inline for MVP


def _openai_client() -> Optional[OpenAI]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _make_friendly_question(field: Dict[str, Any]) -> str:
    """Generate a friendly question text from field metadata"""
    field_id = field.get("id", "")
    label = field.get("label", field_id)
    field_type = field.get("type", "text")

    # Handle compound fields (CCCD, address, etc.)
    if field_type == "compound":
        subfields = field.get("subfields", [])
        if not subfields:
            return f"Vui lòng cung cấp thông tin về {label.lower()}"

        # Build combined question for compound field
        prompts = [sf.get("prompt", sf.get("label", "")) for sf in subfields]
        prompt_list = (
            ", ".join(prompts[:-1]) + f" và {prompts[-1]}"
            if len(prompts) > 1
            else prompts[0]
        )

        return f"Vui lòng cung cấp thông tin {label}: {prompt_list}"

    # Vietnamese friendly question templates
    templates = {
        "email": "Vui lòng cho tôi biết địa chỉ email của bạn",
        "phone": "Bạn có thể cung cấp số điện thoại liên hệ không?",
        "tel": "Bạn có thể cung cấp số điện thoại liên hệ không?",
        "date": "Bạn có thể cho biết ngày tháng không?",
        "number": f"Vui lòng nhập {label.lower()}",
        "text": f"Vui lòng cho tôi biết {label.lower()} của bạn",
    }

    # Check if label contains common keywords
    label_lower = label.lower()

    if "email" in label_lower or "mail" in label_lower:
        return "Vui lòng cho tôi biết địa chỉ email của bạn"
    elif "phone" in label_lower or "điện thoại" in label_lower or "sdt" in label_lower:
        return "Bạn có thể cung cấp số điện thoại liên hệ không?"
    elif "date" in label_lower or "ngày" in label_lower:
        return f"Bạn có thể cho biết {label.lower()} không?"
    elif "name" in label_lower or "tên" in label_lower or "họ" in label_lower:
        return f"Vui lòng cho tôi biết {label.lower()} của bạn"
    elif (
        "address" in label_lower or "địa chỉ" in label_lower or "đia chi" in label_lower
    ):
        return f"Bạn có thể cung cấp {label.lower()} không?"
    elif "job" in label_lower or "nghề" in label_lower or "công việc" in label_lower:
        return f"Vui lòng cho biết {label.lower()} của bạn"
    else:
        # Use type-based template or generic
        if field_type in templates:
            return templates[field_type]
        else:
            return f"Vui lòng cung cấp thông tin về {label.lower()}"


async def _parse_compound_answer(field: Dict[str, Any], answer: str) -> Dict[str, Any]:
    """
    Parse free-form answer for compound fields (CCCD, address, etc.)
    Returns dict with parsed values and missing subfields.

    Example:
    - Input: "001234567890 cấp ngày 15/05/2020 tại Hà Nội"
    - Output: {
        "parsed": {"so": "001234567890", "cap_ngay": "15/05/2020", "cap_tai": "Hà Nội"},
        "missing": [],
        "needs_clarification": False
      }
    """
    client = _openai_client()

    # Fallback if no OpenAI: just store as single text value
    if client is None:
        return {
            "parsed": {field.get("id"): answer},
            "missing": [],
            "needs_clarification": False,
        }

    subfields = field.get("subfields", [])
    if not subfields:
        return {
            "parsed": {field.get("id"): answer},
            "missing": [],
            "needs_clarification": False,
        }

    # Build prompt to parse answer into subfields
    subfield_descriptions = [
        f"- {sf['id']}: {sf.get('prompt', sf.get('label', ''))}" for sf in subfields
    ]
    subfield_list = "\n".join(subfield_descriptions)

    system_prompt = """Bạn là trợ lý phân tích câu trả lời cho các trường thông tin nhóm (compound fields).
Nhiệm vụ: Trích xuất thông tin từ câu trả lời tự do của người dùng và phân loại vào các trường con.

Trả về JSON với format:
{
  "parsed": {
    "subfield_id_1": "giá trị",
    "subfield_id_2": "giá trị",
    ...
  },
  "missing": ["subfield_id của các trường thiếu"],
  "needs_clarification": true/false (nếu câu trả lời không rõ ràng)
}

Lưu ý:
- Nếu người dùng chỉ cung cấp 1 phần thông tin, trích xuất phần đó và đánh dấu các phần còn lại là missing
- Nếu câu trả lời mơ hồ, set needs_clarification=true
- Trả về null cho các trường không có trong câu trả lời"""

    user_prompt = f"""Trường thông tin: {field.get('label')}

Các trường con cần trích xuất:
{subfield_list}

Câu trả lời của người dùng: {answer}

Hãy phân tích và trích xuất thông tin."""

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        # Validate result structure
        if not isinstance(result.get("parsed"), dict):
            result["parsed"] = {}
        if not isinstance(result.get("missing"), list):
            result["missing"] = [sf["id"] for sf in subfields]
        if "needs_clarification" not in result:
            result["needs_clarification"] = False

        return result

    except Exception as e:
        print(f"[compound_parse] OpenAI parse error: {e}")
        # Fallback: store as single value, mark all subfields as missing
        return {
            "parsed": {field.get("id"): answer},
            "missing": [sf["id"] for sf in subfields],
            "needs_clarification": True,
        }


async def _validate_answer_with_openai(
    question: str, answer: Any, field_type: str
) -> ValidationResponse:
    """Validate if the answer is appropriate for the question using OpenAI"""
    client = _openai_client()

    # If no OpenAI available, skip validation
    if client is None:
        return ValidationResponse(isValid=True, needsConfirmation=False)

    # Basic validation - empty answers should be handled by skip logic, not here
    answer_str = str(answer).strip()
    if not answer_str or len(answer_str) < 1:
        # Empty answer - let it pass through, will be handled as skip
        return ValidationResponse(isValid=True, needsConfirmation=False)

    try:
        system_prompt = """Bạn là trợ lý kiểm tra độ phù hợp của câu trả lời với câu hỏi trong biểu mẫu.
Nhiệm vụ: Xác định câu trả lời có phù hợp với câu hỏi không.

Trả về JSON với format:
{
  "isValid": true/false,
  "message": "lý do nếu không hợp lệ hoặc cần xác nhận",
  "needsConfirmation": true/false
}

Tiêu chí:
- isValid=false: Câu trả lời hoàn toàn không liên quan, sai định dạng nghiêm trọng (vd: "abc" cho số điện thoại)
- isValid=true, needsConfirmation=true: Câu trả lời có vẻ không chính xác nhưng có thể đúng (vd: số điện thoại thiếu số)
- isValid=true, needsConfirmation=false: Câu trả lời hợp lệ

Ví dụ:
- Hỏi email, trả "john@email.com" → valid, không cần confirm
- Hỏi số điện thoại, trả "0901234567" → valid, không cần confirm
- Hỏi số điện thoại, trả "090123" → valid nhưng cần confirm (thiếu số?)
- Hỏi email, trả "abc" → invalid
- Hỏi tên, trả "Nguyễn Văn A" → valid, không cần confirm"""

        user_prompt = f"""Câu hỏi: {question}
Loại trường: {field_type}
Câu trả lời: {answer_str}

Kiểm tra câu trả lời có hợp lệ không?"""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        if not response.choices or not response.choices[0].message.content:
            return ValidationResponse(isValid=True, needsConfirmation=False)

        import json

        result = json.loads(response.choices[0].message.content)

        return ValidationResponse(
            isValid=result.get("isValid", True),
            message=result.get("message"),
            needsConfirmation=result.get("needsConfirmation", False),
        )

    except Exception as e:
        print(f"[validation] OpenAI validation error: {e}")
        # On error, allow the answer (don't block user)
        return ValidationResponse(isValid=True, needsConfirmation=False)


async def generate_next_question(
    form_schema: Dict[str, Any], answers: Dict[str, Any], skipped: List[str] = []
) -> NextQuestionResponse:
    # If no OpenAI key, fallback to deterministic next unanswered field
    # Skip fields that are already answered OR explicitly skipped
    answered_or_skipped = set(list(answers.keys()) + skipped)
    unanswered = [
        f
        for f in form_schema.get("fields", [])
        if f.get("id") not in answered_or_skipped
    ]
    if not unanswered:
        return NextQuestionResponse(done=True)

    client = _openai_client()
    if client is None:
        # Use friendly question generator instead of raw label
        field = unanswered[0]
        friendly_text = _make_friendly_question(field)
        return NextQuestionResponse(
            nextQuestion=Question(
                id=field["id"],
                text=friendly_text,
                type=field.get("type", "text"),
                required=field.get("required", True),
            ),
            missingFields=[f["id"] for f in unanswered],
            done=False,
        )

    # With OpenAI: request JSON-structured next question with better prompt
    system = (
        "You are a friendly Vietnamese assistant helping users fill out forms. "
        "Generate natural, conversational questions in Vietnamese that are warm and helpful. "
        'Always return JSON with format: {"nextQuestion": {"id": "field_id", '
        '"text": "friendly question", "type": "text"}, "missingFields": [], "done": false} '
        "Make questions conversational, not just field labels."
    )

    user_prompt = f"""Based on this form schema and already provided answers, generate the next question:

Form title: {form_schema.get('title', 'Form')}
All fields: {[{"id": f["id"], "label": f.get("label"), "type": f.get("type")} for f in form_schema.get("fields", [])]}
Already answered: {list(answers.keys())}
Skipped fields (don't ask again): {skipped}

Generate a friendly, conversational Vietnamese question for the next unanswered field.
Example: Instead of "Phone", ask "Bạn có thể cho tôi biết số điện thoại của bạn không?"
IMPORTANT: Do NOT ask about fields that are already answered or skipped.
"""

    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,  # Increased for more natural language
        )
        content = resp.choices[0].message.content or "{}"
        import json

        data = json.loads(content)
        logger.info(f"[generate_next_question] OpenAI response: {data}")

        # ensure minimal shape
        if data.get("done"):
            return NextQuestionResponse(done=True)
        nq = data.get("nextQuestion") or {}

        question_text = str(nq.get("text", ""))
        logger.info(
            f"[generate_next_question] Generated question text: '{question_text}'"
        )

        return NextQuestionResponse(
            nextQuestion=Question(
                id=str(nq.get("id")),
                text=question_text,
                type=str(nq.get("type", "text")),
                options=nq.get("options"),
                required=bool(nq.get("required", True)),
            ),
            missingFields=[str(x) for x in data.get("missingFields", [])],
            done=bool(data.get("done", False)),
        )
    except Exception as e:
        # Fallback with friendly question generator
        logger.error(
            f"[generate_next_question] OpenAI error: {e}, using friendly fallback"
        )
        field = unanswered[0]
        friendly_text = _make_friendly_question(field)
        logger.info(
            f"[generate_next_question] Fallback question: '{friendly_text}' for field: {field}"
        )
        return NextQuestionResponse(
            nextQuestion=Question(
                id=field["id"],
                text=friendly_text,
                type=field.get("type", "text"),
                required=field.get("required", True),
            ),
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
async def start_session(
    payload: StartSessionRequest, request: Request, db=Depends(get_db)
):
    form = await db.forms.find_one({"id": payload.formId})
    logger.info(
        f"[start_session] formId={payload.formId}, fields_count={len(form.get('fields', [])) if form else 0}"
    )
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    # capture client info
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else None
    session = {
        "formId": payload.formId,
        "answers": {},
        "status": "active",
        "createdAt": int(
            os.getenv("CURRENT_TIME", str(int(__import__("time").time())))
        ),
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
async def next_question(
    session_id: str, payload: NextQuestionRequest, request: Request, db=Depends(get_db)
):
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

    validation_result = None

    # Validate answer if provided (and not empty/skip)
    if payload.lastAnswer is not None:
        answer_value = payload.lastAnswer.value

        # Check if user wants to skip (empty answer or special skip marker)
        is_skip = (
            not answer_value
            or str(answer_value).strip() == ""
            or str(answer_value).strip().lower() in ["skip", "bỏ qua"]
        )

        if is_skip:
            # User wants to skip this question - mark as skipped but don't save answer
            skipped_list = session.get("skipped", [])
            if payload.lastAnswer.fieldId not in skipped_list:
                skipped_list.append(payload.lastAnswer.fieldId)

            updates = {
                "skipped": skipped_list,
                "lastActiveAt": int(__import__("time").time()),
            }
            await db.sessions.update_one({"_id": session.get("_id")}, {"$set": updates})

            # Move to next question (use updated skipped list)
            resp = await generate_next_question(
                form_schema=form,
                answers=session.get("answers", {}),
                skipped=skipped_list,
            )
            return resp

        # Not skipping, validate the answer
        field = next(
            (
                f
                for f in form.get("fields", [])
                if f.get("id") == payload.lastAnswer.fieldId
            ),
            None,
        )

        if field:
            # Get the question text (try to find it from previous session state or generate it)
            question_text = _make_friendly_question(field)
            field_type = field.get("type", "text")

            # Handle compound fields differently
            if field_type == "compound":
                # Parse free-form answer into subfields
                parse_result = await _parse_compound_answer(field, answer_value)

                # Check if any critical info is missing
                if parse_result["missing"] or parse_result["needs_clarification"]:
                    # Build clarification message
                    missing_prompts = []
                    subfields = field.get("subfields", [])
                    for missing_id in parse_result["missing"]:
                        sf = next((s for s in subfields if s["id"] == missing_id), None)
                        if sf:
                            missing_prompts.append(sf.get("prompt", sf.get("label")))

                    if missing_prompts:
                        clarification_msg = (
                            f"Bạn chưa cung cấp: {', '.join(missing_prompts)}. "
                            "Vui lòng cung cấp đầy đủ thông tin."
                        )
                    else:
                        clarification_msg = (
                            "Thông tin bạn cung cấp chưa rõ ràng. "
                            "Vui lòng cung cấp lại đầy đủ hơn."
                        )

                    # Return validation error asking for complete info
                    validation_result = ValidationResponse(
                        isValid=False,
                        message=clarification_msg,
                        needsConfirmation=False,
                    )
                    resp = await generate_next_question(
                        form_schema=form,
                        answers=session.get("answers", {}),
                        skipped=session.get("skipped", []),
                    )
                    resp.validation = validation_result
                    return resp

                # All subfields parsed successfully - save as structured data
                # Store with compound field ID + subfield structure
                parsed_data = parse_result["parsed"]
                session.setdefault("answers", {})[
                    payload.lastAnswer.fieldId
                ] = parsed_data
                updates = {
                    "answers": session["answers"],
                    "lastActiveAt": int(__import__("time").time()),
                }
                await db.sessions.update_one(
                    {"_id": session.get("_id")},
                    {"$set": updates, "$inc": {"answerCount": 1}},
                )

                # Move to next question
                resp = await generate_next_question(
                    form_schema=form,
                    answers=session["answers"],
                    skipped=session.get("skipped", []),
                )
                return resp

            # Regular field - validate normally
            # Validate the answer
            validation_result = await _validate_answer_with_openai(
                question=question_text, answer=answer_value, field_type=field_type
            )

            # If validation failed completely, return error response with validation info
            if not validation_result.isValid:
                # Don't save the answer, return validation error
                resp = await generate_next_question(
                    form_schema=form,
                    answers=session.get("answers", {}),
                    skipped=session.get("skipped", []),
                )
                resp.validation = validation_result
                return resp

            # If needs confirmation, return current state with validation warning
            if validation_result.needsConfirmation:
                # Save the answer but ask for confirmation
                session.setdefault("answers", {})[
                    payload.lastAnswer.fieldId
                ] = answer_value
                updates = {
                    "answers": session["answers"],
                    "lastActiveAt": int(__import__("time").time()),
                }
                await db.sessions.update_one(
                    {"_id": session.get("_id")},
                    {"$set": updates, "$inc": {"answerCount": 1}},
                )
                # Return next question with validation warning
                resp = await generate_next_question(
                    form_schema=form,
                    answers=session["answers"],
                    skipped=session.get("skipped", []),
                )
                resp.validation = validation_result
                return resp

        # Answer is valid, save it
        session.setdefault("answers", {})[payload.lastAnswer.fieldId] = answer_value
        updates = {
            "answers": session["answers"],
            "lastActiveAt": int(__import__("time").time()),
        }
        await db.sessions.update_one(
            {"_id": session.get("_id")}, {"$set": updates, "$inc": {"answerCount": 1}}
        )

    resp = await generate_next_question(
        form_schema=form, answers=session["answers"], skipped=session.get("skipped", [])
    )
    if validation_result:
        resp.validation = validation_result
    return resp


# Minimal fill implementation (overlay stub)


# Register Unicode font for Vietnamese support
def _register_unicode_font():
    """Register a Unicode-compatible font for Vietnamese text"""
    # List of font paths to try (macOS, Linux, Windows)
    font_candidates = [
        # Linux (Debian/Ubuntu) - most common in Docker
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        # Windows
        "C:/Windows/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arialuni.ttf",
    ]

    # Try each font
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                font_name = "UnicodeFont"
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                print(f"✅ Registered font: {font_path}")
                return font_name
            except Exception as e:
                print(f"⚠️  Failed to register {font_path}: {e}")
                continue

    # Ultimate fallback: use Helvetica
    print("⚠️  No Unicode font found, using Helvetica (Vietnamese may show as boxes)")
    return "Helvetica"


# Try to register Unicode font at startup
UNICODE_FONT = _register_unicode_font()


def _detect_file_type(file_bytes: bytes) -> str:
    """Detect file type from magic bytes"""
    if file_bytes.startswith(b"%PDF"):
        return "pdf"
    if file_bytes.startswith(b"PK"):
        return "docx_or_zip"
    if file_bytes.startswith(b"\xD0\xCF\x11\xE0"):
        return "doc_ole"
    return "unknown"


def _convert_doc_to_pdf(doc_bytes: bytes, filename: str = "input.doc") -> bytes:
    """Convert DOC/DOCX to PDF using LibreOffice"""
    try:
        # Create temp directory for conversion
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write DOC to temp file
            input_ext = ".doc" if filename.endswith(".doc") else ".docx"
            input_path = os.path.join(tmpdir, f"input{input_ext}")
            with open(input_path, "wb") as f:
                f.write(doc_bytes)

            # Convert using LibreOffice headless
            # --headless: no GUI
            # --convert-to pdf: output format
            # --outdir: output directory
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
                timeout=30,  # 30s timeout
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


def overlay_pdf(
    base_pdf_bytes: bytes,
    annotations: Dict[str, Any],
    form_schema: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Overlay annotations on PDF - ALWAYS preserves original form"""
    try:
        base_reader = PdfReader(BytesIO(base_pdf_bytes))
        writer = PdfWriter()

        # Get page dimensions from first page
        first_page = base_reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)

        # Get image dimensions from bbox detection metadata (if available)
        bbox_detection = form_schema.get("bbox_detection", {}) if form_schema else {}
        image_width = bbox_detection.get("image_width")
        image_height = bbox_detection.get("image_height")

        # Get font info from metadata (for consistent rendering)
        font_info = bbox_detection.get("font_info", {})
        primary_font = font_info.get("primary_font", "Times-Roman")
        font_size = font_info.get("font_size", 12)

        # Map PDF font names to ReportLab/system fonts
        font_to_use = UNICODE_FONT  # Default to Unicode font
        print(f"[FONT DEBUG] bbox_detection font_info: {font_info}")
        print(f"[FONT DEBUG] primary_font: {primary_font}")
        if "times" in primary_font.lower() or "liberation" in primary_font.lower():
            # Try to use Times-like font
            try:
                # Check if LiberationSerif exists
                if os.path.exists(
                    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
                ):
                    pdfmetrics.registerFont(
                        TTFont(
                            "LiberationSerif",
                            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                        )
                    )
                    font_to_use = "LiberationSerif"
                    print(
                        f"[FONT DEBUG] ✅ Using LiberationSerif font (matches {primary_font})"
                    )
                    logger.info(f"Using LiberationSerif font (matches {primary_font})")
            except Exception as e:
                print(f"[FONT DEBUG] ❌ Could not load LiberationSerif: {e}")
                logger.warning(
                    f"Could not load LiberationSerif: {e}, using {UNICODE_FONT}"
                )

        print(f"[FONT DEBUG] Final font_to_use: {font_to_use}")
        logger.info(f"Overlay font: {font_to_use} (PDF original: {primary_font})")

        # Calculate scale factor from image coordinates to PDF coordinates
        if image_width and image_height:
            scale_x = page_width / image_width
            scale_y = page_height / image_height
            logger.info(
                f"Scaling bbox: image {image_width}x{image_height} → "
                f"PDF {page_width}x{page_height} "
                f"(scale {scale_x:.3f}x{scale_y:.3f})"
            )
        else:
            # No image dimensions - assume coordinates are already in PDF points
            scale_x = 1.0
            scale_y = 1.0
            logger.warning("No image dimensions in bbox_detection, using scale=1.0")

        # Create field position mapping from schema
        field_positions = {}
        if form_schema:
            for field in form_schema.get("fields", []):
                field_id = field.get("id")
                bbox = field.get("bbox")
                page_num = field.get("page", 1)
                if field_id and bbox:
                    field_positions[field_id] = {"bbox": bbox, "page": page_num}

        # Create overlay for each page
        pages_with_overlays = {}

        # Only create overlays if there are answers
        if not annotations:
            # No answers - return original PDF unchanged
            for page in base_reader.pages:
                writer.add_page(page)
            out_stream = BytesIO()
            writer.write(out_stream)
            out_stream.seek(0)
            return out_stream.read()

        # Check if we have valid bbox positions for ALL fields
        has_valid_positions = all(
            field_id in field_positions for field_id in annotations.keys()
        )

        if not has_valid_positions:
            # No bbox positions - add original pages + answer summary page
            logger.info("No bbox positions available, creating answer summary page")

            # Add all original pages
            for page in base_reader.pages:
                writer.add_page(page)

            # Create answer summary page
            summary_page = BytesIO()
            can = canvas.Canvas(summary_page, pagesize=(page_width, page_height))

            # Title
            can.setFont(UNICODE_FONT, 16)
            title_text = "Thông tin đã điền"
            can.drawString(72, page_height - 60, title_text)

            # Subtitle
            can.setFont(UNICODE_FONT, 10)
            can.drawString(
                72,
                page_height - 80,
                "(Vui lòng kiểm tra và điền vào form gốc bên trên)",
            )

            # Draw answers
            y = page_height - 120
            can.setFont(UNICODE_FONT, 11)

            for field_id, value in annotations.items():
                if not value or str(value).strip() == "":
                    continue

                # Find field label
                field_label = field_id
                if form_schema:
                    for field in form_schema.get("fields", []):
                        if field.get("id") == field_id:
                            field_label = field.get("label", field_id)
                            break

                # Draw label (bold-ish by using size 11)
                can.setFont(UNICODE_FONT, 11)
                can.drawString(72, y, f"• {field_label}:")
                y -= 18

                # Draw value (indented, size 10)
                can.setFont(UNICODE_FONT, 10)
                display_value = str(value)
                max_width = page_width - 144

                # Word wrap
                if can.stringWidth(display_value, UNICODE_FONT, 10) > max_width:
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

                    for line in lines:
                        can.drawString(90, y, line)
                        y -= 14
                else:
                    can.drawString(90, y, display_value)
                    y -= 14

                y -= 10  # Extra space between fields

                # New page if needed
                if y < 80:
                    can.showPage()
                    can.setFont(UNICODE_FONT, 11)
                    y = page_height - 60

            can.save()
            summary_page.seek(0)

            # Add summary page(s)
            summary_reader = PdfReader(summary_page)
            for page in summary_reader.pages:
                writer.add_page(page)

            out_stream = BytesIO()
            writer.write(out_stream)
            out_stream.seek(0)
            return out_stream.read()

        for field_id, value in annotations.items():
            # Skip empty values
            if not value or str(value).strip() == "":
                continue
            # Get field position if available
            if field_id in field_positions:
                pos = field_positions[field_id]
                page_num = pos["page"]
                bbox = pos["bbox"]  # {x, y, width, height} dict or [x, y, w, h] list

                # Handle both dict and list format
                if isinstance(bbox, dict):
                    x, y = bbox["x"], bbox["y"]
                    bbox_height = bbox.get("height", 20)  # Get height for Y adjustment
                else:
                    x, y = bbox[0], bbox[1]
                    bbox_height = bbox[3] if len(bbox) > 3 else 20

                # Scale from image coordinates to PDF coordinates
                x = x * scale_x
                y = y * scale_y
                bbox_height = bbox_height * scale_y

                # Convert image coordinates (top-left origin) to PDF coordinates (bottom-left origin)
                # PDF uses bottom-left as (0,0), image uses top-left as (0,0)
                # Add 70% bbox_height to account for text baseline (text positioned in lower part of bbox)
                y = (
                    page_height - y - (bbox_height * 0.7)
                )  # Flip Y axis and adjust for text baseline

                logger.info(
                    f"Drawing {field_id} at ({x:.1f}, {y:.1f}) on page "
                    f"{page_num} (scaled from image coords, "
                    f"bbox_height={bbox_height:.1f})"
                )

                use_label = False  # Don't show label when using bbox
            else:
                # Smart fallback: distribute fields vertically on first page
                page_num = 1
                idx = list(annotations.keys()).index(field_id)
                # Position from top with better spacing
                margin = 72  # 1 inch margin
                y_start = page_height - margin - 100  # Leave space for header
                y_offset = 50  # More spacing for label + value
                x = margin
                y = y_start - (idx * y_offset)
                use_label = True  # Show label in fallback mode

            # Ensure page overlay exists
            if page_num not in pages_with_overlays:
                pages_with_overlays[page_num] = BytesIO()
                pages_with_overlays[page_num].canvas = canvas.Canvas(
                    pages_with_overlays[page_num], pagesize=(page_width, page_height)
                )

            can = pages_with_overlays[page_num].canvas

            # Format value based on type
            display_value = str(value) if value else ""

            # If using fallback layout, show field label + value
            if use_label:
                # Find field label from schema
                field_label = field_id  # Default to field_id
                if form_schema:
                    for field in form_schema.get("fields", []):
                        if field.get("id") == field_id:
                            field_label = field.get("label", field_id)
                            break

                # Draw label in bold
                can.setFont(UNICODE_FONT, 11)
                can.drawString(x, y + 15, f"{field_label}:")

                # Draw value below label
                can.setFont(UNICODE_FONT, 10)
                y_value = y  # Value position
            else:
                # Bbox mode: only draw value with detected font
                can.setFont(font_to_use, int(font_size))
                can.setFillColorRGB(0, 0, 0)  # Black text
                y_value = y

                # Word wrap for long text
            max_width = page_width - x - 72  # 1 inch right margin
            if can.stringWidth(display_value, font_to_use, int(font_size)) > max_width:
                # Simple word wrap
                words = display_value.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if (
                        can.stringWidth(test_line, font_to_use, int(font_size))
                        <= max_width
                    ):
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)

                # Draw wrapped lines
                for i, line in enumerate(lines):
                    can.drawString(x, y_value - (i * 12), line)
            else:
                # Draw single line
                can.drawString(x, y_value, display_value)

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
        # If overlay fails, return ORIGINAL PDF unchanged to preserve form
        # This ensures users can still write by hand even if overlay fails
        logger.warning(f"PDF overlay failed: {e}, returning original PDF")
        return base_pdf_bytes


def create_pdf_from_answers(answers: Dict[str, Any]) -> bytes:
    """Create a new PDF with filled answers - FALLBACK ONLY"""
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Title - NO "Biểu mẫu đã điền" text to keep form valid
    can.setFont(UNICODE_FONT, 12)

    # Answers
    y_start = 750  # Start from top
    y_offset = 25
    for idx, (field_id, value) in enumerate(answers.items()):
        y = y_start - (idx * y_offset)
        if y < 50:  # New page if needed
            can.showPage()
            can.setFont(UNICODE_FONT, 12)
            y = 750
        # Display only value, not field_id to keep it clean
        can.drawString(72, y, str(value) if value else "")

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

    # Always try overlay_pdf - it handles DOC/DOCX conversion internally
    try:
        filled = overlay_pdf(file_bytes, answers, form)
        return StreamingResponse(BytesIO(filled), media_type="application/pdf")
    except Exception as e:
        logger.error(f"PDF overlay/conversion failed: {e}")
        # If everything fails, create new PDF
        filled = create_pdf_from_answers(answers)
        return StreamingResponse(BytesIO(filled), media_type="application/pdf")


# ============================================================================
# ADMIN: BBOX EDITOR ENDPOINTS
# ============================================================================


class BboxUpdate(BaseModel):
    field_id: str
    bbox: Dict[str, float]  # {x, y, width, height, page}


@app.get("/admin/forms/{form_id:path}/bbox-editor")
async def get_bbox_editor_data(form_id: str, db=Depends(get_db)):
    """
    Get form data for bbox editing
    Returns: form schema with fields, PDF URL, detected bbox positions
    """
    form = await db.forms.find_one({"id": form_id})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Return form schema + PDF access info
    return {
        "formId": form_id,
        "title": form.get("title", form_id),
        "fields": form.get("fields", []),
        "pages": form.get("pages", 1),
        "pdfUrl": f"/admin/forms/{form_id}/pdf",  # PDF download endpoint
        "bboxDetection": form.get("bbox_detection", {}),  # Auto-detected positions
    }


@app.get("/admin/forms/{form_id:path}/pdf")
async def get_form_pdf(form_id: str, db=Depends(get_db)):
    """
    Download form PDF for bbox editor
    """
    form = await db.forms.find_one({"id": form_id})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    bucket = form.get("source", {}).get("bucket")
    key = form.get("source", {}).get("key")
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="Form source not configured")

    try:
        # Get S3 endpoint (only set if not empty for LocalStack, omit for real AWS S3)
        s3_endpoint = os.getenv("S3_ENDPOINT_URL")
        s3_config = {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region_name": os.getenv("AWS_REGION", "us-east-1"),
        }
        if s3_endpoint:  # Only add endpoint_url if it's set (for LocalStack)
            s3_config["endpoint_url"] = s3_endpoint

        s3 = boto3.client("s3", **s3_config)
        obj = s3.get_object(Bucket=bucket, Key=key)
        file_bytes = obj["Body"].read()

        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={form_id.split('/')[-1]}"
            },
        )
    except Exception as e:
        logger.error(f"Failed to fetch PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch PDF: {str(e)}")


@app.get("/admin/forms/{form_id:path}/preview")
async def get_form_preview_image(form_id: str, page: int = 1, db=Depends(get_db)):
    """
    Convert PDF page to PNG image for canvas display
    """
    from pdf2image import convert_from_bytes

    form = await db.forms.find_one({"id": form_id})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    bucket = form.get("source", {}).get("bucket")
    key = form.get("source", {}).get("key")
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="Form source not configured")

    try:
        # Get S3 endpoint
        s3_endpoint = os.getenv("S3_ENDPOINT_URL")
        s3_config = {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            "region_name": os.getenv("AWS_REGION", "us-east-1"),
        }
        if s3_endpoint:
            s3_config["endpoint_url"] = s3_endpoint

        s3 = boto3.client("s3", **s3_config)
        obj = s3.get_object(Bucket=bucket, Key=key)
        pdf_bytes = obj["Body"].read()

        # Convert PDF page to image (DPI 300 to match OCR coordinates)
        images = convert_from_bytes(pdf_bytes, dpi=300, first_page=page, last_page=page)
        if not images:
            raise HTTPException(status_code=400, detail="Failed to render PDF page")

        # Convert PIL image to PNG bytes
        img_buffer = BytesIO()
        images[0].save(img_buffer, format="PNG")
        img_buffer.seek(0)

        return StreamingResponse(
            img_buffer,
            media_type="image/png",
            headers={"Content-Disposition": f"inline; filename=page{page}.png"},
        )
    except Exception as e:
        logger.error(f"Failed to generate preview: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate preview: {str(e)}"
        )


@app.post("/admin/forms/{form_id:path}/bbox")
async def update_field_bbox(
    form_id: str, updates: List[BboxUpdate], db=Depends(get_db)
):
    """
    Update bbox coordinates for form fields
    Accepts array of {field_id, bbox: {x, y, width, height, page}}
    """
    form = await db.forms.find_one({"id": form_id})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    fields = form.get("fields", [])

    # Apply bbox updates
    updated_count = 0
    for update in updates:
        for field in fields:
            if field["id"] == update.field_id:
                field["bbox"] = update.bbox
                updated_count += 1
                logger.info(f"Updated bbox for {update.field_id}: {update.bbox}")
                break

    # Save updated fields to MongoDB
    await db.forms.update_one({"id": form_id}, {"$set": {"fields": fields}})

    logger.info(f"Updated {updated_count}/{len(updates)} bbox positions for {form_id}")

    return {
        "success": True,
        "updated": updated_count,
        "total": len(updates),
        "fields": fields,
    }
