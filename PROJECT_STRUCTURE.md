# 📦 Project Structure Overview

```
fastapi_form_pipeline/
│
├── 📄 app.py                          # Main FastAPI application
│   ├── Settings (Pydantic BaseSettings)
│   ├── SessionManager (Redis-based)
│   ├── OpenAI integration with retry
│   └── API endpoints
│
├── 🗂️ forms/
│   └── form_samples.json              # Form definitions
│       ├── don_xin_viec              # Job application
│       ├── don_xin_nghi_phep         # Leave request
│       ├── giay_uy_quyen             # Power of attorney
│       ├── xac_nhan_cu_tru           # Residency cert
│       └── don_nhan_luong_huu        # Pension transfer
│
├── 🎨 templates/
│   ├── base.html                      # Base PDF template
│   └── generic_form.html              # Generic form layout
│
├── 📋 schemas/
│   └── form_schema.json               # JSON schema for form validation
│
├── 🐳 Docker Files
│   ├── Dockerfile                     # App container
│   ├── docker-compose.yml             # Multi-container setup
│   └── .dockerignore                  # Build exclusions
│
├── ⚙️ Configuration
│   ├── .env.example                   # Environment template
│   ├── .env                          # Your config (gitignored)
│   ├── .gitignore                    # Git exclusions
│   └── requirements.txt              # Python dependencies
│
├── 📚 Documentation
│   ├── README.md                      # Main documentation
│   ├── QUICKSTART.md                  # Quick start guide
│   ├── DEPLOYMENT.md                  # Deployment guide
│   ├── CHANGELOG.md                   # Version history
│   └── .github/
│       └── copilot-instructions.md    # AI coding guide
│
└── 🛠️ Development
    └── Makefile                       # Development commands
```

---

## 🔑 Key Files

### Core Application

- **`app.py`** (540 lines)
  - FastAPI app setup
  - SessionManager class (Redis)
  - OpenAI integration with retry
  - 7 API endpoints
  - Validation pipeline
  - Error handling & logging

### Data & Config

- **`forms/form_samples.json`**
  - 5 Vietnamese forms
  - Field definitions with validators
  - Vietnamese aliases for NLU

- **`.env`** (create from .env.example)
  - OpenAI API key
  - Redis connection
  - Session TTL
  - PDF template

### Docker

- **`docker-compose.yml`**
  - Redis service (persistent storage)
  - FastAPI app service
  - Health checks
  - Volume mounts

### Documentation

- **`README.md`** - Start here
- **`QUICKSTART.md`** - Get running in 1 minute
- **`DEPLOYMENT.md`** - Production deployment
- **`CHANGELOG.md`** - What changed

---

## 🔄 Data Flow

```
User Request
    ↓
FastAPI Endpoint
    ↓
SessionManager (Redis)
    ↓
Form Validation
    ↓
OpenAI API (with retry) ←→ Fallback
    ↓
Redis Session Update
    ↓
Response to User
```

---

## 🎯 API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/forms` | List available forms |
| POST | `/session/start` | Create new session |
| POST | `/question/next` | Get next question |
| POST | `/answer` | Submit answer |
| POST | `/confirm` | Confirm suspicious value |
| GET | `/preview` | Generate preview |
| GET | `/export_pdf` | Export as PDF |

---

## 🗄️ Redis Schema

```
Key: session:{uuid}
Value: {
  "form_id": "don_xin_viec",
  "answers": {"full_name": "...", ...},
  "field_idx": 2,
  "questions": [...],
  "stage": "ask",
  "pending": {},
  "preview": [...],
  "prose": "..."
}
TTL: 3600 seconds (1 hour)
```

---

## 📊 Form Schema

```json
{
  "form_id": "unique_id",
  "title": "Vietnamese title",
  "aliases": ["search", "terms"],
  "fields": [
    {
      "name": "field_name",
      "label": "Vietnamese label",
      "type": "string|date|email|phone",
      "required": true,
      "example": "sample",
      "validators": [...],
      "normalizers": [...],
      "pattern": "regex"
    }
  ]
}
```

---

## 🔧 Technology Stack

### Backend

- **FastAPI** 0.115.2 - Web framework
- **Uvicorn** 0.30.6 - ASGI server
- **Pydantic** 2.9.2 - Data validation

### Storage

- **Redis** 7-alpine - Session storage
- Python **redis** 5.0.1 - Client library

### AI

- **OpenAI** 1.51.0 - LLM integration
- **Tenacity** 8.2.3 - Retry logic

### PDF Generation

- **WeasyPrint** 61.2 - HTML to PDF
- **Jinja2** 3.1.4 - Templates

### DevOps

- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration

---

## 🚦 Health Checks

### Application Health

```bash
curl http://localhost:8000/forms
# Should return list of forms
```

### Redis Health

```bash
docker exec fastapi_form_redis redis-cli ping
# Should return: PONG
```

### Container Status

```bash
docker-compose ps
# Both services should be "Up (healthy)"
```

---

## 📈 Monitoring Points

- Session creation rate
- Session expiration rate
- OpenAI API success/failure
- Redis connection status
- Response times per endpoint
- Error rates (4xx, 5xx)

---

## 🔐 Security Features

✅ Environment-based secrets (`.env`)
✅ Redis session isolation
✅ Non-root Docker user
✅ Jinja2 autoescape (XSS protection)
✅ Pydantic validation (injection protection)
✅ Session TTL (limits exposure)
✅ HTTPS ready (via reverse proxy)

---

## 📏 Code Metrics

- **Total Lines**: ~540 (app.py)
- **Functions**: 15+
- **Classes**: 2 (Settings, SessionManager)
- **API Endpoints**: 7
- **Forms Supported**: 5
- **Dependencies**: 8 core packages

---

## 🎓 Learning Resources

- FastAPI Docs: <https://fastapi.tiangolo.com/>
- Redis Docs: <https://redis.io/docs/>
- OpenAI API: <https://platform.openai.com/docs/>
- WeasyPrint: <https://doc.courtbouillon.org/weasyprint/>
- Docker Compose: <https://docs.docker.com/compose/>

---

## 🤝 Contributing

1. Fork the repo
2. Create feature branch
3. Make changes
4. Test with `docker-compose up --build`
5. Submit pull request

---

## 📞 Getting Help

1. Check logs: `docker-compose logs -f app`
2. Review documentation in `docs/`
3. Check issues in CHANGELOG.md
4. Verify environment in `.env`
5. Test Redis: `redis-cli ping`
