import os, re, uuid, json, datetime as dt, logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from jinja2 import Environment, FileSystemLoader, select_autoescape
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from io import BytesIO
import redis
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    openai_api_key: Optional[str] = None
    openai_model: str = "o4-mini"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    session_ttl_seconds: int = 3600  # 1 hour
    pdf_template: str = "generic_form.html"
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    
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
    """Get Redis client with connection pooling"""
    try:
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        client.ping()  # Test connection
        logger.info("Redis connection established")
        return client
    except redis.ConnectionError as e:
        logger.error(f"Redis connection failed: {e}")
        raise HTTPException(503, "Session storage không khả dụng. Vui lòng thử lại sau.")

# Skip Redis connection during testing
if os.getenv('TESTING') == 'true':
    import fakeredis
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    logger.info("Using FakeRedis for testing")
else:
    redis_client = get_redis_client()

# Session management
class SessionManager:
    """Manages sessions in Redis with TTL"""
    
    def __init__(self, redis_client: redis.Redis, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl
        self.prefix = "session:"
    
    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"
    
    def create(self, session_id: str, data: Dict[str, Any]) -> None:
        """Create new session with TTL"""
        key = self._key(session_id)
        self.redis.setex(key, self.ttl, json.dumps(data, ensure_ascii=False))
        logger.info(f"Created session {session_id} with TTL {self.ttl}s")
    
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        key = self._key(session_id)
        data = self.redis.get(key)
        if data:
            # Refresh TTL on access
            self.redis.expire(key, self.ttl)
            return json.loads(data)
        logger.warning(f"Session {session_id} not found or expired")
        return None
    
    def update(self, session_id: str, data: Dict[str, Any]) -> None:
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

session_manager = SessionManager(redis_client, settings.session_ttl_seconds)

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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def call_openai_with_retry(client, **kwargs):
    """Call OpenAI API with retry logic"""
    try:
        return client.responses.create(**kwargs)
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise

def load_forms():
    with open(FORMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["forms"]

FORMS = load_forms()
FORM_INDEX = {f["form_id"]: f for f in FORMS}
ALIASES = {}
for f in FORMS:
    for a in f.get("aliases", []):
        ALIASES[a.lower()] = f["form_id"]

def pick_form(text: str) -> Optional[str]:
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
  "type":"object","properties":{
    "questions":{"type":"array","items":{
      "type":"object","properties":{
        "name":{"type":"string"},
        "ask":{"type":"string"},
        "reprompt":{"type":"string"},
        "example":{"type":["string","null"]}
      },"required":["name","ask","reprompt"],"additionalProperties":False
    }}
  },"required":["questions"],"additionalProperties":False
}
SCHEMA_GRADER = {
  "type":"object","properties":{
    "is_suspicious":{"type":"boolean"},
    "confirm_question":{"type":["string","null"]},
    "hint":{"type":["string","null"]}
  },"required":["is_suspicious"],"additionalProperties":False
}
SCHEMA_PREVIEW = {
  "type":"object","properties":{
    "preview":{"type":"array","items":{"type":"object","properties":{
      "label":{"type":"string"},"value":{"type":"string"}
    },"required":["label","value"],"additionalProperties":False}},
    "prose":{"type":"string"}
  },"required":["preview","prose"],"additionalProperties":False
}

SYSTEM_ASK = "Bạn là trợ lý điền form cho người cao tuổi. Viết câu hỏi rất ngắn, 1 ý/1 câu, lịch sự, dùng từ giản dị, có ví dụ nếu có. Với trường không bắt buộc, nói 'có thể bỏ qua'. Trả về JSON đúng schema."
SYSTEM_GRADER = "Bạn đánh giá một giá trị trường form. Nếu giá trị hợp lệ nhưng bất thường (tuổi ngoài 18–90, địa chỉ quá ngắn, email miền lạ, số điện thoại có vẻ sai), đặt is_suspicious=true và tạo một câu hỏi xác nhận ngắn, lịch sự. Nếu có gợi ý sửa, ghi vào hint. Trả về JSON đúng schema."
SYSTEM_PREVIEW = "Từ các câu trả lời cuối cùng của người dùng, tạo preview (label gốc + value) và viết một đoạn văn hành chính mạch lạc, lịch sự để in ra PDF. Trả về JSON đúng schema."

app = FastAPI(title="Elder-Friendly Form Pipeline", version="1.0.0")

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Custom rate limit exceeded handler with Vietnamese message
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"Rate limit exceeded for {get_remote_address(request)}")
    return HTTPException(
        status_code=429,
        detail="Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau ít phút."
    )

class StartReq(BaseModel):
    form: Optional[str] = None
    query: Optional[str] = None

class TurnIn(BaseModel):
    session_id: str
    text: str

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
        fid = req.form or pick_form(req.query or "")
        if not fid or fid not in FORM_INDEX:
            logger.warning(f"Form not found: form={req.form}, query={req.query}")
            raise HTTPException(400, "Không xác định được form. Vui lòng nêu rõ tên form.")
        
        sid = str(uuid.uuid4())
        session_data = {
            "form_id": fid,
            "answers": {},
            "field_idx": 0,
            "questions": None,
            "stage": "ask",
            "pending": {}
        }
        
        form_meta = FORM_INDEX[fid]
        client = get_client()
        
        if client:
            try:
                logger.info(f"Generating questions with OpenAI for form {fid}")
                out = call_openai_with_retry(
                    client,
                    model=settings.openai_model,
                    input=[
                        {"role": "system", "content": SYSTEM_ASK},
                        {"role": "user", "content": f"Form metadata:\n```json\n{json.dumps(form_meta, ensure_ascii=False)}\n```"}
                    ],
                    text_format={"type":"json_schema","json_schema":SCHEMA_QUESTIONS,"strict":True}
                )
                questions = out.output_parsed["questions"]
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
        session_manager.create(sid, session_data)
        
        first = questions[0]
        logger.info(f"Session {sid} created for form {fid}")
        return {"session_id": sid, "form_id": fid, "ask": first["ask"], "field": first["name"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in start_session: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.")

def _validate_field(field, value):
    # normalizers
    for n in field.get("normalizers", []):
        if n == "strip_spaces": value = value.strip()
        if n == "collapse_whitespace": value = re.sub(r"\s+", " ", value).strip()
        if n == "upper": value = value.upper()
        if n == "lower": value = value.lower()
        if n == "title_case": value = value.title()
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
            try: num = float(value)
            except: return False, v.get("message") or "Cần số.", value
            mi, ma = float(v["min"]), float(v["max"])
            if not (mi <= num <= ma):
                return False, v.get("message") or f"Giá trị cần trong [{mi},{ma}].", value
        elif t == "date_range":
            try: d = dt.datetime.strptime(value, "%d/%m/%Y").date()
            except: return False, "Ngày nên là dd/mm/yyyy.", value
            min_d = dt.date.fromisoformat(v["min"]); max_d = dt.date.fromisoformat(v["max"])
            if not (min_d <= d <= max_d):
                return False, v.get("message") or "Ngày ngoài khoảng cho phép.", value
    if field.get("pattern") and not re.match(field["pattern"], value):
        return False, f'{field.get("label","Trường")} chưa đúng.', value
    return True, "", value

@app.post("/question/next")
@limiter.limit("60/minute")
def question_next(request: Request, inp: TurnIn):
    """Get next question for session"""
    try:
        st = session_manager.get(inp.session_id)
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
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.")

@app.post("/answer")
@limiter.limit("30/minute")
def answer_field(request: Request, inp: TurnIn):
    """Process answer for current field"""
    try:
        st = session_manager.get(inp.session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")
        
        fid = st["form_id"]
        form = FORM_INDEX[fid]
        idx = st["field_idx"]
        fields = form["fields"]
        
        if idx >= len(fields):
            return {"done": True, "message": "Đã đủ thông tin."}
        
        field = fields[idx]
        ok, msg, norm_val = _validate_field(field, inp.text.strip())
        
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
                    input=[{"role":"system","content": SYSTEM_GRADER},{"role":"user","content": content}],
                    text_format={"type":"json_schema","json_schema": SCHEMA_GRADER, "strict": True}
                )
                g = out.output_parsed
                if g.get("is_suspicious"):
                    st["pending"] = {"value": norm_val}
                    st["stage"] = "confirm"
                    session_manager.update(inp.session_id, st)
                    logger.info(f"Session {inp.session_id}: Suspicious value detected, requesting confirmation")
                    return {"ok": True, "confirm_required": True, "confirm_question": g.get("confirm_question"), "hint": g.get("hint")}
            except (RetryError, Exception) as e:
                logger.warning(f"OpenAI grader failed: {e}, skipping suspicious check")
        
        st["answers"][field["name"]] = norm_val
        st["field_idx"] += 1
        
        if st["field_idx"] >= len(fields):
            st["stage"] = "review"
            session_manager.update(inp.session_id, st)
            logger.info(f"Session {inp.session_id}: All fields completed")
            return {"ok": True, "done": True, "message": "Đã đủ thông tin. Bạn có thể xem trước."}
        
        session_manager.update(inp.session_id, st)
        nxt = st["questions"][st["field_idx"]]
        logger.debug(f"Session {inp.session_id}: Answer accepted, moving to next field")
        return {"ok": True, "ask": nxt["ask"], "field": nxt["name"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in answer_field: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.")

@app.post("/confirm")
@limiter.limit("30/minute")
def confirm(request: Request, inp: TurnIn, yes: bool = Query(True)):
    """Confirm or reject suspicious value"""
    try:
        st = session_manager.get(inp.session_id)
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
                session_manager.update(inp.session_id, st)
                logger.info(f"Session {inp.session_id}: Confirmed and completed all fields")
                return {"ok": True, "done": True, "message": "Đã đủ thông tin. Bạn có thể xem trước."}
            
            session_manager.update(inp.session_id, st)
            nxt = st["questions"][st["field_idx"]]
            logger.info(f"Session {inp.session_id}: Value confirmed, moving to next field")
            return {"ok": True, "ask": nxt["ask"], "field": nxt["name"]}
        else:
            st["pending"] = {}
            st["stage"] = "ask"
            session_manager.update(inp.session_id, st)
            q = st["questions"][idx]
            logger.info(f"Session {inp.session_id}: Value rejected, requesting re-entry")
            return {"ok": True, "ask": q["ask"], "field": q["name"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in confirm: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.")

@app.get("/preview")
@limiter.limit("20/minute")
def preview(request: Request, session_id: str):
    """Generate preview of form submission"""
    try:
        st = session_manager.get(session_id)
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
                    input=[{"role":"system","content": SYSTEM_PREVIEW},
                           {"role":"user","content": f"Form title: {form['title']}\nAnswers (JSON):\n```json\n{json.dumps(answers, ensure_ascii=False)}\n```"}],
                    text_format={"type":"json_schema","json_schema": SCHEMA_PREVIEW, "strict": True}
                )
                res = out.output_parsed
                st["preview"] = res["preview"]
                st["prose"] = res["prose"]
                logger.info(f"Session {session_id}: Preview generated via OpenAI")
            except (RetryError, Exception) as e:
                logger.warning(f"OpenAI preview generation failed: {e}, using fallback")
                client = None
        
        if not client:
            logger.info(f"Session {session_id}: Using fallback preview generation")
            st["preview"] = [{"label": f["label"], "value": answers.get(f["name"], "")} for f in form["fields"]]
            st["prose"] = " ".join([f"{f['label']}: {answers.get(f['name'],'')}" for f in form["fields"]])
        
        session_manager.update(session_id, st)
        return {"ok": True, "preview": st["preview"], "prose": st["prose"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in preview: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi. Vui lòng thử lại.")

@app.get("/export_pdf")
@limiter.limit("10/minute")
def export_pdf(request: Request, session_id: str):
    """Export form as PDF"""
    try:
        st = session_manager.get(session_id)
        if not st:
            raise HTTPException(404, "Session không tồn tại hoặc đã hết hạn.")
        
        fid = st["form_id"]
        form = FORM_INDEX[fid]
        
        if not st.get("preview"):
            st["preview"] = [{"label": f["label"], "value": st["answers"].get(f["name"], "")} for f in form["fields"]]
        
        tpl = env.get_template(settings.pdf_template)
        html = tpl.render(title=form["title"], preview=st["preview"])
        
        logger.info(f"Session {session_id}: Generating PDF for form {fid}")
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        
        logger.info(f"Session {session_id}: PDF generated successfully")
        return StreamingResponse(
            BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=form.pdf"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in export_pdf: {e}", exc_info=True)
        raise HTTPException(500, "Đã xảy ra lỗi khi tạo PDF. Vui lòng thử lại.")
