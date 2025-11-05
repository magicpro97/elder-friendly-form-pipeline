# OCR Validation for Crawler

## Quick Start

### 1. Install System Dependencies

**macOS:**
```bash
brew install tesseract tesseract-lang poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-vie poppler-utils
```

**Verify installation:**
```bash
tesseract --version
tesseract --list-langs | grep vie  # Should show 'vie'
pdftoppm -v
```

### 2. Install Python Dependencies

```bash
source .venv/bin/activate
pip install -r requirements-crawler.txt
```

### 3. Test OCR on Existing Files

```bash
# Test all downloaded files
python test_ocr_validator.py

# Test single file
python src/ocr_validator.py crawler_output/mau-don.pdf
```

### 4. Run Crawler with OCR

```bash
# With OCR validation (default)
python src/vietnamese_form_crawler.py

# Without OCR (faster)
ENABLE_OCR=false python src/vietnamese_form_crawler.py
```

## How It Works

### File Processing Flow

```
Download File
    ↓
Detect File Type (.pdf, .docx, .xls, .xlsx)
    ↓
Extract Text (PyPDF2, python-docx, openpyxl)
    ↓
Search for Vietnamese Keywords
    ↓
Calculate Confidence Score
    ↓
Mark as Valid/Invalid
    ↓
Save to CSV with validation results
```

### Supported File Types

| Extension | Extraction Method | Library |
|-----------|------------------|---------|
| `.pdf` (text) | Text extraction | PyPDF2 |
| `.pdf` (scanned) | OCR | pytesseract + pdf2image |
| `.docx` | Document parsing | python-docx |
| `.doc` | Text extraction | textract (fallback to assumed valid) |
| `.xls`, `.xlsx` | Cell reading | openpyxl |

**Note:** Image files (`.jpg`, `.png`) are no longer supported due to quality issues (broken images, ads, irrelevant content).

### Vietnamese Keywords Detected

**Form Keywords:**
- mẫu, đơn, biểu mẫu, tờ khai, phiếu
- giấy, bản khai, hồ sơ, văn bản

**Date/Number Fields:**
- số, ngày, tháng, năm

**Personal Info:**
- họ tên, địa chỉ, cmnd, cccd

**Official Fields:**
- chức vụ, chữ ký, xác nhận

### Validation Criteria

✅ **VALID** if:
- Text length ≥ 50 characters
- At least 2 form keywords found

❌ **INVALID** if:
- Insufficient text extracted
- No form keywords found
- Extraction error

### Confidence Score

```python
Score = Text_Bonus + Keyword_Bonus + Method_Bonus

Text_Bonus = 0.3 if text_length >= 50 else 0
Keyword_Bonus = min(keyword_count / 5.0, 0.5)
Method_Bonus = {
    'pdf': 0.2,      # High reliability
    'docx': 0.2,     # High reliability
    'image_ocr': 0.1 # Medium reliability
}
```

**Range:** 0.0 - 1.0

## CSV Output

### Without OCR (old format):
```csv
Tieu_de_trang,Link_file,Ten_file,Dang_tep,Ngay_dang
"Mẫu đơn","http://...",mau-don.pdf,.pdf,2025-11-05
```

### With OCR (new format):
```csv
Tieu_de_trang,Link_file,Ten_file,Dang_tep,Ngay_dang,OCR_Valid,OCR_Confidence,OCR_Keywords,OCR_Method
"Mẫu đơn","http://...",mau-don.pdf,.pdf,2025-11-05,Yes,0.85,"mẫu, đơn, họ tên",pdf
```

**Columns:**
- `OCR_Valid`: Yes/No
- `OCR_Confidence`: 0.00 - 1.00
- `OCR_Keywords`: Top 3 keywords found
- `OCR_Method`: pdf/docx/image_ocr/etc.

## Example Results

### ✓ Valid PDF (High Confidence)

```
✓ VALID - mau-don-dang-ky.pdf
  Confidence: 0.85
  Method: pdf
  Text length: 1547 chars
  Keywords found: mẫu, đơn, họ tên, địa chỉ, ngày
```

### ✗ Invalid Image (Low Confidence)

```
✗ INVALID - random-image.jpg
  Confidence: 0.15
  Method: image_ocr
  Text length: 23 chars
  Keywords found: (none)
```

### ✓ Assumed Valid (DOC file)

```
✓ VALID - mau-don.doc
  Confidence: 0.60
  Method: doc_assumed
  Text length: 0 chars
  Note: textract not available, file assumed valid
```

## Performance

### Speed Comparison

| File Type | Processing Time | Accuracy |
|-----------|----------------|----------|
| PDF (text) | ~0.1s ⚡⚡⚡ | ⭐⭐⭐ High |
| DOCX | ~0.2s ⚡⚡⚡ | ⭐⭐⭐ High |
| Image (OCR) | ~3-5s ⚡ | ⭐⭐ Medium |
| PDF (scanned OCR) | ~5-10s ⚡ | ⭐⭐ Medium |

### Optimization

**Skip OCR for large batches:**
```python
crawler = VietnameseFormCrawler(enable_ocr=False)
```

**Process only high-priority file types:**
```python
# In settings.py
FILE_EXTENSIONS = [".pdf", ".docx"]  # Skip images
```

## Troubleshooting

### Error: Tesseract not found

```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-vie

# Verify
tesseract --version
```

### Error: Vietnamese language not installed

```bash
# Download Vietnamese language data
brew install tesseract-lang  # macOS
sudo apt-get install tesseract-ocr-vie  # Ubuntu

# Verify
tesseract --list-langs | grep vie
```

### Error: pdf2image fails

```bash
# Install poppler
brew install poppler  # macOS
sudo apt-get install poppler-utils  # Ubuntu

# Verify
pdftoppm -v
```

### Low Confidence Scores

**Causes:**
- Poor image quality
- Non-Vietnamese text
- Corrupted file

**Solutions:**
1. Check original file quality
2. Verify Vietnamese language pack: `tesseract --list-langs`
3. Test extraction manually: `python src/ocr_validator.py <file>`

## Advanced Usage

### Custom Keywords

Edit `src/ocr_validator.py`:

```python
class OCRValidator:
    FORM_KEYWORDS = [
        "mẫu", "đơn",
        "your_custom_keyword",  # Add here
    ]
```

### Adjust Validation Thresholds

```python
class OCRValidator:
    MIN_TEXT_LENGTH = 50         # Minimum characters
    MIN_KEYWORD_MATCHES = 2      # Minimum keywords
```

### Delete Invalid Files

In `vietnamese_form_crawler.py`, uncomment:

```python
if not validation_result.get('is_valid'):
    file_path.unlink()  # Delete invalid file
    return False, None
```

## GitHub Actions Integration

Update `.github/workflows/daily-crawler.yml`:

```yaml
- name: Install OCR dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      tesseract-ocr \
      tesseract-ocr-vie \
      poppler-utils

- name: Install Python packages
  run: pip install -r requirements-crawler.txt

- name: Run crawler with OCR
  run: python src/vietnamese_form_crawler.py
```

## CSV Analytics

**Count valid files:**
```bash
awk -F',' '$6=="Yes"' crawler_output/downloaded_files.csv | wc -l
```

**Average confidence:**
```bash
awk -F',' 'NR>1 {sum+=$7; count++} END {print sum/count}' crawler_output/downloaded_files.csv
```

**Most common extraction method:**
```bash
awk -F',' 'NR>1 {print $9}' crawler_output/downloaded_files.csv | sort | uniq -c | sort -rn
```

**List invalid files:**
```bash
awk -F',' '$6=="No" {print $3}' crawler_output/downloaded_files.csv
```

## Summary Output

```
VIETNAMESE FORM CRAWLER - SUMMARY
==================================================
Total targets: 2
Files downloaded: 5
Files validated (OCR): 4
Files failed validation: 1
Validation rate: 80.0%
Output directory: crawler_output
CSV file: crawler_output/downloaded_files.csv
==================================================
```

## Architecture

```python
# src/ocr_validator.py
class OCRValidator:
    def validate_file(file_path) -> dict:
        # Returns: {is_valid, confidence, keywords, method, ...}

# src/vietnamese_form_crawler.py
class VietnameseFormCrawler:
    def __init__(enable_ocr=True):
        self.ocr_validator = OCRValidator()

    def download_file(url):
        # 1. Download
        # 2. Validate with OCR
        # 3. Save results to CSV
```

## Next Steps

1. **Install dependencies:** `brew install tesseract tesseract-lang poppler`
2. **Test OCR:** `python test_ocr_validator.py`
3. **Run crawler:** `python src/vietnamese_form_crawler.py`
4. **Check results:** `cat crawler_output/downloaded_files.csv`

## References

- [pytesseract](https://github.com/madmaze/pytesseract)
- [PyPDF2](https://pypdf2.readthedocs.io/)
- [python-docx](https://python-docx.readthedocs.io/)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [Vietnamese Language Data](https://github.com/tesseract-ocr/tessdata)
