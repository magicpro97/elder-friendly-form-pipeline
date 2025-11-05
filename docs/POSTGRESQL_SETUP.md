# PostgreSQL Integration Guide

## Overview

Form processing pipeline với PostgreSQL để lưu trữ và tìm kiếm forms tự động từ crawler.

## Architecture

```
┌─────────────────┐
│ Daily Crawler   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Form Processor  │ ◄── OCR + AI Field Extraction
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Form Merger    │ ◄── Deduplicate + Merge
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PostgreSQL Sync │ ◄── Upsert to Railway DB
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   FastAPI App   │ ◄── Query forms from DB
└─────────────────┘
```

## Database Schema

### Tables

#### `forms`

Stores form metadata and source information.

| Column | Type | Description |
|--------|------|-------------|
| `form_id` | VARCHAR(255) PRIMARY KEY | Unique form identifier |
| `title` | TEXT NOT NULL | Form title (Vietnamese) |
| `aliases` | TEXT[] | Alternative names for search |
| `source` | VARCHAR(50) | 'manual' or 'crawler' |
| `metadata` | JSONB | OCR confidence, keywords, URL |
| `created_at` | TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

#### `form_fields`

Stores individual fields for each form.

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PRIMARY KEY | Auto-increment ID |
| `form_id` | VARCHAR(255) FOREIGN KEY | References forms(form_id) |
| `name` | VARCHAR(255) | Field name (e.g., 'full_name') |
| `label` | TEXT | Field label (Vietnamese) |
| `type` | VARCHAR(50) | 'string', 'date', 'phone', etc. |
| `required` | BOOLEAN | Whether field is required |
| `validators` | JSONB | Validation rules |
| `normalizers` | JSONB | Normalization rules |
| `pattern` | TEXT | Regex pattern |
| `field_order` | INTEGER | Display order |

### Indexes

- **Full-text search**: `idx_forms_title_fts`, `idx_forms_aliases_fts`
- **Fuzzy search**: `idx_forms_title_trgm` (trigram)
- **Performance**: `idx_forms_source`, `idx_form_fields_form_id`

### Functions

#### `search_forms(query, min_similarity, max_results)`

Vietnamese-aware search with relevance scoring (0.0-1.0).

## Setup on Railway

### 1. Create PostgreSQL Database

```bash
# On Railway dashboard:
# 1. Click "New" → "Database" → "PostgreSQL"
# 2. Copy DATABASE_URL
```

### 2. Add Environment Variables

```bash
# Railway project settings → Variables
DATABASE_URL=postgresql://user:password@host:port/database
```

### 3. Initialize Schema

**Option A: Manual via Railway Dashboard**

```bash
# Connect to database in Railway
# Paste contents of db/schema.sql
```

**Option B: Via sync script**

```bash
# Locally with Railway DATABASE_URL
python src/sync_to_db.py --init-schema --database-url "postgresql://..."
```

### 4. First Sync

```bash
# Sync existing forms to database
python src/sync_to_db.py --forms-file forms/all_forms.json
```

## GitHub Actions Setup

### Required Secrets

Add these in GitHub repo → Settings → Secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `RAILWAY_DATABASE_URL` | `postgresql://...` | From Railway dashboard |
| `OPENAI_API_KEY` | `sk-...` | For AI field extraction |

### Workflow Triggers

1. **Automatic**: After `daily-crawler.yml` completes
2. **Manual**: Workflow dispatch from Actions tab

### Workflow Steps

```yaml
1. Download crawler artifacts
2. Process forms (OCR + AI)
3. Merge with manual forms
4. Sync to PostgreSQL
5. Test search function
6. Commit changes [skip ci]
7. Create summary
```

## API Endpoints

### GET `/api/forms`

List all forms, optionally filtered by source.

**Query Parameters**:

- `source` (optional): 'manual' or 'crawler'

**Response**:

```json
{
  "ok": true,
  "count": 6,
  "source_filter": null,
  "forms": [
    {
      "form_id": "don_xin_viec",
      "title": "Đơn xin việc",
      "aliases": ["đơn xin việc", "job application"],
      "source": "manual",
      "fields": [...]
    }
  ]
}
```

### GET `/api/forms/search?q=đơn xin việc`

Search forms with Vietnamese fuzzy matching.

**Query Parameters**:

- `q` (required): Search query
- `min_score` (optional, default=0.3): Minimum relevance (0.0-1.0)
- `max_results` (optional, default=10): Max results (1-50)

**Response**:

```json
{
  "ok": true,
  "query": "đơn xin việc",
  "count": 2,
  "results": [
    {
      "form_id": "don_xin_viec",
      "title": "Đơn xin việc",
      "aliases": ["đơn xin việc"],
      "source": "manual",
      "relevance": 1.0
    }
  ]
}
```

### GET `/api/forms/{form_id}`

Get detailed information about a specific form.

**Response**:

```json
{
  "ok": true,
  "form": {
    "form_id": "don_xin_viec",
    "title": "Đơn xin việc",
    "fields": [
      {
        "name": "full_name",
        "label": "Họ và tên",
        "type": "string",
        "required": true
      }
    ]
  }
}
```

## Local Development

### Prerequisites

```bash
# Install PostgreSQL locally (macOS)
brew install postgresql@15
brew services start postgresql@15

# Or use Docker
docker run -d \
  --name elder-forms-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=elder_forms \
  -p 5432:5432 \
  postgres:15-alpine
```

### Configuration

```bash
# .env file
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/elder_forms
USE_POSTGRES=true
```

### Initialize Database

```bash
# Create schema
python src/sync_to_db.py --init-schema

# Sync forms
python src/sync_to_db.py

# Test search
python src/sync_to_db.py --test-search "đơn xin"
```

### Run App

```bash
# With PostgreSQL
python -m uvicorn app:app --reload

# Test API
curl http://localhost:8000/api/forms
curl "http://localhost:8000/api/forms/search?q=đơn"
curl http://localhost:8000/api/forms/don_xin_viec
```

## Fallback Behavior

App automatically falls back to JSON files if:

1. `USE_POSTGRES=false` in environment
2. `DATABASE_URL` not set
3. PostgreSQL connection fails

**Fallback logic**:

```python
# In app.py
if settings.use_postgres and settings.database_url:
    try:
        # Load from PostgreSQL
        forms = repo.get_all_forms()
    except Exception:
        # Fallback to JSON
        forms = load_forms_from_json()
```

## Maintenance

### View Database Stats

```bash
python src/sync_to_db.py  # Shows stats after sync
```

### Re-sync All Forms

```bash
# Force re-process and sync
make forms-pipeline
python src/sync_to_db.py
```

### Clear Form Cache

```python
# In app.py or via API
from src.form_repository import get_form_repository
repo = get_form_repository()
repo.clear_cache()
```

### Backup Database

```bash
# Via Railway CLI
railway run pg_dump $DATABASE_URL > backup.sql

# Restore
railway run psql $DATABASE_URL < backup.sql
```

## Performance

| Operation | PostgreSQL | JSON Fallback |
|-----------|-----------|---------------|
| List all forms (6) | ~50ms | ~5ms |
| Search forms | ~20ms (indexed) | ~50ms (fuzzy) |
| Get form by ID | ~10ms (cached) | ~1ms |
| Sync 100 forms | ~2s | N/A |

## Troubleshooting

### Connection Error

```
psycopg2.OperationalError: could not connect to server
```

**Solution**:

1. Check `DATABASE_URL` format
2. Verify Railway database is running
3. Check network/firewall

### Schema Not Initialized

```
relation "forms" does not exist
```

**Solution**:

```bash
python src/sync_to_db.py --init-schema
```

### Search Returns No Results

```
Empty results despite having forms
```

**Solution**:

1. Check trigram extension: `SELECT * FROM pg_extension WHERE extname = 'pg_trgm';`
2. Re-sync forms: `python src/sync_to_db.py`
3. Test query: `SELECT * FROM search_forms('đơn', 0.1, 10);`

### App Still Uses JSON

**Solution**:

1. Check environment variables:

   ```bash
   echo $DATABASE_URL
   echo $USE_POSTGRES
   ```

2. Restart app: `railway restart`

## Migration from JSON to PostgreSQL

```bash
# 1. Export current JSON forms
cp forms/all_forms.json forms/backup_forms.json

# 2. Initialize PostgreSQL schema
python src/sync_to_db.py --init-schema

# 3. Sync all forms to database
python src/sync_to_db.py --forms-file forms/all_forms.json

# 4. Update environment variable
# Railway dashboard → Set USE_POSTGRES=true

# 5. Restart app
railway restart

# 6. Test API
curl https://your-app.railway.app/api/forms
```

## Next Steps

1. ✅ Schema created (`db/schema.sql`)
2. ✅ Sync script implemented (`src/sync_to_db.py`)
3. ✅ GitHub Actions workflow (`.github/workflows/process-forms.yml`)
4. ✅ API endpoints added to `app.py`
5. ⏳ **Add `RAILWAY_DATABASE_URL` secret to GitHub**
6. ⏳ **Run manual workflow to test**
7. ⏳ **Monitor GitHub Actions logs**

## Resources

- [Railway PostgreSQL Docs](https://docs.railway.app/databases/postgresql)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [pg_trgm Extension](https://www.postgresql.org/docs/current/pgtrgm.html)
