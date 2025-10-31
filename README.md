# Elder-Friendly Form Pipeline

![CI/CD](https://github.com/magicpro97/elder-friendly-form-pipeline/workflows/Deploy%20to%20Railway/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-80%25-green)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/fastapi-0.115.2-009688)
![License](https://img.shields.io/badge/license-MIT-blue)

**Hệ thống hỗ trợ điền form qua hội thoại dành cho người cao tuổi Việt Nam**

🚂 **Deployed on Railway.app** | 🌐 **Live Demo**: [Coming soon]

---

## 🚀 Quick Deploy to Railway

### Option 1: One-Click Deploy (Fastest)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/elder-form)

### Option 2: Deploy via CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project (in project directory)
railway init

# Add Redis service
railway add --service redis

# Set environment variables
railway variables set OPENAI_API_KEY=sk-your-key-here
railway variables set OPENAI_MODEL=o4-mini

# Deploy!
railway up

# Get your app URL
railway status
```

### Option 3: Auto-Deploy via GitHub Actions

1. Fork this repository
2. Get Railway token:

   ```bash
   railway whoami
   # Copy token from ~/.railway/config.json
   ```

3. Add `RAILWAY_TOKEN` to GitHub repository secrets:
   - Go to: Settings → Secrets and variables → Actions
   - Add new secret: `RAILWAY_TOKEN`
4. Push to `main` branch → Auto-deploys! 🎉

---

## 🛠️ Local Development

### Quick Start với Docker (Khuyến nghị)

```bash
# 1. Clone và vào thư mục dự án
git clone https://github.com/magicpro97/elder-friendly-form-pipeline.git
cd elder-friendly-form-pipeline

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

### Run Locally (Development)

```bash
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
# Chỉnh sửa .env và thêm OPENAI_API_KEY

# Chạy Redis (nếu chưa có)
docker run -d -p 6379:6379 redis:7-alpine

# Chạy app
uvicorn app:app --reload --port 8000
```

---

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

### Environment Variables

Railway tự động cung cấp một số biến môi trường:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No | None | OpenAI API key (fallback mode if missing) |
| `OPENAI_MODEL` | No | o4-mini | OpenAI model name |
| `REDIS_URL` | Railway | Auto | Redis connection URL (auto-provided by Railway) |
| `REDIS_HOST` | Local | localhost | Redis hostname for local dev |
| `REDIS_PORT` | Local | 6379 | Redis port for local dev |
| `PORT` | Railway | 8000 | Application port (auto-provided by Railway) |
| `SESSION_TTL_SECONDS` | No | 3600 | Session lifetime (1 hour) |
| `RATE_LIMIT_PER_MINUTE` | No | 60 | Rate limit per minute |

**Railway Auto-Config:**

- `REDIS_URL`: Tự động set khi add Redis service
- `PORT`: Tự động set bởi Railway platform
- App tự động detect và sử dụng các biến này

**Local Development:**

```bash
cp .env.example .env
# Edit .env và set:
# - OPENAI_API_KEY=sk-your-key
# - REDIS_HOST=localhost
```

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests with coverage
pytest tests/ -v --cov=. --cov-report=term --cov-report=html

# Run specific test file
pytest tests/test_api.py -v

# Run linters
ruff check .
black --check .
```

---

## 📦 Tech Stack

- **Backend**: FastAPI 0.115.2, Python 3.11
- **Database**: Redis 7 (session storage)
- **AI**: OpenAI GPT-4o-mini (with graceful fallback)
- **PDF**: WeasyPrint (Vietnamese font support)
- **Deployment**: Railway.app (container-based)
- **CI/CD**: GitHub Actions (automated testing + deployment)
- **Frontend**: Vanilla JavaScript, CSS3, Web Speech API

---

## 📂 Project Structure

```
elder-friendly-form-pipeline/
├── app.py                 # Main FastAPI application
├── forms/
│   └── form_samples.json # Form definitions
├── templates/
│   ├── index.html        # Landing page
│   ├── base.html         # Base template
│   └── generic_form.html # PDF template
├── static/
│   ├── css/main.css      # Elder-friendly styles
│   └── js/app.js         # Frontend logic
├── tests/                # Test suite
├── .github/
│   └── workflows/
│       └── railway-deploy.yml  # CI/CD pipeline
├── railway.toml          # Railway config
├── railway.json          # Railway template
├── Dockerfile            # Container definition
├── docker-compose.yml    # Local development
└── requirements.txt      # Python dependencies
```

---

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
