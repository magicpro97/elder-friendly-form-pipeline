# Form Processing Pipeline

## Overview

Automated pipeline to convert crawled Vietnamese forms into structured JSON definitions compatible with the elder-friendly form system.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Daily Crawler (GitHub Actions)                                 │
│  ↓                                                               │
│  crawler_output/*.pdf, *.doc, *.docx                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Form Processor (src/form_processor.py)                         │
│  - OCR extraction (pytesseract, PyPDF2, python-docx)            │
│  - AI field detection (OpenAI GPT-4) with fallback              │
│  - Vietnamese text normalization                                │
│  - Automatic form_id generation                                 │
│  ↓                                                               │
│  forms/crawled_forms/*.json                                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Form Merger (src/form_merger.py)                               │
│  - Deduplicate by title similarity (80% threshold)              │
│  - Merge aliases and metadata                                   │
│  - Prioritize manual forms over crawled                         │
│  ↓                                                               │
│  forms/all_forms.json (manual + crawled)                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Form Search (src/form_search.py)                               │
│  - Vietnamese text normalization                                │
│  - Fuzzy matching with SequenceMatcher                          │
│  - Keyword indexing for fast lookup                             │
│  - Relevance scoring (0.0-1.0)                                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Endpoints (app.py)                                     │
│  - GET /forms (list all forms)                                  │
│  - GET /forms/search?q=... (search forms)                       │
│  - GET /forms/{form_id} (get specific form)                     │
│  - POST /session/start (pick form for conversation)             │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Form Processor (`src/form_processor.py`)

**Purpose**: Convert raw crawled files into structured form definitions

**Features**:

- ✅ OCR text extraction (PDF, DOCX, DOC, XLS, XLSX)
- ✅ AI-powered field detection using OpenAI GPT-4
- ✅ Fallback to pattern matching if OpenAI unavailable
- ✅ Vietnamese text normalization (remove diacritics)
- ✅ Automatic `form_id` generation (e.g., "Đơn xin việc" → "don_xin_viec")
- ✅ Metadata preservation (source URL, OCR confidence, keywords)

**Usage**:

```bash
# Process all files in crawler_output/
python src/form_processor.py

# Process specific directory
python src/form_processor.py --input path/to/files --output forms/crawled_forms

# Process single file
python src/form_processor.py --file crawler_output/mau-don.pdf
```

**Output Structure**:

```json
{
  "form_id": "don_xin_viec",
  "title": "Đơn xin việc",
  "aliases": ["xin việc", "apply job"],
  "source": "crawler",
  "metadata": {
    "source_file": "mau-don-xin-viec.pdf",
    "source_url": "https://...",
    "processed_at": "2025-11-05T19:00:00",
    "ocr_confidence": 0.95,
    "ocr_method": "pdf",
    "ocr_keywords": ["đơn", "họ tên", "ngày sinh"]
  },
  "fields": [
    {
      "name": "full_name",
      "label": "Họ và tên",
      "type": "string",
      "required": true
    }
  ]
}
```

**AI Prompt Strategy**:

- Model: `gpt-4o-mini` (fast, cost-effective)
- Temperature: 0.1 (deterministic)
- Max tokens: 2000
- Retry: 3 attempts with exponential backoff
- Fallback: Pattern matching for common Vietnamese fields

### 2. Form Merger (`src/form_merger.py`)

**Purpose**: Merge manual and crawled forms, remove duplicates

**Deduplication Strategy**:

1. Calculate title similarity using `SequenceMatcher`
2. If similarity ≥ 80% → considered duplicate
3. Check alias overlap
4. Prioritize manual forms (preserve manual edits)
5. Merge metadata from crawled version

**Usage**:

```bash
# Merge forms (default paths)
python src/form_merger.py

# Custom paths
python src/form_merger.py \
  --manual forms/form_samples.json \
  --crawled forms/crawled_forms \
  --output forms/all_forms.json \
  --threshold 0.8
```

**Output**:

```json
{
  "forms": [...],
  "count": 6,
  "sources": {
    "manual": 5,
    "crawler": 1
  },
  "generated_at": "2025-11-05T19:00:00"
}
```

### 3. Form Search (`src/form_search.py`)

**Purpose**: Fast, fuzzy search for Vietnamese forms

**Search Features**:

- ✅ Vietnamese text normalization (đ → d, á → a, etc.)
- ✅ Keyword indexing for O(1) lookup
- ✅ Fuzzy matching with relevance scoring
- ✅ Search by title, aliases, form_id
- ✅ Configurable minimum score (default: 0.3)

**Relevance Scoring**:

| Match Type | Score |
|------------|-------|
| Exact title match | 1.0 |
| Title contains query | 0.8 |
| Exact alias match | 0.7 |
| Alias contains query | 0.6 |
| Fuzzy similarity | 0.0-0.5 |

**Usage**:

```bash
# Search forms
python src/form_search.py "đơn xin việc"

# Adjust min score
python src/form_search.py "phản tố" --min-score 0.5

# List all forms
python src/form_search.py --list

# Filter by source
python src/form_search.py --list --source crawler
```

**Example Output**:

```
Search: 'đơn xin việc'
Found: 2 results
============================================================

1. Đơn xin việc
   Score: 1.000 | Source: manual | ID: don_xin_viec
   Aliases: xin việc, apply job

2. Đơn xin nghỉ phép
   Score: 0.650 | Source: manual | ID: don_xin_nghi_phep
   Aliases: nghỉ phép, leave request
```

## Directory Structure

```
forms/
├── form_samples.json          # Manual forms (curated)
├── crawled_forms/             # Processed crawled forms
│   ├── don_phan_to.json
│   ├── giay_uy_quyen_*.json
│   └── _index.json            # Index of all crawled forms
└── all_forms.json             # Merged forms (manual + crawled)

crawler_output/
├── mau-don-xin-viec.pdf       # Raw downloaded files
├── giay-uy-quyen.docx
├── downloaded_files.csv       # Metadata
└── crawler.log
```

## Workflow

### Manual Processing

```bash
# 1. Run crawler (if not already done)
python src/vietnamese_form_crawler.py

# 2. Process crawled files → structured JSON
python src/form_processor.py

# 3. Merge with manual forms
python src/form_merger.py

# 4. Test search
python src/form_search.py "đơn xin việc"
```

### Automated Processing (GitHub Actions)

**Workflow**: `.github/workflows/process-forms.yml`

```yaml
name: Process Crawled Forms

on:
  workflow_run:
    workflows: ["Daily Crawler"]
    types: [completed]
  workflow_dispatch:

jobs:
  process:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-crawler.txt

      - name: Download crawler artifacts
        uses: actions/download-artifact@v3
        with:
          name: crawler-output
          path: crawler_output/

      - name: Process forms
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python src/form_processor.py

      - name: Merge forms
        run: python src/form_merger.py

      - name: Commit changes
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add forms/crawled_forms/ forms/all_forms.json
          git commit -m "chore: process crawled forms"
          git push
```

## API Integration

### FastAPI Endpoints

**1. List All Forms**

```http
GET /forms?source=all
```

Response:

```json
{
  "forms": [...],
  "count": 6,
  "sources": {
    "manual": 5,
    "crawler": 1
  }
}
```

**2. Search Forms**

```http
GET /forms/search?q=đơn+xin+việc&min_score=0.3&max=10
```

Response:

```json
{
  "query": "đơn xin việc",
  "results": [
    {
      "form_id": "don_xin_viec",
      "title": "Đơn xin việc",
      "_search_score": 1.0,
      ...
    }
  ],
  "count": 2
}
```

**3. Get Form by ID**

```http
GET /forms/{form_id}
```

Response:

```json
{
  "form_id": "don_xin_viec",
  "title": "Đơn xin việc",
  "fields": [...]
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | None | OpenAI API key for AI field extraction |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for field detection |

### Form Processor Settings

```python
# In src/form_processor.py
MIN_TEXT_LENGTH = 50  # Minimum chars for valid form
SIMILARITY_THRESHOLD = 0.8  # Duplicate detection threshold
```

### Merger Settings

```python
# In src/form_merger.py
similarity_threshold = 0.8  # Can be adjusted via CLI
# python src/form_merger.py --threshold 0.85
```

## Troubleshooting

### Issue 1: No fields extracted

**Symptom**: Form processor returns empty fields

**Causes**:

1. OpenAI API key missing or invalid
2. OCR extraction failed (insufficient text)
3. File format not supported

**Solutions**:

```bash
# Check OCR extraction
python -c "from src.ocr_validator import OCRValidator; \
  from pathlib import Path; \
  ocr = OCRValidator(); \
  result = ocr.validate_file(Path('crawler_output/file.pdf')); \
  print(result)"

# Test with fallback (no OpenAI)
unset OPENAI_API_KEY
python src/form_processor.py --file path/to/file.pdf
```

### Issue 2: Duplicate forms not merged

**Symptom**: Same form appears twice in all_forms.json

**Causes**:

1. Title too different (< 80% similarity)
2. No alias overlap

**Solutions**:

```bash
# Lower similarity threshold
python src/form_merger.py --threshold 0.7

# Manually add aliases to one of the forms
```

### Issue 3: Search returns no results

**Symptom**: Search query returns 0 results

**Causes**:

1. Query too specific
2. Vietnamese diacritics not normalized
3. Min score too high

**Solutions**:

```bash
# Lower min score
python src/form_search.py "query" --min-score 0.2

# Use simpler query (single keyword)
python src/form_search.py "đơn"

# List all forms to verify data
python src/form_search.py --list
```

## Performance

### Processing Speed

| Task | Files | Time | Notes |
|------|-------|------|-------|
| OCR extraction | 1 PDF | ~0.5s | PyPDF2 (text-based) |
| OCR extraction | 1 PDF | ~3s | pdf2image + pytesseract (scanned) |
| AI field detection | 1 form | ~2s | OpenAI GPT-4o-mini |
| Pattern matching | 1 form | ~0.01s | Regex fallback |
| Merge (5+1 forms) | 6 forms | ~0.1s | SequenceMatcher |
| Search | 100 forms | ~0.05s | Indexed lookup |

### Optimization Tips

1. **Parallel processing** (future enhancement):

   ```python
   from concurrent.futures import ProcessPoolExecutor
   with ProcessPoolExecutor(max_workers=4) as executor:
       results = executor.map(process_file, file_paths)
   ```

2. **Cache AI results** (avoid re-processing):

   ```python
   # Add to form_processor.py
   cache_file = f"cache/{file_hash}.json"
   if cache_file.exists():
       return json.load(cache_file)
   ```

3. **Batch OpenAI calls** (future):
   Use OpenAI batch API for cost savings

## Testing

```bash
# Test form processor
python src/form_processor.py --file crawler_output/sample.pdf

# Test merger
python src/form_merger.py

# Test search
python src/form_search.py "đơn xin việc"

# Integration test
make test-form-pipeline  # TODO: Add to Makefile
```

## Future Enhancements

- [ ] **Parallel processing** for faster batch processing
- [ ] **Cache AI results** to avoid re-processing
- [ ] **Manual review interface** for AI-extracted fields
- [ ] **Field validation** (e.g., check field types, required flags)
- [ ] **Auto-generate validators** (regex patterns, date ranges)
- [ ] **Form versioning** (track changes over time)
- [ ] **Webhook notifications** when new forms added
- [ ] **Redis integration** for fast search (optional)
- [ ] **Admin UI** for form management

## Related Documentation

- [Crawler Documentation](CRAWLER_OCR.md)
- [Vietnamese Crawler](VIETNAMESE_CRAWLER.md)
- [GitHub Actions Workflows](WORKFLOWS.md)
- [API Documentation](../README.md)
