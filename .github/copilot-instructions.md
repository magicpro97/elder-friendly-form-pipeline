# Copilot Instructions for Elder-Friendly Form Pipeline

## Architecture Overview

This is a FastAPI-based conversational form assistant designed for elderly Vietnamese users. It uses **Redis for session persistence**, **OpenAI's API** for intelligent question generation and validation, with graceful fallbacks when API is unavailable.

**Core Flow**: Forms → Sessions (Redis) → Questions → Answers → Validation → Confirmation → Preview → PDF

## Key Components

### Session Management (Redis-based)
- `SessionManager` class handles all session operations with Redis backend
- Sessions stored with TTL (default 1 hour, configurable via `SESSION_TTL_SECONDS`)
- Session structure: `{"form_id", "answers", "field_idx", "questions", "stage", "pending"}`
- Stages: `"ask"` → `"confirm"` → `"review"`
- TTL automatically refreshed on each access
- Key pattern: `session:{session_id}`

### Form Resolution System
- Forms loaded from `forms/form_samples.json` into `FORM_INDEX` and `ALIASES`
- `pick_form()` matches user queries via: exact ID → aliases (substring) → title match
- Priority ensures flexible form selection with Vietnamese natural language

### Validation Pipeline
1. **Normalizers** (strip_spaces, collapse_whitespace, upper/lower/title_case)
2. **Validators** (regex, length, numeric_range, date_range)  
3. **AI Grader** (suspicious value detection with confirmation prompts)
4. **Field patterns** (top-level regex validation)

### OpenAI Integration with Retry Logic
- **Question Generation**: `SYSTEM_ASK` prompt + form metadata → structured questions
- **Suspicious Value Detection**: `SYSTEM_GRADER` validates user input
- **Preview Generation**: `SYSTEM_PREVIEW` creates formatted output
- All calls wrapped with `@retry` decorator (3 attempts, exponential backoff)
- Automatic fallback to basic functionality if OpenAI fails

## Critical Patterns

### Settings Management
All configuration via `pydantic.BaseSettings`:
```python
settings = Settings()  # Auto-loads from .env
settings.openai_api_key
settings.redis_host
settings.session_ttl_seconds
settings.rate_limit_per_minute
```

### Rate Limiting Pattern
All endpoints protected with customized limits:
```python
@app.post("/session/start")
@limiter.limit("10/minute")  # Most expensive endpoint
def start_session(request: Request, req: StartReq):
    ...

@app.get("/export_pdf")
@limiter.limit("10/minute")  # CPU-intensive
def export_pdf(request: Request, session_id: str):
    ...
```

### Vietnamese UI Text
All user-facing messages use respectful Vietnamese tone ("bác"/"cháu"):
```python
"Họ và tên của bác là gì ạ?"
"Cháu chưa nghe rõ, bác nhắc lại..."  
```

### Date Format Convention
- User input: `dd/mm/yyyy` (e.g., "12/10/1950")
- Validation: `datetime.strptime(value, "%d/%m/%Y")`
- Storage in validators: ISO format (`"min": "1930-01-01"`)

### Error Handling Pattern
```python
try:
    # Business logic
except HTTPException:
    raise  # Re-raise HTTP errors
except Exception as e:
    logger.error(f"Context: {e}", exc_info=True)
    raise HTTPException(500, "Vietnamese error message")
```

### Logging Conventions
```python
logger.info(f"Session {sid} created")  # User actions
logger.warning(f"OpenAI failed: {e}, using fallback")  # Degraded service
logger.error(f"Unexpected error: {e}", exc_info=True)  # Bugs
logger.debug(f"Session {sid}: Moving to next field")  # Verbose
```

## Development Workflow

### Running Tests
```bash
# Unit tests with coverage
pytest tests/ -v --cov=. --cov-report=term --cov-report=html

# Run specific test file
pytest tests/test_session.py -v

# Run with markers
pytest -m "not slow" -v
```

### Running with Docker (Production-like)
```bash
docker-compose up -d --build  # Start all services
docker-compose logs -f app     # View logs
docker-compose down -v         # Clean shutdown
```

### Running Locally (Development)
```bash
# Terminal 1: Redis
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 2: App
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Configure OPENAI_API_KEY, REDIS_HOST
uvicorn app:app --reload --port 8000
```

### Testing API Flow
1. `GET /forms` → list available forms
2. `POST /session/start` → creates Redis session, returns first question
3. `POST /answer` → validates + stores answer (may trigger AI confirmation)
4. `POST /confirm?yes=true` → confirm/reject suspicious values
5. `GET /preview` → AI-generated preview (cached in session)
6. `GET /export_pdf` → WeasyPrint PDF generation

Note: All endpoints have rate limiting (10-60 requests/minute based on resource intensity)

### Running CI/CD Pipeline
1. Add to `forms/form_samples.json` with Vietnamese `aliases`
2. Include `validators`, `normalizers` appropriate for field types
3. Test both with and without `OPENAI_API_KEY` (fallback mode)
4. Verify date fields use `dd/mm/yyyy` format

## External Dependencies

- **Redis**: Session persistence (required, fails fast if unavailable)
- **OpenAI**: AI features (optional, graceful degradation)
- **WeasyPrint**: PDF generation (requires system fonts for Vietnamese)
- **Jinja2**: Template rendering with autoescape
- **Tenacity**: Retry logic for OpenAI calls
- **Slowapi**: Rate limiting middleware
- **Pytest**: Testing framework with fakeredis for mocking

## Testing Strategy

### Test Structure
```
tests/
├── conftest.py         # Fixtures and mocks
├── test_forms.py       # Form matching logic
├── test_validation.py  # Field validation rules
├── test_session.py     # Redis session management
└── test_api.py         # API endpoint integration
```

### Key Testing Patterns
1. **Mock Redis**: Use `fakeredis.FakeRedis()` for session tests
2. **Mock OpenAI**: Patch `app.get_client()` to avoid API calls
3. **Fixtures**: Reuse `sample_form`, `sample_session` across tests
4. **Coverage**: Aim for >80% coverage on core logic

### Running Tests in CI
- GitHub Actions runs on every PR and push to main
- Coverage report uploaded to Codecov
- Docker image built and tested automatically
- Security scanning with Trivy

## Docker Architecture

```yaml
services:
  redis:   # Session storage, port 6379, persistent volume
  app:     # FastAPI, port 8000, depends on redis health check
```

**Volumes**: `redis_data` persists sessions across restarts
**Networks**: `form_network` for service communication
**Health checks**: Both services monitored for availability

## Common Pitfalls

1. **Session expiration**: Sessions auto-expire after TTL, handle 404 gracefully
2. **Redis connection**: App fails to start if Redis unreachable (by design)
3. **OpenAI quota**: Retry logic exhausted → falls back to basic mode
4. **PDF fonts**: WeasyPrint needs Vietnamese fonts (DejaVu Sans in Docker)
5. **Async blocking**: WeasyPrint runs in sync (consider `run_in_threadpool` for scale)
6. **Rate limiting**: Each endpoint has different limits, adjust per use case
7. **Test mocking**: Always use fakeredis for session tests, not real Redis
8. **CI/CD secrets**: OPENAI_API_KEY must be set in GitHub secrets for full testing

## Environment Variables Reference

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENAI_API_KEY` | None | No | OpenAI API key (fallback if missing) |
| `OPENAI_MODEL` | `o4-mini` | No | Model name for all AI calls |
| `REDIS_HOST` | `localhost` | Yes | Redis server hostname |
| `REDIS_PORT` | `6379` | No | Redis server port |
| `SESSION_TTL_SECONDS` | `3600` | No | Session lifetime (1 hour) |
| `PDF_TEMPLATE` | `generic_form.html` | No | Jinja2 template for PDF |

When OpenAI is unavailable, system generates template-based questions and basic previews without AI enhancement.