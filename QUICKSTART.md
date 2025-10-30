# 🚀 Quick Start Guide

## Chạy ngay với Docker (1 phút)

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Thêm OpenAI API key vào .env (optional - app vẫn chạy được nếu không có)
# OPENAI_API_KEY=sk-xxx...

# 3. Start!
docker-compose up -d

# 4. Kiểm tra
curl http://localhost:8000/forms
```

✅ Done! API đang chạy tại `http://localhost:8000`

---

## Test API Flow

### 1. Xem danh sách forms
```bash
curl http://localhost:8000/forms
```

### 2. Bắt đầu session
```bash
curl -X POST http://localhost:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"query": "xin việc"}'
```

Response:
```json
{
  "session_id": "abc-123-...",
  "form_id": "don_xin_viec",
  "ask": "Họ và tên của bác là gì ạ? (ví dụ: Nguyễn Văn A)",
  "field": "full_name"
}
```

### 3. Trả lời câu hỏi
```bash
curl -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123-...", "text": "Nguyễn Văn A"}'
```

### 4. Tiếp tục trả lời cho đến khi `"done": true`

### 5. Xem preview
```bash
curl "http://localhost:8000/preview?session_id=abc-123-..."
```

### 6. Export PDF
```bash
curl "http://localhost:8000/export_pdf?session_id=abc-123-..." --output form.pdf
```

---

## Xem Logs

```bash
# Xem logs realtime
docker-compose logs -f app

# Chỉ xem 100 dòng cuối
docker-compose logs --tail=100 app

# Xem logs Redis
docker-compose logs redis
```

---

## Quản lý Services

```bash
# Stop
docker-compose down

# Restart
docker-compose restart app

# Rebuild
docker-compose up -d --build

# Xóa tất cả (kể cả data)
docker-compose down -v
```

---

## Local Development (không dùng Docker)

```bash
# 1. Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 4. Configure
cp .env.example .env
# Edit .env: REDIS_HOST=localhost

# 5. Run
uvicorn app:app --reload --port 8000
```

---

## Troubleshooting

### App không start?
```bash
# Xem logs
docker-compose logs app

# Check Redis
docker-compose ps redis
```

### Redis connection error?
```bash
# Restart Redis
docker-compose restart redis

# Check connectivity
docker exec fastapi_form_app redis-cli -h redis ping
```

### Port 8000 đã được dùng?
Edit `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Đổi thành port khác
```

---

## Useful Commands

```bash
# Check status
docker-compose ps

# Shell vào container
docker exec -it fastapi_form_app bash

# Redis CLI
docker exec -it fastapi_form_redis redis-cli

# Check Redis keys
docker exec fastapi_form_redis redis-cli KEYS "session:*"

# Backup Redis
docker exec fastapi_form_redis redis-cli BGSAVE
```

---

## 📚 More Info

- Full README: [README.md](README.md)
- Deployment Guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- Changes Log: [CHANGELOG.md](CHANGELOG.md)
- AI Instructions: [.github/copilot-instructions.md](.github/copilot-instructions.md)
