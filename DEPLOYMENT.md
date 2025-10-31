# Deployment Guide

## 🐳 Docker Deployment (Recommended)

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+

### Steps

1. **Clone repository**
```bash
git clone <repo-url>
cd fastapi_form_pipeline
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env and set:
# - OPENAI_API_KEY (required for AI features)
# - Other optional configs
```

3. **Build and start services**
```bash
docker-compose up -d --build
```

4. **Verify deployment**
```bash
# Check services are running
docker-compose ps

# Check logs
docker-compose logs -f app

# Test API
curl http://localhost:8000/forms
```

5. **Health checks**
```bash
# App health
curl http://localhost:8000/forms

# Redis health
docker exec fastapi_form_redis redis-cli ping
# Should return: PONG
```

### Management Commands

```bash
# View logs
docker-compose logs -f app        # App logs
docker-compose logs -f redis      # Redis logs

# Restart services
docker-compose restart app
docker-compose restart redis

# Stop services
docker-compose stop

# Remove containers (keeps data)
docker-compose down

# Remove everything including volumes
docker-compose down -v

# Update and restart
git pull
docker-compose up -d --build
```

## 🔧 Production Considerations

### 1. Environment Variables
```bash
# Production .env should have:
OPENAI_API_KEY=sk-xxx...
OPENAI_MODEL=o4-mini
REDIS_HOST=redis
REDIS_PORT=6379
SESSION_TTL_SECONDS=3600
PDF_TEMPLATE=generic_form.html
```

### 2. Redis Configuration
For production, consider:
- Redis password protection
- AOF persistence
- Memory limits
- Backup strategy

Edit `docker-compose.yml`:
```yaml
redis:
  command: >
    redis-server
    --appendonly yes
    --requirepass your_secure_password
    --maxmemory 512mb
    --maxmemory-policy allkeys-lru
```

Update `.env`:
```
REDIS_PASSWORD=your_secure_password
```

### 3. Reverse Proxy (Nginx)
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running requests
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }
}
```

### 4. SSL/TLS (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 5. Monitoring & Logging

**Docker logs to file:**
```yaml
# docker-compose.yml
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**Prometheus monitoring:**
```python
# Add to requirements.txt
prometheus-fastapi-instrumentator==6.1.0

# Add to app.py
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)
```

### 6. Scaling

**Horizontal scaling with multiple workers:**
```yaml
# docker-compose.yml
services:
  app:
    command: uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
    deploy:
      replicas: 3
```

**Load balancer (Nginx):**
```nginx
upstream fastapi_backend {
    least_conn;
    server localhost:8001;
    server localhost:8002;
    server localhost:8003;
}

server {
    location / {
        proxy_pass http://fastapi_backend;
    }
}
```

## 🚀 Cloud Deployment

### AWS ECS/Fargate
```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker build -t fastapi-form-pipeline .
docker tag fastapi-form-pipeline:latest <account>.dkr.ecr.us-east-1.amazonaws.com/fastapi-form-pipeline:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/fastapi-form-pipeline:latest

# Use ElastiCache for Redis
# Set REDIS_HOST to ElastiCache endpoint
```

### Google Cloud Run
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/PROJECT-ID/fastapi-form-pipeline
gcloud run deploy fastapi-form-pipeline \
  --image gcr.io/PROJECT-ID/fastapi-form-pipeline \
  --platform managed \
  --set-env-vars OPENAI_API_KEY=xxx,REDIS_HOST=xxx
```

### Heroku
```bash
# Add Heroku Redis addon
heroku addons:create heroku-redis:mini

# Deploy
heroku container:push web
heroku container:release web

# Set environment
heroku config:set OPENAI_API_KEY=xxx
```

## 🔐 Security Checklist

- [ ] Use strong Redis password in production
- [ ] Keep `.env` file secure (never commit)
- [ ] Use HTTPS/TLS for all traffic
- [ ] Limit CORS origins in production
- [ ] Enable rate limiting
- [ ] Regular security updates
- [ ] Monitor logs for suspicious activity
- [ ] Backup Redis data regularly
- [ ] Use secrets management (AWS Secrets Manager, etc.)

## 📊 Monitoring

### Key Metrics to Monitor
- API response times
- Error rates (4xx, 5xx)
- OpenAI API call success/failure rates
- Redis connection status
- Session creation/expiration rates
- Memory usage
- CPU usage

### Health Check Endpoints
```bash
# Check app health
curl http://localhost:8000/forms

# Check Redis
docker exec fastapi_form_redis redis-cli info stats
```

## 🐛 Troubleshooting

### App won't start
```bash
# Check logs
docker-compose logs app

# Common issues:
# - Redis not available → check redis service
# - Port 8000 in use → change port in docker-compose.yml
# - Missing .env → copy from .env.example
```

### Redis connection issues
```bash
# Test Redis connectivity
docker exec fastapi_form_app redis-cli -h redis ping

# Check Redis logs
docker-compose logs redis
```

### OpenAI API errors
```bash
# Check API key
echo $OPENAI_API_KEY

# Check quota at https://platform.openai.com/usage

# App will fallback automatically if OpenAI fails
```

## 📝 Backup & Recovery

### Backup Redis data
```bash
# Manual backup
docker exec fastapi_form_redis redis-cli BGSAVE

# Copy dump file
docker cp fastapi_form_redis:/data/dump.rdb ./backup/dump-$(date +%Y%m%d).rdb

# Automated backup script
#!/bin/bash
docker exec fastapi_form_redis redis-cli BGSAVE
sleep 5
docker cp fastapi_form_redis:/data/dump.rdb /backups/dump-$(date +%Y%m%d-%H%M%S).rdb
```

### Restore Redis data
```bash
# Stop Redis
docker-compose stop redis

# Copy backup file
docker cp ./backup/dump.rdb fastapi_form_redis:/data/dump.rdb

# Start Redis
docker-compose start redis
```
