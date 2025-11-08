# Elder-Friendly Form Pipeline - AI Agent Instructions

## Architecture Overview

**Elder-friendly chatbot** that fills PDF/DOCX forms via conversational Vietnamese Q&A. Data flows: `crawler` → S3 → SQS → `worker` (OCR) → MongoDB → `api` (GPT-4o-mini) → `frontend` (Next.js chat).

### Service Boundaries
- **crawler**: Downloads forms from URLs, uploads to S3 (runs daily)
- **worker**: SQS consumer, OCRs documents, writes MongoDB `forms` collection with field metadata
- **api**: FastAPI REST, manages `sessions`, generates questions via OpenAI, overlays PDFs with ReportLab
- **frontend**: Next.js chat UI, conversational form filling with Vietnamese text support

### Data Flow
```
Internet → crawler → S3 → (S3 event) → SQS → worker → MongoDB (forms)
                                                         ↓
Frontend ← api (GPT-4o-mini Q&A) ← MongoDB (sessions + forms)
```

### Key Collections (MongoDB)
- `forms`: OCR-extracted fields with `{id, label, type, bbox, page}` metadata
- `sessions`: User answers `{formId, answers: {field_id: value}, client: {userAgent, ip, deviceType}}`
- `gold`: Aggregated analytics (completion rates, field popularity) - see `gold_aggregator.py`

## Critical Workflows

### Running Locally
```bash
# Start all services (uses LocalStack for S3/SQS)
docker compose --profile dev up -d --build

# Verify: API http://localhost:8000/healthz, Frontend http://localhost:3000

# Restart after code changes
docker compose restart api  # hot-reload enabled via volume mounts
```

### Vietnamese Font Rendering
**Critical**: PDFs MUST use Unicode fonts (DejaVuSans.ttf in Docker, Arial Unicode on macOS).  
Check `api/app/main.py:_register_unicode_font()` - tries 10+ font paths, falls back to Helvetica if missing.  
Docker: Install via `api/Dockerfile` → `apt-get install fonts-dejavu-core`

### UX Pattern: Friendly Questions
**Never show raw field labels** like "Phone" or "Email". Use `_make_friendly_question(field)` in `api/app/main.py`:
```python
# BAD: text=field["label"]  # "Phone"
# GOOD: text=_make_friendly_question(field)  # "Bạn có thể cung cấp số điện thoại liên hệ không?"
```
Templates in Vietnamese for email/phone/date/address/job. OpenAI prompt uses temperature=0.7 for natural tone.

### PDF Overlay Strategy
`overlay_pdf()` in `api/app/main.py`:
1. Try positioned overlay using `field.bbox` from OCR (x, y, width, height)
2. Fallback: vertical list layout if bbox missing
3. Emergency: `create_pdf_from_answers()` generates new PDF if overlay fails
4. Word-wrap logic for long Vietnamese text (max_width calculation)

## Testing & Debugging

### E2E Tests (Playwright)
```bash
cd e2e-tests && npm test  # headless, requires running services
npm run test:headed       # watch browser UI
npm run test:ui           # interactive debug mode
```
Tests in `e2e-tests/tests/`: form-filling.spec.ts (Vietnamese text validation), smoke.spec.ts (health checks), demo.spec.ts (step-by-step screenshots).

### Manual Testing Vietnamese UX
```bash
python3 api/test_ux_improvements.py  # compares old vs new question styles
```

### Debugging Worker (SQS Polling)
```bash
docker compose logs -f worker  # watch OCR processing
# Worker sleeps 10s if FORMS_QUEUE_URL unset, polls SQS every 10s otherwise
```

## Project-Specific Conventions

### Import Patterns (Worker/Crawler)
```python
# Dual import for Docker vs local execution
try:
    from .ocr import ocr_extract_fields  # package mode
except ImportError:
    from ocr import ocr_extract_fields   # direct run
```

### Session ID Handling (MongoDB)
API tries ObjectId first, falls back to string `sessionId` field:
```python
try:
    session = await db.sessions.find_one({"_id": ObjectId(session_id)})
except:
    session = await db.sessions.find_one({"sessionId": session_id})
```

### Environment Variables
- `OPENAI_API_KEY`: Required for GPT question generation (fallback: uses `_make_friendly_question()`)
- `S3_ENDPOINT_URL`: Set to `http://localstack:4566` for dev, omit for AWS
- `MONGODB_URI`: Default `mongodb://mongodb:27017/forms` in Docker

### Git Staging Rules
**CRITICAL: Always check changed files before committing!**

**Development Workflow (Build → Test → Commit → Push):**

**1. Make code changes**
```bash
# Edit files as needed
vim api/app/main.py frontend/pages/forms/[id].tsx
```

**2. Build affected services**
```bash
# Build only changed services
docker compose build api frontend worker

# Or rebuild all if uncertain
docker compose build
```

**3. Restart services**
```bash
# Restart specific services
docker compose restart api frontend worker

# Check logs for errors
docker compose logs api --tail=30
docker compose logs frontend --tail=30
```

**4. Test functionality**
```bash
# Health check
curl http://localhost:8000/healthz

# Test specific endpoints
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"formId": "raw/test.docx"}'

# For complex flows, write test script
cat > /tmp/test_feature.sh << 'EOF'
#!/bin/bash
# Test validation, form filling, etc.
EOF
chmod +x /tmp/test_feature.sh
/tmp/test_feature.sh
```

**5. Stage and commit (after successful testing)**
```bash
# 1. Review ALL changed files
git status
git diff

# 2. If too many files staged, RESET first
git reset

# 3. Stage ONLY essential files explicitly
git add api/app/main.py frontend/pages/forms/[id].tsx

# 4. Verify what's staged
git status

# 5. Commit with descriptive message
git commit -m "feat: add feature X with Y improvement

- Detail 1
- Detail 2
- Tested: scenario A → result B"

# 6. Push to remote
git push origin khang
```

**Only stage essential files**:
- ✅ Source code changes (`api/app/main.py`)
- ✅ Related tests (`api/test_ux_improvements.py`)
- ✅ Documentation updates (`README.md`, `.github/copilot-instructions.md`)
- ✅ Config changes (after careful review - NO secrets!)

**NEVER stage:**
- ❌ `.env`, `.env.bk` - Contains API keys/secrets
- ❌ `coverage.xml` - Test coverage artifacts
- ❌ `__pycache__/`, `*.pyc` - Python cache
- ❌ `node_modules/` - Dependencies
- ❌ `.pytest_cache/`, `htmlcov/` - Test artifacts
- ❌ `*.log` - Log files
- ❌ Binary files unless absolutely necessary

**Testing Examples:**

**API Validation Testing:**
```bash
# Test OpenAI answer validation
SESSION_ID=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"formId": "raw/form.docx"}' | jq -r '.sessionId')

# Test invalid answer (should reject)
curl -s -X POST "http://localhost:8000/sessions/$SESSION_ID/next-question" \
  -H "Content-Type: application/json" \
  -d '{"lastAnswer": {"fieldId": "phone", "value": "abc"}}' | jq '.validation'

# Expected: {"isValid": false, "message": "...", "needsConfirmation": false}

# Test valid answer (should accept)
curl -s -X POST "http://localhost:8000/sessions/$SESSION_ID/next-question" \
  -H "Content-Type: application/json" \
  -d '{"lastAnswer": {"fieldId": "phone", "value": "0901234567"}}' | jq '.validation'

# Expected: {"isValid": true, "message": "", "needsConfirmation": false}
```

**Frontend UI Testing:**
```bash
# Open browser to test
open http://localhost:3000

# Verify:
# - Form titles display correctly (not filenames)
# - Warning messages show yellow background
# - Error messages show red background
# - Vietnamese text renders properly
```

## Integration Points

### OpenAI API
`generate_next_question()` in `api/app/main.py`:
- Model: `gpt-4o-mini` (fast, cheap)
- Response format: `{"type": "json_object"}` for structured output
- System prompt emphasizes **conversational Vietnamese**, not raw labels
- Retry logic: catches exceptions, falls back to template-based questions

`_validate_answer_with_openai()` in `api/app/main.py`:
- Validates answer relevance to question using GPT-4o-mini
- Returns `ValidationResponse` with 3 states:
  * `isValid: false` → Reject answer, show error, ask again
  * `isValid: true, needsConfirmation: true` → Accept with warning
  * `isValid: true, needsConfirmation: false` → Fully valid
- Examples:
  * Phone "abc" → invalid, "090123" → needs confirmation, "0901234567" → valid
  * Email "abc" → invalid, "test@email.com" → valid

`_extract_title_from_text()` in `worker/app/ocr.py`:
- Extracts meaningful form titles from document content
- Falls back to OpenAI `_generate_title_with_openai()` if first line too short
- Result: "Đơn xin việc" instead of "topcv-1762617188.docx"

### S3 → SQS → Worker Pipeline
1. Crawler uploads to `s3://FORMS_BUCKET/raw/topcv-{timestamp}.docx`
2. S3 event triggers SQS message (configured via Terraform or LocalStack)
3. Worker polls SQS, downloads file, runs OCR, writes MongoDB
4. Important: Worker deletes SQS message only after successful MongoDB write

### Frontend → API Communication
Next.js uses `axios` with `NEXT_PUBLIC_API_BASE_URL`:
- `/sessions` POST: Start new form session
- `/sessions/{id}/next-question` POST: Submit answer, get next question with validation
  * Response includes `validation` field with `isValid`, `message`, `needsConfirmation`
  * Frontend handles 4 message types: `bot`, `user`, `warning` (yellow), `error` (red)
- `/sessions/{id}/fill` POST: Generate PDF with all answers
- Chat UI in `pages/forms/[id].tsx` stores messages in React state, scrolls to bottom automatically

## Key Files Reference
- `api/app/main.py`: Core FastAPI app, UX question generation, answer validation, PDF overlay
- `api/app/gold_aggregator.py`: Analytics aggregation (completion rates, field popularity)
- `worker/app/main.py`: SQS consumer, OCR orchestration, form title extraction
- `worker/app/ocr.py`: Multi-format OCR (PDF/DOCX/DOC/images), title extraction with OpenAI fallback
- `frontend/pages/forms/[id].tsx`: Conversational chat UI with Vietnamese support, validation message display
- `e2e-tests/playwright.config.ts`: Multi-browser E2E test config (Chromium, Firefox, WebKit, Mobile)
- `docker-compose.yml`: Full stack with hot-reload, LocalStack for dev

## Recommended MCP Tools

### For Development & Testing
- **playwright** (`@playwright/mcp`): Browser automation for E2E tests
  - Use for: Testing form flows, Vietnamese text rendering validation
  - Example: `npm run test:ui` in e2e-tests/

- **github/github-mcp-server**: GitHub integration for PRs, issues, code review
  - Use for: Creating issues, reviewing PRs, managing branches
  - Useful for: Tracking UX improvements, bug reports

### For Documentation & Analysis
- **context7** (`@upstash/context7-mcp`): Library documentation lookup
  - Use for: FastAPI, Next.js, ReportLab, PyPDF documentation
  - Example: Get latest FastAPI best practices, React hooks patterns

- **markitdown**: Convert documents to markdown
  - Use for: Converting PDF/DOCX forms to markdown for analysis
  - Useful for: Previewing form content before OCR

### For Image & OCR Tasks
- **imagesorcery-mcp**: Image processing and OCR
  - Use for: Analyzing form screenshots, testing Vietnamese font rendering
  - Example: `ocr` tool to extract text from UI screenshots
  - Critical for: Validating PDF overlay positioning (bbox coordinates)

### For Code Quality
- **memory** (`@modelcontextprotocol/server-memory`): Persistent context across sessions
  - Use for: Remembering project patterns, conventions, previous fixes
  - Useful for: Git staging rules, Vietnamese UX patterns

- **sequentialthinking** (`@modelcontextprotocol/server-sequential-thinking`): Complex problem-solving
  - Use for: Debugging multi-service issues, architectural decisions
  - Example: Tracing S3 → SQS → Worker → MongoDB pipeline issues

### NOT Recommended for This Project
- **huggingface**: Not needed (using OpenAI GPT-4o-mini directly)
- **filesystem**: Redundant (VS Code has native file access)

### Usage Examples
```bash
# Analyze form screenshot with OCR
Use imagesorcery-mcp to read screenshot → identify curt questions → suggest improvements

# Test Vietnamese text rendering
Use playwright to fill form → capture screenshot → verify diacritics

# Lookup ReportLab docs for PDF improvements
Use context7 to get "/reportlab/reportlab" docs on canvas text positioning

# Track UX improvement issue
Use github to create issue "Improve question friendliness" with Vietnamese examples
```
