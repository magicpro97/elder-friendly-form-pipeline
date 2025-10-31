# Elder-Friendly Form Pipeline (FastAPI)

# Elder-Friendly Form Pipeline

![CI/CD](https://github.com/YOUR_USERNAME/fastapi_form_pipeline/workflows/CI/CD%20Pipeline/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-80%25-green)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.115.2-009688)
![License](https://img.shields.io/badge/license-MIT-blue)

**Hệ thống hỗ trợ điền form qua hội thoại dành cho người cao tuổi Việt Nam**


## 🚀 Quick Start với Docker (Khuyến nghị)

```bash
# 1. Clone và vào thư mục dự án
cd fastapi_form_pipeline

# 2. Tạo file .env từ template
cp .env.example .env
# Chỉnh sửa .env và thêm OPENAI_API_KEY của bạn

# 3. Chạy với Docker Compose
docker-compose up -d

# 4. Kiểm tra logs
docker-compose logs -f app

# 5. Test API
curl http://localhost:8000/forms
```

API sẽ chạy tại: `http://localhost:8000`

## 🛠️ Run locally (Development)

```bash
cd fastapi_form_pipeline

# Tạo virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Chỉnh sửa .env và thêm:
# - OPENAI_API_KEY
# - REDIS_HOST=localhost (hoặc chạy Redis container)

# Chạy Redis (nếu chưa có)
docker run -d -p 6379:6379 redis:7-alpine

# Chạy app
uvicorn app:app --reload --port 8000
```

## 📋 Endpoints

- `GET /forms` — Danh sách các form khả dụng
- `POST /session/start` — Bắt đầu session mới
  - `{ "form": "don_xin_viec" }` hoặc
  - `{ "query": "nghỉ phép" }`
- `POST /question/next` — Lấy câu hỏi tiếp theo
  - `{ "session_id": "..." }`
- `POST /answer` — Trả lời câu hỏi
  - `{ "session_id": "...", "text": "giá trị người dùng" }`
- `POST /confirm?yes=true|false` — Xác nhận giá trị nghi ngờ
  - `{ "session_id": "..." }`
- `GET /preview?session_id=...` — Xem trước form
- `GET /export_pdf?session_id=...` — Xuất PDF

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Client    │─────▶│  FastAPI App │─────▶│    Redis    │
│  (Browser)  │◀─────│   (Python)   │◀─────│  (Sessions) │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  OpenAI API  │
                     │  (Optional)  │
                     └──────────────┘
```

## Features

- 🗣️ **Conversational Interface**: Natural Vietnamese dialogue for elderly users
- 📋 **Multiple Form Types**: Job applications, leave requests, power of attorney, etc.
- 🤖 **AI-Powered**: OpenAI integration for intelligent question generation
- ✅ **Smart Validation**: Multi-stage validation (normalizers → validators → AI grader)
- 🔄 **Session Management**: Persistent sessions with Redis and TTL
- 📄 **PDF Export**: Professional form generation with WeasyPrint
- 🚦 **Rate Limiting**: Per-endpoint rate limits to prevent API abuse
- 🔄 **CI/CD Pipeline**: Automated testing and deployment with GitHub Actions
- 🐳 **Docker Ready**: Complete containerized deployment

## 🔧 Configuration

Tất cả config qua environment variables (xem `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_MODEL` | `gpt-4` | AI model name |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `SESSION_TTL_SECONDS` | `3600` | Session expiration time (1 hour) |
| `PDF_TEMPLATE` | `generic_form.html` | Jinja2 template for PDF |
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `60` | Default rate limit per minute |
| `RATE_LIMIT_PER_HOUR` | `1000` | Default rate limit per hour |

## 📦 Docker Commands

```bash
# Build và start
docker-compose up -d --build

# Stop
docker-compose down

# View logs
docker-compose logs -f app

# Restart app only
docker-compose restart app

# Clean up (bao gồm volumes)
docker-compose down -v
```

## 🧪 Testing

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests with coverage
pytest tests/ -v --cov=. --cov-report=term --cov-report=html

# View coverage report
# Open htmlcov/index.html in browser
```

### API Testing

```bash
# Test với curl
curl -X POST http://localhost:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"query": "xin việc"}'

# Response example:
{
  "session_id": "abc-123-...",
  "form_id": "don_xin_viec",
  "ask": "Họ và tên của bác là gì ạ?",
  "field": "full_name"
}
```

## � Rate Limiting

Each endpoint has customized rate limits based on resource intensity:

| Endpoint | Rate Limit | Reason |
|----------|-----------|---------|
| `GET /forms` | 30/min | Lightweight listing |
| `POST /session/start` | 10/min | OpenAI + session creation |
| `POST /question/next` | 60/min | Fast session read |
| `POST /answer` | 30/min | Validation + possible AI |
| `POST /confirm` | 30/min | Session update |
| `GET /preview` | 20/min | OpenAI call |
| `GET /export_pdf` | 10/min | CPU-intensive PDF generation |

Rate limits can be configured via environment variables or disabled entirely.

## 🔄 CI/CD Pipeline

GitHub Actions workflow automatically:

1. **Tests**: Runs pytest with coverage reporting
2. **Security**: Scans code with Trivy vulnerability scanner
3. **Build**: Creates Docker image with caching
4. **Deploy**: Pushes to container registry on main branch

See `.github/workflows/ci-cd.yml` for details.

## 📂 Project Structure

```
fastapi_form_pipeline/
├── app.py                    # Main FastAPI application
├── forms/
│   └── form_samples.json    # Form definitions
├── templates/
│   ├── base.html            # Base template
│   └── generic_form.html    # PDF template
├── schemas/
│   └── form_schema.json     # JSON schema
├── tests/                   # Test suite
│   ├── conftest.py          # Pytest fixtures
│   ├── test_forms.py        # Form matching tests
│   ├── test_validation.py   # Validation logic tests
│   ├── test_session.py      # Session management tests
│   └── test_api.py          # API endpoint tests
├── .github/
│   ├── workflows/
│   │   └── ci-cd.yml        # GitHub Actions pipeline
│   └── copilot-instructions.md  # AI agent guidance
├── Dockerfile               # Container image
├── docker-compose.yml       # Multi-container setup
└── requirements.txt         # Python dependencies
```

## �📝 Notes

- Nếu không set `OPENAI_API_KEY`, hệ thống dùng fallback (câu hỏi mặc định, preview đơn giản)
- Sessions tự động expire sau `SESSION_TTL_SECONDS` (mặc định 1 giờ)
- Redis data được persist trong Docker volume `redis_data`
- WeasyPrint cần system fonts để render tiếng Việt (đã cài trong Docker image)

## 🐛 Troubleshooting

**Redis connection failed:**
```bash
# Check Redis is running
docker-compose ps redis
# View Redis logs
docker-compose logs redis
```

**OpenAI API errors:**
- Check API key trong `.env`
- Check quota/billing tại OpenAI dashboard
- App sẽ fallback tự động nếu OpenAI fail

**PDF generation errors:**
- Ensure WeasyPrint dependencies installed
- Check template syntax trong `templates/`
