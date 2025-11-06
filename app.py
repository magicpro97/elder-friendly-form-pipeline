import datetime as dt
import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import redis
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from tenacity import RetryError

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
    openai_model: str = "gpt-4o-mini"  # Fast chat model (~2-5s), not reasoning model

    # Redis configuration
    # Railway provides REDIS_URL in format redis://default:password@host:port
    redis_url: str | None = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # PostgreSQL configuration
    # Railway provides DATABASE_URL in format postgresql://user:password@host:port/database
    database_url: str | None = None
    use_postgres: bool = True  # If False, fallback to JSON files

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
                max_connections=50,  # Connection pool size
                retry_on_timeout=True,
                health_check_interval=30,  # Health check every 30s
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
                max_connections=50,  # Connection pool size
                retry_on_timeout=True,
                health_check_interval=30,  # Health check every 30s
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
        # Use orjson for faster JSON serialization (falls back to standard json if not available)
        try:
            import orjson

            serialized = orjson.dumps(data).decode("utf-8")
        except ImportError:
            serialized = json.dumps(data, ensure_ascii=False)
        self.redis.setex(key, self.ttl, serialized)
        logger.info(f"Created session {session_id} with TTL {self.ttl}s")

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Get session data"""
        key = self._key(session_id)
        data = self.redis.get(key)
        if data:
            # Refresh TTL on access
            self.redis.expire(key, self.ttl)
            # Use orjson for faster JSON deserialization
            try:
                import orjson

                return orjson.loads(data)
            except ImportError:
                return json.loads(str(data))
        logger.warning(f"Session {session_id} not found or expired")
        return None

    def update(self, session_id: str, data: dict[str, Any]) -> None:
        """Update session data and refresh TTL"""
        key = self._key(session_id)
        if self.redis.exists(key):
            try:
                import orjson

                serialized = orjson.dumps(data).decode("utf-8")
            except ImportError:
                serialized = json.dumps(data, ensure_ascii=False)
            self.redis.setex(key, self.ttl, serialized)
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


logger = logging.getLogger(__name__)

# Singleton OpenAI client with connection pooling
_openai_client = None
_http_client = None
_executor = ThreadPoolExecutor(max_workers=4)  # Thread pool for blocking OpenAI calls


def get_client():
    """Get singleton OpenAI client with persistent connection pooling"""
    global _openai_client, _http_client

    if not OPENAI_OK:
        logger.warning("OpenAI library not installed")
        return None
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not configured")
        return None

    # Return existing client to reuse connections
    if _openai_client is not None:
        return _openai_client

    try:
        # Create persistent HTTP client with connection pooling (reused across all requests)
        _http_client = httpx.Client(
            timeout=10.0,  # 10s timeout (enough for gpt-4o-mini, fail fast)
            limits=httpx.Limits(
                max_connections=10,  # Max concurrent connections
                max_keepalive_connections=5,  # Keep-alive pool
                keepalive_expiry=60.0,  # Keep connections alive for 60s
            ),
        )
        _openai_client = OpenAI(
            api_key=settings.openai_api_key,
            http_client=_http_client,
            max_retries=0,  # No retries - fail fast
        )
        logger.info("Initialized singleton OpenAI client with connection pooling (no retries, 10s timeout)")
        return _openai_client
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        return None


def call_openai_with_retry(client, **kwargs):
    """Call OpenAI API without retry - fail fast (OpenAI client already has max_retries=0)"""
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise


def load_forms():
    with open(FORMS_PATH, encoding="utf-8") as f:
        return json.load(f)["forms"]


# Form loading with PostgreSQL fallback
def load_forms_from_source():
    """
    Load forms from PostgreSQL or fallback to JSON

    Returns:
        List of form dictionaries
    """
    # Try PostgreSQL first if enabled
    if settings.use_postgres and settings.database_url:
        try:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            forms = repo.get_all_forms()
            logger.info(f"Loaded {len(forms)} forms from PostgreSQL")
            return forms
        except Exception as e:
            logger.warning(f"Failed to load forms from PostgreSQL, falling back to JSON: {e}")

    # Fallback to JSON file
    logger.info("Loading forms from JSON file")
    return load_forms()


def get_form_index_from_source():
    """
    Build form index from PostgreSQL or JSON

    Returns:
        Dictionary of {form_id: form_data}
    """
    if settings.use_postgres and settings.database_url:
        try:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            return repo.get_form_index()
        except Exception:
            pass

    # Fallback
    forms = load_forms()
    return {f["form_id"]: f for f in forms}


def get_aliases_from_source():
    """
    Build aliases map from PostgreSQL or JSON

    Returns:
        Dictionary of {alias: form_id}
    """
    if settings.use_postgres and settings.database_url:
        try:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            return repo.get_aliases_map()
        except Exception:
            pass

    # Fallback
    forms = load_forms()
    aliases = {}
    for f in forms:
        for a in f.get("aliases", []):
            aliases[a.lower()] = f["form_id"]
    return aliases


FORMS = load_forms_from_source()
FORM_INDEX = get_form_index_from_source()
ALIASES = get_aliases_from_source()

# Cache for AI-generated questions (form_id -> questions)
QUESTIONS_CACHE: dict[str, list[dict]] = {}

# Compile regex patterns once for better performance
COMPILED_PATTERNS: dict[str, re.Pattern] = {}


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


def generate_fallback_questions(form_meta: dict) -> list[dict]:
    """Generate simple fallback questions without AI (fast)"""
    questions = []
    fields = form_meta["fields"]

    for i, f in enumerate(fields):
        ex = f.get("example")
        optional_note = "" if f.get("required", True) else " (không bắt buộc, bác có thể bỏ qua)."

        # Handle example - don't duplicate "Ví dụ:" prefix
        if ex:
            # Remove "Ví dụ:" prefix if it already exists in the example
            ex_clean = ex.replace("Ví dụ:", "").replace("Ví dụ :", "").strip()
        else:
            ex_clean = None

        label_lower = f.get("label", "").lower().strip()

        # CRITICAL: Validate label is not empty
        if not label_lower:
            logger.warning(f"Field {f.get('name', 'unknown')} has empty label, using field name as fallback")
            label_lower = f.get("name", "thông tin").replace("_", " ")

        # CRITICAL: Detect ambiguous labels that need context from previous field
        # Common patterns: "cấp ngày", "tại", "nơi cấp", "ngày cấp", "do", etc.
        ambiguous_patterns = ["cấp ngày", "tại", "nơi cấp", "ngày cấp", "do ", "của "]
        needs_context = any(pattern in label_lower for pattern in ambiguous_patterns)

        # Check if field name suggests it's related to previous field (issue_date after id_number)
        field_name = f.get("name", "")
        if i > 0 and ("issue" in field_name.lower() or "place" in field_name.lower() or needs_context):
            # Look back to find the main subject (not just immediate previous field)
            # For chains like: id_number → id_issue_date → id_issue_place
            subject = None
            for j in range(i - 1, max(i - 3, -1), -1):  # Look back up to 3 fields
                check_field = fields[j]
                check_label = check_field.get("label", "").lower().strip()
                check_name = check_field.get("name", "")

                # Stop if we hit another ambiguous field (don't chain ambiguous → ambiguous)
                if any(pattern in check_label for pattern in ambiguous_patterns):
                    continue

                # Extract subject from document/ID fields
                if any(x in check_label for x in ["cmnd", "cccd", "cmtnd"]):
                    subject = "CMND/CCCD"
                    break
                elif any(x in check_label for x in ["hộ chiếu", "passport"]):
                    subject = "hộ chiếu"
                    break
                elif any(x in check_label for x in ["giấy báo", "giấy chứng", "giấy khai"]):
                    # Extract document name after "giấy" (case-insensitive)
                    import re

                    parts = re.split(r"giấy\s+", check_label)
                    if len(parts) > 1:
                        doc_name = parts[1].strip().split(":")[0].strip().split("/")[0].strip()
                        subject = f"giấy {doc_name}" if doc_name else None
                    break
                elif "number" in check_name.lower() or "số" in check_label:
                    # Generic document number field
                    subject_text = check_label.replace("số", "").strip()
                    if subject_text and len(subject_text) < 30:  # Reasonable length
                        subject = subject_text.split("/")[0].strip()
                    break

            # Add context to ambiguous labels
            if subject and needs_context:
                if "cấp ngày" in label_lower or "ngày cấp" in label_lower:
                    label_lower = f"{subject} {label_lower}"
                elif label_lower == "tại" or label_lower.startswith("tại "):
                    label_lower = f"{subject} cấp tại"
                elif "nơi cấp" in label_lower:
                    label_lower = f"nơi cấp {subject}"

                logger.info(f"Added context to field {field_name}: '{f.get('label', '')}' → '{label_lower}'")

        # Do NOT inline example into the ask; provide it separately to avoid duplicate "Ví dụ:" when rendering
        ask = f"Bác cho cháu xin {label_lower} ạ.{optional_note}"
        reprompt = f"Cháu xin phép chưa nghe rõ, bác nhắc lại {label_lower} giúp cháu với ạ."
        # Store cleaned example without "Ví dụ:" prefix
        questions.append({"name": f["name"], "ask": ask, "reprompt": reprompt, "example": ex_clean})
    return questions


async def generate_questions_async(form_id: str, form_meta: dict, session_id: str) -> None:
    """Generate AI questions in background (runs in thread pool to avoid blocking)"""
    client = get_client()
    if not client:
        return

    try:
        logger.info(f"Background: Generating AI questions for form {form_id}, session {session_id}")

        # Run blocking OpenAI call in thread pool to avoid blocking event loop
        import asyncio

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(
            _executor,
            lambda: call_openai_with_retry(
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
            ),
        )

        response_content = out.choices[0].message.content
        parsed_response = json.loads(response_content)
        questions = parsed_response["questions"]

        # CRITICAL: Validate AI questions match form fields
        field_names = [f["name"] for f in form_meta["fields"]]

        # Check if number of questions matches number of fields
        if len(questions) != len(field_names):
            logger.warning(
                f"AI questions count ({len(questions)}) != fields count ({len(field_names)}), using fallback"
            )
            return

        # Validate each question has non-empty ask text
        for i, q in enumerate(questions):
            if not q.get("ask", "").strip():
                logger.warning(f"Question {i} for field {q.get('name', 'unknown')} has empty 'ask', using fallback")
                return

            # Validate question name matches field name
            if q.get("name") != field_names[i]:
                logger.warning(
                    f"Question name '{q.get('name')}' != field name '{field_names[i]}' at index {i}, using fallback"
                )
                return

        # Cache for future sessions
        QUESTIONS_CACHE[form_id] = questions
        logger.info(f"Background: Cached {len(questions)} AI questions for form {form_id}")

        # Update current session with AI questions
        st = get_session_manager().get(session_id)
        if st:
            st["questions"] = questions
            get_session_manager().update(session_id, st)
            logger.info(f"Background: Updated session {session_id} with AI questions")
    except Exception as e:
        logger.warning(f"Background AI question generation failed: {e}, session will use fallback")


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

SYSTEM_ASK = """
Bạn là trợ lý thân thiện giúp người cao tuổi điền form bằng tiếng Việt.

Yêu cầu về câu hỏi:
- Xưng hô "cháu" với "bác", giọng điệu ấm áp, kính trọng.
- Mỗi câu hỏi rất ngắn, chỉ một ý, dễ nghe (khoảng 8–16 từ).
- Dùng từ phổ thông, tránh thuật ngữ. Tránh câu ghép dài.
- Trường không bắt buộc: nói rõ "(không bắt buộc, bác có thể bỏ qua)".
- Nếu có ví dụ, thêm 1 ví dụ ngắn trong dấu "Ví dụ: …".
- Viết sẵn câu nhắc lại (reprompt) lịch sự, khích lệ, không đổ lỗi.

QUAN TRỌNG - Xử lý trường tối nghĩa:
- Nếu trường có label tối nghĩa (như "cấp ngày", "tại", "nơi cấp", "do"), thêm context từ trường trước.
- Ví dụ:
  * Sau "Số CMND": "cấp ngày" → "CMND cấp ngày nào ạ?"
  * Sau "Số CMND": "tại" → "CMND cấp tại đâu ạ?"
  * Sau "Giấy khai sinh": "cấp ngày" → "Giấy khai sinh cấp ngày nào ạ?"
- Luôn đảm bảo người nghe hiểu rõ đang hỏi về giấy tờ/thông tin nào.

Chỉ trả về JSON đúng schema "questions_response" (không thêm lời dẫn hoặc giải thích).
    """
SYSTEM_GRADER = """
Bạn đánh giá một giá trị của trường form.

Nguyên tắc:
- Nếu giá trị hợp lệ nhưng có dấu hiệu bất thường (ví dụ: tuổi < 18 hoặc > 90, địa chỉ quá ngắn, email miền lạ, số điện thoại sai định dạng/độ dài, họ tên chứa chữ số, ngày sinh ngoài khoảng), đặt is_suspicious=true.
- Tạo một câu hỏi xác nhận rất ngắn, lịch sự, dễ trả lời "đúng/sai"; không phỏng đoán.
- Nếu có thể, đưa ra một gợi ý sửa ngắn gọn, thực tế trong "hint".
- Không lặp lại toàn bộ hướng dẫn; không thêm ký tự trang trí.

Chỉ trả về JSON đúng schema "grader_response".
    """
SYSTEM_PREVIEW = """
Từ các câu trả lời đã hoàn tất, tạo:
1) preview: mảng các cặp {label gốc, value}, giữ nguyên thứ tự trường trong form.
2) prose: một đoạn văn hành chính ngắn, mạch lạc, kính trọng (không markdown), tổng hợp nội dung để in PDF.

Yêu cầu:
- Không bịa thêm thông tin, không suy diễn. Bỏ qua trường trống/không bắt buộc nếu người dùng chưa cung cấp.
- Giữ dấu tiếng Việt, dùng câu ngắn, rõ ý.

Chỉ trả về JSON đúng schema "preview_response".
    """

app = FastAPI(title="Elder-Friendly Form Pipeline", version="1.0.0")


# Middleware to handle reverse proxy (Railway, nginx, etc.)
class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Trust X-Forwarded-Proto and X-Forwarded-Host headers from reverse proxy"""

    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto for HTTPS detection
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto:
            request.scope["scheme"] = forwarded_proto

        # Trust X-Forwarded-Host for correct host
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_host:
            request.scope["server"] = (forwarded_host, None)

        return await call_next(request)


# Add proxy headers middleware FIRST (before other middlewares)
app.add_middleware(ProxyHeadersMiddleware)

# Add GZip compression middleware for better network performance
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

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
    response = templates.TemplateResponse("index.html", {"request": request})
    # Add cache control for HTML (short-lived)
    response.headers["Cache-Control"] = "public, max-age=300"  # 5 minutes
    return response


@app.get("/forms")
@limiter.limit("30/minute")
def list_forms(request: Request):
    """List all available forms"""
    return {"forms": [{"form_id": f["form_id"], "title": f["title"]} for f in FORMS]}


@app.post("/session/start")
@limiter.limit("10/minute")
def start_session(request: Request, req: StartReq, background_tasks: BackgroundTasks):
    """Start a new form session (optimized for fast response)"""
    try:
        fid = pick_form(req.form_query)
        if not fid or fid not in FORM_INDEX:
            logger.warning(f"Form not found: query={req.form_query}")
            raise HTTPException(400, "Không xác định được form. Vui lòng nêu rõ tên form.")

        sid = str(uuid.uuid4())
        form_meta = FORM_INDEX[fid]

        # Check cache first for instant response
        if fid in QUESTIONS_CACHE:
            questions = QUESTIONS_CACHE[fid]
            logger.info(f"Using cached questions for form {fid}")
        else:
            # Use fallback questions immediately for fast response
            questions = generate_fallback_questions(form_meta)
            logger.info(f"Using fallback questions for form {fid}, will upgrade in background")

            # Schedule AI generation in background (non-blocking)
            background_tasks.add_task(generate_questions_async, fid, form_meta, sid)

        session_data = {
            "form_id": fid,
            "answers": {},
            "field_idx": 0,
            "questions": questions,
            "stage": "ask",
            "pending": {},
        }

        get_session_manager().create(sid, session_data)

        first = questions[0]
        first_field = form_meta["fields"][0]
        total_fields = len(form_meta["fields"]) if form_meta.get("fields") else 0
        logger.info(f"Session {sid} created for form {fid}")
        return {
            "session_id": sid,
            "form_id": fid,
            "ask": first["ask"],
            "field": first["name"],
            "example": first.get("example"),
            "required": first_field.get("required", True),
            "current_index": 1,
            "total_fields": total_fields,
            "progress": 0,
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
            pattern = v["pattern"]
            # Use compiled pattern cache for better performance
            if pattern not in COMPILED_PATTERNS:
                COMPILED_PATTERNS[pattern] = re.compile(pattern)
            if not COMPILED_PATTERNS[pattern].match(value):
                return False, v.get("message") or "Dữ liệu chưa đúng định dạng.", value
        elif t == "length":
            mi, ma = int(v["min"]), int(v["max"])
            value_len = len(value)
            if not (mi <= value_len <= ma):
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
    # Check field pattern
    if field.get("pattern"):
        pattern = field["pattern"]
        if pattern not in COMPILED_PATTERNS:
            COMPILED_PATTERNS[pattern] = re.compile(pattern)
        if not COMPILED_PATTERNS[pattern].match(value):
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

        # CRITICAL: Validate question index
        if idx >= len(st["questions"]):
            logger.error(f"Session {inp.session_id}: field_idx {idx} >= questions length {len(st['questions'])}")
            st["questions"] = generate_fallback_questions(form)
            get_session_manager().update(inp.session_id, st)

        q = st["questions"][idx]

        # Validate question content
        if not q.get("ask", "").strip():
            field = fields[idx]
            label = field.get("label", field.get("name", "thông tin")).lower()
            q["ask"] = f"Bác cho cháu xin {label} ạ."
            logger.warning(f"Session {inp.session_id}: Fixed empty question at index {idx}")

        total = len(fields)
        current_index = idx + 1
        progress = int((idx / total) * 100) if total else 0
        logger.debug(f"Session {inp.session_id}: Next question for field {q['name']}")
        return {
            "ask": q["ask"],
            "field": q["name"],
            "example": q.get("example"),
            "required": fields[idx].get("required", True),
            "current_index": current_index,
            "total_fields": total,
            "progress": progress,
        }

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

            # CRITICAL: Validate question index before access
            if st["field_idx"] >= len(st["questions"]):
                logger.error(
                    f"Session {inp.session_id}: field_idx {st['field_idx']} >= questions length {len(st['questions'])}"
                )
                st["questions"] = generate_fallback_questions(form)
                get_session_manager().update(inp.session_id, st)

            nxt = st["questions"][st["field_idx"]]

            # Validate question content
            if not nxt.get("ask", "").strip():
                next_field = fields[st["field_idx"]]
                label = next_field.get("label", next_field.get("name", "thông tin")).lower()
                nxt["ask"] = f"Bác cho cháu xin {label} ạ."
                logger.warning(f"Session {inp.session_id}: Fixed empty question at index {st['field_idx']}")

            logger.info(f"Session {inp.session_id}: Skipped optional field {field['name']}")
            total = len(fields)
            current_index = st["field_idx"] + 1
            progress = int((st["field_idx"] / total) * 100) if total else 0
            return {
                "ok": True,
                "ask": nxt["ask"],
                "field": nxt["name"],
                "example": nxt.get("example"),
                "current_index": current_index,
                "total_fields": total,
                "progress": progress,
            }

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

        # CRITICAL: Validate question index is within bounds
        if st["field_idx"] >= len(st["questions"]):
            logger.error(
                f"Session {inp.session_id}: field_idx {st['field_idx']} >= questions length {len(st['questions'])}, "
                f"regenerating fallback questions"
            )
            # Regenerate fallback questions to match fields
            st["questions"] = generate_fallback_questions(form)
            get_session_manager().update(inp.session_id, st)

        nxt = st["questions"][st["field_idx"]]
        next_field = fields[st["field_idx"]]

        # Additional validation: ensure question has required fields
        if not nxt.get("ask", "").strip():
            logger.warning(
                f"Session {inp.session_id}: Question at index {st['field_idx']} has empty 'ask', "
                f"using field label: {next_field.get('label', next_field.get('name', 'thông tin'))}"
            )
            # Fallback to field label
            label = next_field.get("label", next_field.get("name", "thông tin")).lower()
            nxt["ask"] = f"Bác cho cháu xin {label} ạ."

        logger.debug(f"Session {inp.session_id}: Answer accepted, moving to next field")
        total = len(fields)
        current_index = st["field_idx"] + 1
        progress = int((st["field_idx"] / total) * 100) if total else 0
        return {
            "ok": True,
            "ask": nxt["ask"],
            "field": nxt["name"],
            "example": nxt.get("example"),
            "required": next_field.get("required", True),
            "current_index": current_index,
            "total_fields": total,
            "progress": progress,
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

            # CRITICAL: Validate question index
            if st["field_idx"] >= len(st["questions"]):
                logger.error(
                    f"Session {session_id}: field_idx {st['field_idx']} >= questions length {len(st['questions'])}"
                )
                st["questions"] = generate_fallback_questions(form)
                get_session_manager().update(session_id, st)

            nxt = st["questions"][st["field_idx"]]
            next_field = form["fields"][st["field_idx"]]

            # Validate question content
            if not nxt.get("ask", "").strip():
                label = next_field.get("label", next_field.get("name", "thông tin")).lower()
                nxt["ask"] = f"Bác cho cháu xin {label} ạ."
                logger.warning(f"Session {session_id}: Fixed empty question at index {st['field_idx']}")

            logger.info(f"Session {session_id}: Value confirmed, moving to next field")
            total = len(form["fields"])
            current_index = st["field_idx"] + 1
            progress = int((st["field_idx"] / total) * 100) if total else 0
            return {
                "ok": True,
                "ask": nxt["ask"],
                "field": nxt["name"],
                "example": nxt.get("example"),
                "required": next_field.get("required", True),
                "current_index": current_index,
                "total_fields": total,
                "progress": progress,
            }
        else:
            st["pending"] = {}
            st["stage"] = "ask"
            get_session_manager().update(session_id, st)

            # CRITICAL: Validate question index
            if idx >= len(st["questions"]):
                logger.error(f"Session {session_id}: idx {idx} >= questions length {len(st['questions'])}")
                st["questions"] = generate_fallback_questions(form)
                get_session_manager().update(session_id, st)

            q = st["questions"][idx]

            # Validate question content
            if not q.get("ask", "").strip():
                label = field.get("label", field.get("name", "thông tin")).lower()
                q["ask"] = f"Bác cho cháu xin {label} ạ."
                logger.warning(f"Session {session_id}: Fixed empty question at index {idx}")

            logger.info(f"Session {session_id}: Value rejected, requesting re-entry")
            total = len(form["fields"])
            current_index = idx + 1
            progress = int((idx / total) * 100) if total else 0
            return {
                "ok": True,
                "ask": q["ask"],
                "field": q["name"],
                "example": q.get("example"),
                "required": field.get("required", True),
                "current_index": current_index,
                "total_fields": total,
                "progress": progress,
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
    """Export form as PDF using original file template"""
    try:
        st = get_session_manager().get(session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")

        fid = st["form_id"]
        form = FORM_INDEX[fid]
        answers = st.get("answers", {})

        # Check if form has original file (crawler forms)
        original_file_path = form.get("metadata", {}).get("original_file_path")

        if original_file_path and Path(original_file_path).exists():
            # Use original file template with form_filler
            logger.info(f"Session {session_id}: Using original file template: {original_file_path}")

            try:
                from src.form_filler import fill_and_export

                # Fill and convert to PDF
                filled_pdf_path = fill_and_export(original_file_path, answers)

                # Read PDF content
                with open(filled_pdf_path, "rb") as f:
                    pdf_content = f.read()

                logger.info(f"Session {session_id}: PDF generated from original template")

                return StreamingResponse(
                    BytesIO(pdf_content),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={form['title']}.pdf"},
                )

            except Exception as e:
                logger.warning(f"Failed to use original template: {e}, falling back to generic template")
                # Fall through to generic template below

        # Fallback: Use generic HTML template (for manual forms or if original file fails)
        logger.info(f"Session {session_id}: Using generic HTML template")

        if not st.get("preview"):
            st["preview"] = [{"label": f["label"], "value": answers.get(f["name"], "")} for f in form["fields"]]

        tpl = env.get_template(settings.pdf_template)
        html = tpl.render(title=form["title"], preview=st["preview"], style=form.get("style", {}))

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


# =============================================================================
# Form Management API Endpoints
# =============================================================================


@app.get("/api/forms")
@limiter.limit("60/minute")
def list_forms_api(request: Request, source: str | None = None):
    """
    List all available forms

    Args:
        source: Optional filter by source ('manual' or 'crawler')

    Returns:
        JSON with forms list and metadata
    """
    try:
        if settings.use_postgres and settings.database_url:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            forms = repo.get_all_forms(source=source)
        else:
            # Fallback to in-memory FORMS
            if source:
                forms = [f for f in FORMS if f.get("source") == source]
            else:
                forms = FORMS

        return {"ok": True, "count": len(forms), "source_filter": source, "forms": forms}

    except Exception as e:
        logger.error(f"Failed to list forms: {e}", exc_info=True)
        raise HTTPException(500, "Không thể tải danh sách forms") from e


@app.get("/api/forms/search")
@limiter.limit("60/minute")
def search_forms_api(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    min_score: float = Query(0.3, ge=0.0, le=1.0),
    max_results: int = Query(10, ge=1, le=50),
):
    """
    Search forms with Vietnamese fuzzy matching

    Args:
        q: Search query
        min_score: Minimum relevance score (0.0-1.0)
        max_results: Maximum number of results (1-50)

    Returns:
        JSON with search results and relevance scores
    """
    try:
        if settings.use_postgres and settings.database_url:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            results = repo.search_forms(q, min_score, max_results)
        else:
            # Fallback to basic search using FORM_INDEX
            from src.form_search import FormSearch

            searcher = FormSearch()
            results = searcher.search(q, min_score, max_results)

        return {"ok": True, "query": q, "count": len(results), "results": results}

    except Exception as e:
        logger.error(f"Search failed for query '{q}': {e}", exc_info=True)
        raise HTTPException(500, "Tìm kiếm thất bại") from e


@app.get("/api/forms/{form_id}")
@limiter.limit("60/minute")
def get_form_api(request: Request, form_id: str):
    """
    Get detailed information about a specific form

    Args:
        form_id: Form ID to retrieve

    Returns:
        JSON with form details including fields
    """
    try:
        if settings.use_postgres and settings.database_url:
            from src.form_repository import get_form_repository

            repo = get_form_repository()
            form = repo.get_form_by_id(form_id)
        else:
            # Fallback to FORM_INDEX
            form = FORM_INDEX.get(form_id)

        if not form:
            raise HTTPException(404, f"Form '{form_id}' không tồn tại")

        return {"ok": True, "form": form}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get form {form_id}: {e}", exc_info=True)
        raise HTTPException(500, "Không thể tải thông tin form") from e


# =============================================================================
# Application Lifecycle
# =============================================================================


@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Application shutting down...")

    # Close PostgreSQL connection
    if settings.use_postgres and settings.database_url:
        try:
            from src.form_repository import close_repository

            close_repository()
            logger.info("Closed PostgreSQL connection")
        except Exception as e:
            logger.warning(f"Failed to close PostgreSQL: {e}")

    # Close OpenAI HTTP client (read-only access, no need for global statement)
    if _http_client:
        _http_client.close()
        logger.info("Closed OpenAI HTTP client")
