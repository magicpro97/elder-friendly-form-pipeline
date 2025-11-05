# Form Processing Quick Start

## 🚀 Phương án 1.5 đã được implement

Pipeline tự động để xử lý forms từ crawler thành cấu trúc JSON tương thích với hệ thống.

## Kiến trúc

```
Crawler → Form Processor → Form Merger → Form Search → API
```

## Cài đặt nhanh

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install -r requirements-crawler.txt

# 2. Crawl forms (nếu chưa có)
make crawler-run

# 3. Xử lý và merge forms
make forms-pipeline

# 4. Tìm kiếm forms
make forms-search Q="đơn xin việc"
```

## Commands quan trọng

| Command | Mô tả |
|---------|-------|
| `make forms-process` | Xử lý files từ crawler → JSON |
| `make forms-merge` | Merge manual + crawled forms |
| `make forms-search Q="..."` | Tìm kiếm forms |
| `make forms-list` | List tất cả forms |
| `make forms-pipeline` | Chạy full pipeline |

## Cấu trúc thư mục

```
forms/
├── form_samples.json          # Forms thủ công (5 forms)
├── crawled_forms/             # Forms từ crawler
│   ├── don_phan_to.json       # Example: Đơn phản tố
│   └── _index.json            # Index của crawled forms
└── all_forms.json             # Merged (manual + crawled = 6 forms)

crawler_output/
├── *.pdf, *.docx              # Raw files
└── downloaded_files.csv       # Metadata
```

## Features

### ✅ Form Processor (`src/form_processor.py`)

- OCR text extraction (PDF, DOCX, DOC, XLS, XLSX)
- AI field detection (OpenAI GPT-4o-mini) với fallback pattern matching
- Vietnamese text normalization
- Auto generate `form_id` từ title
- Metadata preservation (source URL, OCR confidence, keywords)

**Test**:

```bash
python src/form_processor.py --file crawler_output/mau-don.pdf
```

### ✅ Form Merger (`src/form_merger.py`)

- Deduplicate by title similarity (80% threshold)
- Merge aliases và metadata
- Prioritize manual forms
- Source tracking (manual/crawler)

**Test**:

```bash
python src/form_merger.py --threshold 0.8
```

### ✅ Form Search (`src/form_search.py`)

- Vietnamese text normalization (đ → d, á → a, etc.)
- Fuzzy matching với relevance scoring
- Keyword indexing cho fast lookup
- Search by title, aliases, form_id

**Test**:

```bash
python src/form_search.py "đơn xin việc"
python src/form_search.py --list --source crawler
```

## Example Output

### Processed Form

```json
{
  "form_id": "don_phan_to",
  "title": "ĐƠN PHẢN TỐ",
  "aliases": ["đơn phản tố", "phản tố"],
  "source": "crawler",
  "metadata": {
    "source_url": "https://luatsubaoho.com/...",
    "ocr_confidence": 1.0,
    "ocr_keywords": ["đơn", "số", "ngày"]
  },
  "fields": [
    {"name": "full_name", "label": "Họ và tên", "type": "string"},
    {"name": "id_number", "label": "Số CCCD/CMND", "type": "string"}
  ]
}
```

### Search Results

```
Search: 'phản tố'
Found: 2 results

1. ĐƠN PHẢN TỐ
   Score: 0.800 | Source: crawler | ID: don_phan_to

2. Giấy xác nhận cư trú
   Score: 0.370 | Source: manual | ID: xac_nhan_cu_tru
```

## Workflow Integration

### Manual Workflow

```bash
# 1. Crawl forms
make crawler-run

# 2. Process + merge
make forms-pipeline

# 3. Search to verify
make forms-search Q="đơn"
```

### Automated (GitHub Actions)

Workflow `.github/workflows/process-forms.yml` (TODO):

- Trigger sau khi Daily Crawler hoàn thành
- Auto-process forms
- Auto-merge với manual forms
- Commit changes
- Notify qua GitHub Issues

## API Integration (TODO)

Endpoints cần thêm vào `app.py`:

```python
@app.get("/forms/search")
def search_forms(q: str, min_score: float = 0.3):
    """Search forms by query"""
    from src.form_search import FormSearch
    searcher = FormSearch()
    return searcher.search(q, min_score=min_score)

@app.get("/forms/{form_id}")
def get_form(form_id: str):
    """Get form by ID"""
    from src.form_search import FormSearch
    searcher = FormSearch()
    return searcher.search_by_id(form_id)
```

## Performance

| Task | Time | Notes |
|------|------|-------|
| OCR extraction (PDF text) | ~0.5s | PyPDF2 |
| OCR extraction (scanned) | ~3s | pdf2image + pytesseract |
| AI field detection | ~2s | OpenAI GPT-4o-mini |
| Pattern matching (fallback) | ~0.01s | Regex |
| Merge (5+1 forms) | ~0.1s | SequenceMatcher |
| Search (100 forms) | ~0.05s | Indexed lookup |

## Troubleshooting

### OpenAI API Error

```bash
# Error: Client.__init__() got an unexpected keyword argument 'proxies'
# Solution: Update openai package
pip install --upgrade openai
```

### No fields extracted

```bash
# Check OCR extraction
python -c "from src.ocr_validator import OCRValidator; \
  from pathlib import Path; \
  ocr = OCRValidator(); \
  result = ocr.validate_file(Path('file.pdf')); \
  print(result)"
```

### Duplicate not merged

```bash
# Lower threshold
python src/form_merger.py --threshold 0.7
```

## Documentation

- [Full Documentation](docs/FORM_PROCESSING.md)
- [Crawler Documentation](docs/CRAWLER_OCR.md)
- [Vietnamese Crawler](docs/VIETNAMESE_CRAWLER.md)

## Next Steps

- [ ] Add API endpoints to `app.py`
- [ ] Create GitHub Actions workflow
- [ ] Add manual review interface
- [ ] Implement Redis caching for search
- [ ] Add field validation
- [ ] Auto-generate validators

## Status

✅ **Completed**:

- Form Processor with AI + fallback
- Form Merger with deduplication
- Form Search with fuzzy matching
- Documentation
- Makefile commands
- Local testing successful

⏳ **In Progress**:

- API endpoints integration
- GitHub Actions workflow

📋 **TODO**:

- Manual review interface
- Redis integration
- Admin UI
