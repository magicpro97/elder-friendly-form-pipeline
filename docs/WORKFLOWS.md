# GitHub Actions Workflows

## Overview

This project has 3 GitHub Actions workflows:

1. **CI/CD Pipeline** - Test and lint on every push/PR
2. **Daily Crawler** - Automated daily form crawling with OCR validation
3. **Deploy to Railway** - Deploy to production

## 1. CI/CD Pipeline

**File:** `.github/workflows/ci-cd.yml`

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

**Jobs:**

### Test Job
- **OS:** Ubuntu Latest
- **Python:** 3.11
- **Services:** Redis 7 Alpine

**Steps:**
1. Install system dependencies (WeasyPrint requirements)
2. Install Python dependencies (requirements.txt only)
3. Run linting (flake8, black, isort)
4. Run tests with coverage
   - **Skips crawler tests** (test_crawler.py, test_vietnamese_crawler.py)
   - Reason: Crawler tests require OCR dependencies not needed for main app
5. Upload coverage to Codecov

**Important Notes:**
- Crawler dependencies (pytesseract, etc.) are **NOT installed**
- Crawler tests are **skipped** with `--ignore` flags
- This keeps CI fast and focused on core FastAPI app

## 2. Daily Crawler

**File:** `.github/workflows/daily-crawler.yml`

**Triggers:**
- **Scheduled:** Daily at 2:00 AM UTC (9:00 AM Vietnam)
- **Manual:** workflow_dispatch from GitHub UI

**Jobs:**

### Crawl Job
- **OS:** Ubuntu Latest
- **Python:** 3.11
- **Timeout:** 30 minutes

**Steps:**
1. **Install OCR system dependencies:**
   - tesseract-ocr
   - tesseract-ocr-vie (Vietnamese language pack)
   - poppler-utils (for PDF to image conversion)

2. **Verify OCR installation:**
   - Check tesseract version
   - Verify Vietnamese language available
   - Check poppler tools

3. **Install Python dependencies:**
   - requirements.txt (core app)
   - requirements-crawler.txt (OCR + crawler libs)

4. **Run crawler:**
   - Executes `src/vietnamese_form_crawler.py`
   - Uses environment variables for config

5. **Upload artifacts:**
   - crawler_output/ (downloaded files + CSV)
   - logs/
   - Retention: 30 days

6. **Notify on failure:**
   - Creates GitHub issue automatically
   - Labels: crawler, automated

**Environment Variables:**
```yaml
CRAWLER_TARGETS: ${{ secrets.CRAWLER_TARGETS }}
  # Default: https://thuvienphapluat.vn,https://luatsubaoho.com

CRITICAL_KEYWORDS: ${{ vars.CRITICAL_KEYWORDS }}
  # Default: mẫu,đơn,biểu mẫu,tờ khai,...

DB_DATE: ${{ vars.DB_DATE }}
  # Default: 2024-01-01
```

**Required Secrets/Variables:**
- `secrets.CRAWLER_TARGETS` (optional) - Override default URLs
- `vars.CRITICAL_KEYWORDS` (optional) - Override default keywords
- `vars.DB_DATE` (optional) - Override date filter

## 3. Deploy to Railway

**File:** `.github/workflows/railway-deploy.yml`

**Triggers:**
- Push to `main` branch
- Pull requests to `main`

**Jobs:**

### Test Job (runs first)
- Same as CI/CD Pipeline
- **Also skips crawler tests**
- Requires `secrets.OPENAI_API_KEY`

### Deploy Job (only on push to main)
- Installs Railway CLI
- Deploys using `railway up --detach`
- Requires `secrets.RAILWAY_TOKEN`

**Required Secrets:**
- `secrets.OPENAI_API_KEY` - For testing
- `secrets.RAILWAY_TOKEN` - For deployment

## Workflow Dependencies

### CI/CD Pipeline
**System:**
- libpango-1.0-0
- libpangocairo-1.0-0
- libgdk-pixbuf2.0-0
- libffi-dev
- shared-mime-info

**Python:**
- requirements.txt only
- No crawler dependencies

### Daily Crawler
**System:**
- tesseract-ocr
- tesseract-ocr-vie
- poppler-utils

**Python:**
- requirements.txt
- requirements-crawler.txt:
  - pytesseract>=0.3.10
  - Pillow>=10.0.0
  - PyPDF2>=3.0.0
  - pdf2image>=1.16.3
  - python-docx>=1.1.0
  - openpyxl>=3.1.2
  - textract>=1.6.5 (optional)

### Railway Deploy
**System:**
- Same as CI/CD Pipeline

**Python:**
- requirements.txt only
- Crawler not deployed to Railway

## Test Strategy

### Main App Tests (CI/CD, Railway)
- ✅ `tests/test_api.py` - API endpoints
- ✅ `tests/test_forms.py` - Form logic
- ✅ `tests/test_session.py` - Redis sessions
- ✅ `tests/test_validation.py` - Field validation
- ✅ `tests/test_coverage.py` - Coverage checks

### Crawler Tests (Local + Manual Only)
- ❌ `tests/test_crawler.py` - **SKIPPED in CI**
- ❌ `tests/test_vietnamese_crawler.py` - **SKIPPED in CI**

**Why Skip?**
1. Require OCR system dependencies (tesseract, poppler)
2. Slow (OCR processing takes time)
3. Not needed for main app deployment
4. Tested separately via Daily Crawler workflow

**How to Run Locally:**
```bash
# Install OCR dependencies first
make ocr-deps-mac  # or ocr-deps-ubuntu

# Run all tests including crawler
pytest tests/ -v
```

## Manual Workflow Triggers

### Trigger Daily Crawler Manually
```bash
# Via GitHub CLI
gh workflow run "Daily Crawler"

# Via GitHub UI
Actions → Daily Crawler → Run workflow
```

### Check Workflow Status
```bash
# List recent runs
gh run list --limit 5

# View specific workflow
gh run list --workflow="Daily Crawler"

# Watch in real-time
gh run watch
```

## Troubleshooting

### CI Failing with "ModuleNotFoundError: No module named 'requests'"
**Cause:** Test file imports crawler modules

**Solution:** Ensure crawler tests are skipped:
```yaml
pytest tests/ -v \
  --ignore=tests/test_crawler.py \
  --ignore=tests/test_vietnamese_crawler.py
```

### Daily Crawler Failing with "tesseract: not found"
**Cause:** OCR dependencies not installed

**Solution:** Add to workflow:
```yaml
- name: Install system dependencies for OCR
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      tesseract-ocr \
      tesseract-ocr-vie \
      poppler-utils
```

### Daily Crawler Failing with "Vietnamese language not found"
**Cause:** tesseract-ocr-vie package not installed

**Solution:**
```yaml
sudo apt-get install -y tesseract-ocr-vie
```

**Verify:**
```bash
tesseract --list-langs | grep vie
```

### Railway Deploy Timing Out
**Cause:** Tests take too long or hanging

**Solution:**
1. Check if crawler tests are skipped
2. Verify Redis service is healthy
3. Check OPENAI_API_KEY is set

## Best Practices

### Adding New Tests

**Main App Test:**
```python
# tests/test_new_feature.py
# ✅ Will run in all workflows
def test_new_feature():
    assert True
```

**Crawler Test:**
```python
# tests/test_new_crawler.py
# ❌ Will be skipped in CI (add to --ignore list)
from src.vietnamese_form_crawler import ...
```

### Environment Variables

**Secrets (sensitive):**
- OPENAI_API_KEY
- RAILWAY_TOKEN
- CRAWLER_TARGETS (if contains internal URLs)

**Variables (non-sensitive):**
- CRITICAL_KEYWORDS
- DB_DATE
- LOG_LEVEL

**Set in GitHub:**
Settings → Secrets and variables → Actions

### Workflow Optimization

**Speed up CI:**
- Use `cache: "pip"` in setup-python
- Skip unnecessary tests
- Parallelize jobs when possible

**Reduce crawler runtime:**
- Adjust timeout: `timeout-minutes: 30`
- Limit targets: fewer URLs in CRAWLER_TARGETS
- Filter aggressively: stricter DB_DATE

## Monitoring

### Check Workflow Runs
```bash
gh run list --limit 10
```

### Download Artifacts
```bash
# List artifacts
gh run view <run-id>

# Download
gh run download <run-id>
```

### View Logs
```bash
# Failed runs only
gh run view --log-failed

# Specific job
gh run view <run-id> --log
```

## Summary

| Workflow | Frequency | Tests Crawler? | Installs OCR? | Purpose |
|----------|-----------|----------------|---------------|---------|
| CI/CD Pipeline | Every push/PR | ❌ Skip | ❌ No | Test main app |
| Daily Crawler | Daily 2AM UTC | ✅ Yes (runs crawler) | ✅ Yes | Download forms |
| Railway Deploy | Push to main | ❌ Skip | ❌ No | Deploy to prod |

**Key Point:** Crawler functionality is isolated:
- ✅ Tested in Daily Crawler workflow (with OCR deps)
- ❌ Skipped in main CI/CD (keeps it fast)
- 🚀 Not deployed to Railway (separate service)
