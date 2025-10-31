import datetime as dt
import json
import logging
import os
import re
import uuid
from io import BytesIO
from typing import Any

import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# OpenAI client (optional)
OPENAI_OK = True
try:
    from openai import OpenAI
except ImportError as e:
    logger.warning(f"OpenAI not available: {e}")
    OPENAI_OK = False

load_dotenv()


# Settings
class Settings(BaseSettings):
    openai_api_key: str | None = None
    openai_model: str = "o4-mini"

    # Redis configuration
    # Railway provides REDIS_URL in format redis://default:password@host:port
    redis_url: str | None = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    session_ttl_seconds: int = 3600  # 1 hour
    pdf_template: str = "generic_form.html"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # Port configuration (Railway provides PORT env var)
    port: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

BASE_DIR = os.path.dirname(__file__)
FORMS_PATH = os.path.join(BASE_DIR, "forms", "form_samples.json")

# Jinja2 environment
env = Environment(
    loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)


# Redis connection
def get_redis_client() -> redis.Redis:
    """Get Redis client with connection pooling.

    Supports both Railway (REDIS_URL) and local development (REDIS_HOST/PORT).
    """
    try:
        # Railway provides REDIS_URL environment variable
        if settings.redis_url:
            client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            logger.info(f"Connected to Redis via REDIS_URL: {settings.redis_url.split('@')[-1]}")
        else:
            # Local development with individual settings
            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            logger.info(f"Connected to Redis at {settings.redis_host}:{settings.redis_port}")

        # Don't test connection on startup - let it fail lazily
        # client.ping() would block app startup if Redis not ready
        return client
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        raise HTTPException(503, "Session storage không khả dụng. Vui lòng thử lại sau.") from e


# Initialize Redis client (lazy loading to avoid startup crashes)
redis_client = None


def get_redis():
    """Get or create Redis client (lazy initialization)"""
    global redis_client
    if redis_client is None:
        # Skip Redis connection during testing
        if os.getenv("TESTING") == "true":
            import fakeredis

            redis_client = fakeredis.FakeRedis(decode_responses=True)
            logger.info("Using FakeRedis for testing")
        else:
            redis_client = get_redis_client()
    return redis_client


# Session management
class SessionManager:
    """Manages sessions in Redis with TTL"""

    def __init__(self, redis_client: redis.Redis, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl
        self.prefix = "session:"

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def create(self, session_id: str, data: dict[str, Any]) -> None:
        """Create new session with TTL"""
        key = self._key(session_id)
        self.redis.setex(key, self.ttl, json.dumps(data, ensure_ascii=False))
        logger.info(f"Created session {session_id} with TTL {self.ttl}s")

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Get session data"""
        key = self._key(session_id)
        data = self.redis.get(key)
        if data:
            # Refresh TTL on access
            self.redis.expire(key, self.ttl)
            return json.loads(str(data))
        logger.warning(f"Session {session_id} not found or expired")
        return None

    def update(self, session_id: str, data: dict[str, Any]) -> None:
        """Update session data and refresh TTL"""
        key = self._key(session_id)
        if self.redis.exists(key):
            self.redis.setex(key, self.ttl, json.dumps(data, ensure_ascii=False))
            logger.debug(f"Updated session {session_id}")
        else:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

    def delete(self, session_id: str) -> None:
        """Delete session"""
        key = self._key(session_id)
        self.redis.delete(key)
        logger.info(f"Deleted session {session_id}")

    def extend_ttl(self, session_id: str) -> None:
        """Extend session TTL"""
        key = self._key(session_id)
        if self.redis.exists(key):
            self.redis.expire(key, self.ttl)


# Initialize session manager (will use lazy Redis client)
session_manager = None


def get_session_manager():
    """Get or create session manager (lazy initialization)"""
    global session_manager
    if session_manager is None:
        session_manager = SessionManager(get_redis(), settings.session_ttl_seconds)
    return session_manager


def get_client():
    """Get OpenAI client with error handling"""
    if not OPENAI_OK:
        logger.warning("OpenAI library not installed")
        return None
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured")
        return None
    try:
        return OpenAI(api_key=settings.openai_api_key)
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def call_openai_with_retry(client, **kwargs):
    """Call OpenAI API with retry logic"""
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise


def load_forms():
    with open(FORMS_PATH, encoding="utf-8") as f:
        return json.load(f)["forms"]


FORMS = load_forms()
FORM_INDEX = {f["form_id"]: f for f in FORMS}
ALIASES = {}
for f in FORMS:
    for a in f.get("aliases", []):
        ALIASES[a.lower()] = f["form_id"]


def pick_form(text: str) -> str | None:
    t = (text or "").strip().lower()
    if t in FORM_INDEX:
        return t
    for key, fid in ALIASES.items():
        if key in t:
            return fid
    for fid, meta in FORM_INDEX.items():
        if meta["title"].lower() in t:
            return fid
    return None


SCHEMA_QUESTIONS = {
    "name": "questions_response",
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "ask": {"type": "string"},
                    "reprompt": {"type": "string"},
                    "example": {"type": ["string", "null"]},
                },
                "required": ["name", "ask", "reprompt"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}
SCHEMA_GRADER = {
    "name": "grader_response",
    "type": "object",
    "properties": {
        "is_suspicious": {"type": "boolean"},
        "confirm_question": {"type": ["string", "null"]},
        "hint": {"type": ["string", "null"]},
    },
    "required": ["is_suspicious"],
    "additionalProperties": False,
}
SCHEMA_PREVIEW = {
    "name": "preview_response",
    "type": "object",
    "properties": {
        "preview": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                "required": ["label", "value"],
                "additionalProperties": False,
            },
        },
        "prose": {"type": "string"},
    },
    "required": ["preview", "prose"],
    "additionalProperties": False,
}

SYSTEM_ASK = "Bạn là trợ lý điền form cho người cao tuổi. Viết câu hỏi rất ngắn, 1 ý/1 câu, lịch sự, dùng từ giản dị, có ví dụ nếu có. Với trường không bắt buộc, nói 'có thể bỏ qua'. Trả về JSON đúng schema."
SYSTEM_GRADER = "Bạn đánh giá một giá trị trường form. Nếu giá trị hợp lệ nhưng bất thường (tuổi ngoài 18–90, địa chỉ quá ngắn, email miền lạ, số điện thoại có vẻ sai), đặt is_suspicious=true và tạo một câu hỏi xác nhận ngắn, lịch sự. Nếu có gợi ý sửa, ghi vào hint. Trả về JSON đúng schema."
SYSTEM_PREVIEW = "Từ các câu trả lời cuối cùng của người dùng, tạo preview (label gốc + value) và viết một đoạn văn hành chính mạch lạc, lịch sự để in ra PDF. Trả về JSON đúng schema."

app = FastAPI(title="Elder-Friendly Form Pipeline", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Jinja2 templates for HTML pages
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Add rate limiter to app state
app.state.limiter = limiter


# Custom rate limit exceeded handler with Vietnamese message
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"Rate limit exceeded for {get_remote_address(request)}")
    return HTTPException(status_code=429, detail="Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.")


class StartReq(BaseModel):
    form_query: str  # Accepts form_id, title, or alias


class AnswerReq(BaseModel):
    session_id: str
    answer: str


class TurnIn(BaseModel):
    session_id: str
    text: str


@app.get("/")
async def index(request: Request):
    """Serve the main web interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/forms")
@limiter.limit("30/minute")
def list_forms(request: Request):
    """List all available forms"""
    return {"forms": [{"form_id": f["form_id"], "title": f["title"]} for f in FORMS]}


@app.post("/session/start")
@limiter.limit("10/minute")
def start_session(request: Request, req: StartReq):
    """Start a new form session"""
    try:
        fid = pick_form(req.form_query)
        if not fid or fid not in FORM_INDEX:
            logger.warning(f"Form not found: query={req.form_query}")
            raise HTTPException(400, "Không xác định được form. Vui lòng nêu rõ tên form.")

        sid = str(uuid.uuid4())
        session_data = {"form_id": fid, "answers": {}, "field_idx": 0, "questions": None, "stage": "ask", "pending": {}}

        form_meta = FORM_INDEX[fid]
        client = get_client()

        if client:
            try:
                logger.info(f"Generating questions with OpenAI for form {fid}")
                out = call_openai_with_retry(
                    client,
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_ASK},
                        {
                            "role": "user",
                            "content": f"Form metadata:\n```json\n{json.dumps(form_meta, ensure_ascii=False)}\n```",
                        },
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": SCHEMA_QUESTIONS["name"], "schema": SCHEMA_QUESTIONS},
                    },
                )
                response_content = out.choices[0].message.content
                parsed_response = json.loads(response_content)
                questions = parsed_response["questions"]
                logger.info(f"Generated {len(questions)} questions via OpenAI")
            except (RetryError, Exception) as e:
                logger.error(f"OpenAI question generation failed: {e}, using fallback")
                client = None  # Fall back to default questions

        if not client:
            logger.info(f"Using fallback question generation for form {fid}")
            questions = []
            for f in form_meta["fields"]:
                ex = f.get("example")
                ex_part = f" (ví dụ: {ex})" if ex else ""
                ask = f'{f["label"]} của bác là gì ạ?{ex_part}'
                reprompt = f'Cháu chưa nghe rõ, bác nhắc lại {f["label"].lower()} giúp cháu nhé.'
                questions.append({"name": f["name"], "ask": ask, "reprompt": reprompt, "example": ex or None})

        session_data["questions"] = questions
        get_session_manager().create(sid, session_data)

        first = questions[0]
        first_field = form_meta["fields"][0]
        logger.info(f"Session {sid} created for form {fid}")
        return {
            "session_id": sid,
            "form_id": fid,
            "ask": first["ask"],
            "field": first["name"],
            "example": first.get("example"),
            "required": first_field.get("required", True),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in start_session: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.") from e


def _validate_field(field, value):
    # normalizers
    for n in field.get("normalizers", []):
        if n == "strip_spaces":
            value = value.strip()
        if n == "collapse_whitespace":
            value = re.sub(r"\s+", " ", value).strip()
        if n == "upper":
            value = value.upper()
        if n == "lower":
            value = value.lower()
        if n == "title_case":
            value = value.title()
    # validators
    for v in field.get("validators", []):
        t = v.get("type")
        if t == "regex":
            if not re.match(v["pattern"], value):
                return False, v.get("message") or "Dữ liệu chưa đúng định dạng.", value
        elif t == "length":
            mi, ma = int(v["min"]), int(v["max"])
            if not (mi <= len(value) <= ma):
                return False, v.get("message") or f"Độ dài cần {mi}–{ma} ký tự.", value
        elif t == "numeric_range":
            try:
                num = float(value)
            except (ValueError, TypeError):
                return False, v.get("message") or "Cần số.", value
            mi, ma = float(v["min"]), float(v["max"])
            if not (mi <= num <= ma):
                return False, v.get("message") or f"Giá trị cần trong [{mi}, {ma}].", value
        elif t == "date_range":
            try:
                d = dt.datetime.strptime(value, "%d/%m/%Y").date()
            except (ValueError, TypeError):
                return False, "Ngày nên là dd/mm/yyyy.", value
            min_d = dt.date.fromisoformat(v["min"])
            max_d = dt.date.fromisoformat(v["max"])
            if not (min_d <= d <= max_d):
                return False, v.get("message") or "Ngày ngoài khoảng cho phép.", value
    if field.get("pattern") and not re.match(field["pattern"], value):
        return False, f'{field.get("label", "Trường")} chưa đúng.', value
    return True, "", value


@app.post("/question/next")
@limiter.limit("60/minute")
def question_next(request: Request, inp: TurnIn):
    """Get next question for session"""
    try:
        st = get_session_manager().get(inp.session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]
        idx = st["field_idx"]
        fields = form["fields"]

        if idx >= len(fields):
            return {"done": True, "message": "Đã thu thập đủ thông tin. Bạn có thể xem trước."}

        q = st["questions"][idx]
        logger.debug(f"Session {inp.session_id}: Next question for field {q['name']}")
        return {"ask": q["ask"], "field": q["name"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in question_next: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.") from e


@app.post("/answer")
@limiter.limit("30/minute")
def answer_field(request: Request, inp: AnswerReq):
    """Process answer for current field"""
    try:
        st = get_session_manager().get(inp.session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]
        idx = st["field_idx"]
        fields = form["fields"]

        if idx >= len(fields):
            return {"done": True, "message": "Đã đủ thông tin."}

        field = fields[idx]
        answer_text = inp.answer.strip()

        # Allow skipping optional fields
        if not answer_text and not field.get("required", True):
            st["field_idx"] += 1

            if st["field_idx"] >= len(fields):
                st["stage"] = "review"
                get_session_manager().update(inp.session_id, st)
                logger.info(f"Session {inp.session_id}: All fields completed")
                return {"ok": True, "done": True, "message": "Đã đủ thông tin. Bạn có thể xem trước."}

            get_session_manager().update(inp.session_id, st)
            nxt = st["questions"][st["field_idx"]]
            logger.info(f"Session {inp.session_id}: Skipped optional field {field['name']}")
            return {"ok": True, "ask": nxt["ask"], "field": nxt["name"], "example": nxt.get("example")}

        ok, msg, norm_val = _validate_field(field, answer_text)

        if not ok:
            logger.info(f"Session {inp.session_id}: Validation failed for {field['name']}: {msg}")
            return {"ok": False, "message": msg}

        client = get_client()
        if client:
            try:
                content = f"Field: {field['name']} ({field['label']})\nValue: {norm_val}\nContext: {fid}"
                logger.debug(f"Session {inp.session_id}: Checking suspicious value with OpenAI")
                out = call_openai_with_retry(
                    client,
                    model=settings.openai_model,
                    messages=[{"role": "system", "content": SYSTEM_GRADER}, {"role": "user", "content": content}],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": SCHEMA_GRADER["name"], "schema": SCHEMA_GRADER},
                    },
                )
                response_content = out.choices[0].message.content
                g = json.loads(response_content)
                if g.get("is_suspicious"):
                    st["pending"] = {"value": norm_val}
                    st["stage"] = "confirm"
                    get_session_manager().update(inp.session_id, st)
                    logger.info(f"Session {inp.session_id}: Suspicious value detected, requesting confirmation")
                    return {
                        "ok": True,
                        "stage": "confirm",
                        "pending_value": norm_val,
                        "message": g.get("confirm_question") or f"Bác chắc chắn là '{norm_val}' chứ?",
                        "hint": g.get("hint"),
                    }
            except (RetryError, Exception) as e:
                logger.warning(f"OpenAI grader failed: {e}, skipping suspicious check")

        st["answers"][field["name"]] = norm_val
        st["field_idx"] += 1

        if st["field_idx"] >= len(fields):
            st["stage"] = "review"
            get_session_manager().update(inp.session_id, st)
            logger.info(f"Session {inp.session_id}: All fields completed")
            return {"ok": True, "done": True, "message": "Đã đủ thông tin. Bạn có thể xem trước."}

        get_session_manager().update(inp.session_id, st)
        nxt = st["questions"][st["field_idx"]]
        next_field = fields[st["field_idx"]]
        logger.debug(f"Session {inp.session_id}: Answer accepted, moving to next field")
        return {
            "ok": True,
            "ask": nxt["ask"],
            "field": nxt["name"],
            "example": nxt.get("example"),
            "required": next_field.get("required", True),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in answer_field: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.") from e


@app.post("/confirm")
@limiter.limit("30/minute")
def confirm(request: Request, session_id: str = Query(...), yes: bool = Query(True)):
    """Confirm or reject suspicious value"""
    try:
        st = get_session_manager().get(session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        if st.get("stage") != "confirm":
            raise HTTPException(400, "Không có mục nào cần xác nhận.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]
        idx = st["field_idx"]
        field = form["fields"][idx]

        if yes:
            st["answers"][field["name"]] = st["pending"]["value"]
            st["pending"] = {}
            st["stage"] = "ask"
            st["field_idx"] += 1

            if st["field_idx"] >= len(form["fields"]):
                st["stage"] = "review"
                get_session_manager().update(session_id, st)
                logger.info(f"Session {session_id}: Confirmed and completed all fields")
                return {"ok": True, "done": True, "message": "Đã đủ thông tin. Bạn có thể xem trước."}

            get_session_manager().update(session_id, st)
            nxt = st["questions"][st["field_idx"]]
            next_field = form["fields"][st["field_idx"]]
            logger.info(f"Session {session_id}: Value confirmed, moving to next field")
            return {
                "ok": True,
                "ask": nxt["ask"],
                "field": nxt["name"],
                "example": nxt.get("example"),
                "required": next_field.get("required", True),
            }
        else:
            st["pending"] = {}
            st["stage"] = "ask"
            get_session_manager().update(session_id, st)
            q = st["questions"][idx]
            logger.info(f"Session {session_id}: Value rejected, requesting re-entry")
            return {
                "ok": True,
                "ask": q["ask"],
                "field": q["name"],
                "example": q.get("example"),
                "required": field.get("required", True),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in confirm: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.") from e


@app.get("/preview")
@limiter.limit("20/minute")
def preview(request: Request, session_id: str):
    """Generate preview of form submission"""
    try:
        st = get_session_manager().get(session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]
        answers = st["answers"]

        missing = [f["label"] for f in form["fields"] if f.get("required") and f["name"] not in answers]
        if missing:
            logger.warning(f"Session {session_id}: Missing required fields: {missing}")
            return {"ok": False, "message": "Còn thiếu: " + ", ".join(missing)}

        client = get_client()
        if client:
            try:
                logger.info(f"Session {session_id}: Generating preview with OpenAI")
                out = call_openai_with_retry(
                    client,
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PREVIEW},
                        {
                            "role": "user",
                            "content": f"Form title: {form['title']}\nAnswers (JSON):\n```json\n{json.dumps(answers, ensure_ascii=False)}\n```",
                        },
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": SCHEMA_PREVIEW["name"], "schema": SCHEMA_PREVIEW},
                    },
                )
                response_content = out.choices[0].message.content
                res = json.loads(response_content)
                st["preview"] = res["preview"]
                st["prose"] = res["prose"]
                logger.info(f"Session {session_id}: Preview generated via OpenAI")
            except (RetryError, Exception) as e:
                logger.warning(f"OpenAI preview generation failed: {e}, using fallback")
                client = None

        if not client:
            logger.info(f"Session {session_id}: Using fallback preview generation")
            st["preview"] = [{"label": f["label"], "value": answers.get(f["name"], "")} for f in form["fields"]]
            st["prose"] = " ".join([f"{f['label']}: {answers.get(f['name'], '')}" for f in form["fields"]])

        get_session_manager().update(session_id, st)
        return {"ok": True, "preview": st["preview"], "prose": st["prose"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in preview: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.") from e


@app.get("/export_pdf")
@limiter.limit("10/minute")
def export_pdf(request: Request, session_id: str):
    """Export form as PDF"""
    try:
        st = get_session_manager().get(session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]

        if not st.get("preview"):
            st["preview"] = [{"label": f["label"], "value": st["answers"].get(f["name"], "")} for f in form["fields"]]

        tpl = env.get_template(settings.pdf_template)
        html = tpl.render(title=form["title"], preview=st["preview"], style=form.get("style", {}))

        logger.info(f"Session {session_id}: Generating PDF for form {fid}")
        from weasyprint import HTML

        pdf = HTML(string=html).write_pdf()

        if not pdf:
            raise HTTPException(500, "Không thể tạo PDF.")

        logger.info(f"Session {session_id}: PDF generated successfully")
        return StreamingResponse(
            BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=form.pdf"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in export_pdf: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi khi tạo PDF. Vui lòng thử lại.") from e
