# Vietnamese Form Crawler

## Tổng quan

Crawler chuyên dụng để thu thập các mẫu đơn, biểu mẫu tiếng Việt từ các trang web pháp luật, thủ tục hành chính.

## Tính năng chính

### 🎯 Crawl 2 cấp độ

- **Level 1**: Quét trang chính để tìm links
- **Level 2**: Quét các trang con để tìm files

### 📅 Lọc theo ngày đăng

- Chỉ crawl các form đăng sau `DB_DATE` (mặc định: 2024-01-01)
- Hỗ trợ format Việt Nam: `dd/mm/yyyy`, `yyyy-mm-dd`
- Tự động loại bỏ các trang cũ

### 🔍 Lọc theo từ khóa

- **CRITICAL_KEYWORDS**: `mẫu`, `đơn`, `biểu mẫu`, `tờ khai`, `phiếu đăng ký`, v.v.
- Chỉ download files có chứa từ khóa quan trọng
- Tránh download files không liên quan

### 📊 CSV Export

```csv
Tieu_de_trang,Link_file,Ten_file,Dang_tep,Ngay_dang
"Mẫu đơn đăng ký",https://...,mau-don.pdf,.pdf,2024-01-15
```

### 🛡️ Anti-bot Protection

- Sử dụng `cloudscraper` để bypass Cloudflare, anti-bot
- Automatic retry với exponential backoff
- Configurable delays giữa các requests

## Cài đặt

### 1. Dependencies

```bash
# Trong virtual environment hoặc Docker
pip install -r requirements-crawler.txt
```

Hoặc thêm vào Docker:

```dockerfile
RUN pip install -r requirements-crawler.txt
```

### 2. Configuration

Copy và chỉnh sửa file config:

```bash
cp .env.crawler.example .env
```

Chỉnh sửa `.env`:

```bash
# Target URLs (phân cách bằng dấu phẩy)
CRAWLER_TARGETS=https://thuvienphapluat.vn,https://luatsubaoho.com

# Từ khóa cần tìm
CRITICAL_KEYWORDS=mẫu,đơn,biểu mẫu,tờ khai

# Chỉ crawl form sau ngày này
DB_DATE=2024-01-01
```

## Sử dụng

### Local Execution

```bash
# Chạy crawler
python3 src/vietnamese_form_crawler.py

# Kết quả được lưu tại:
# - crawler_output/downloaded_files.csv
# - crawler_output/crawler.log
# - crawler_output/*.pdf, *.doc, *.xlsx, ...
```

### GitHub Actions (Tự động hàng ngày)

Crawler chạy tự động **mỗi ngày lúc 2:00 AM UTC** (9:00 AM Việt Nam).

#### Setup Secrets

Vào **Settings → Secrets and variables → Actions**:

1. **Secrets** (bí mật):
   - `CRAWLER_TARGETS`: Danh sách URLs cần crawl

2. **Variables** (công khai):
   - `CRITICAL_KEYWORDS`: Từ khóa (tùy chọn)
   - `DB_DATE`: Ngày cutoff (tùy chọn, mặc định: 2024-01-01)

#### Manual Trigger

1. Vào tab **Actions**
2. Chọn workflow **Daily Crawler**
3. Click **Run workflow**

## Output

### File Structure

```
crawler_output/
├── downloaded_files.csv      # Danh sách files đã tải
├── crawler.log               # Execution logs
├── mau-don-dang-ky.pdf       # Downloaded forms
├── bieu-mau-to-khai.xlsx
└── phieu-dang-ky.doc
```

### CSV Format

| Tieu_de_trang | Link_file | Ten_file | Dang_tep | Ngay_dang |
|---------------|-----------|----------|----------|-----------|
| Mẫu đơn xin việc | https://... | mau-don.pdf | .pdf | 2024-01-15 |

## Use Cases

### 1. Thu thập mẫu đơn hành chính

```bash
CRAWLER_TARGETS="https://thuvienphapluat.vn,https://luatsubaoho.com"
CRITICAL_KEYWORDS="mẫu,đơn,biểu mẫu"
DB_DATE=2024-01-01
```

### 2. Crawl mẫu đơn đất đai

```bash
CRAWLER_TARGETS="https://thuviennhadat.vn"
CRITICAL_KEYWORDS="mẫu,đơn,đất đai,biến động"
```

### 3. Crawl mẫu hóa đơn, chứng từ

```bash
CRAWLER_TARGETS="https://thuvienphapluat.vn"
CRITICAL_KEYWORDS="hóa đơn,chứng từ,phiếu"
```

## Customization

### Thêm từ khóa mới

Chỉnh sửa `src/settings.py`:

```python
CRITICAL_KEYWORDS = [
    "mẫu", "đơn", "biểu mẫu", "tờ khai",
    "giấy chứng nhận",  # Thêm từ khóa mới
    "giấy phép",
]
```

### Thêm file extension

Chỉnh sửa `src/vietnamese_form_crawler.py`:

```python
FILE_EXTENSIONS = [
    ".pdf", ".doc", ".docx",
    ".ppt", ".pptx",  # Thêm PowerPoint
]
```

### Custom date parsing

Chỉnh sửa `DATE_PATTERNS` trong `VietnameseFormCrawler`:

```python
DATE_PATTERNS = [
    r"(\d{1,2}/\d{1,2}/\d{4})",
    r"(\d{4}-\d{1,2}-\d{1,2})",
    r"ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})",  # Custom format
]
```

## Testing

### Unit Tests

```bash
# Run all tests
pytest tests/test_vietnamese_crawler.py -v

# Run specific test
pytest tests/test_vietnamese_crawler.py::TestVietnameseFormCrawler::test_extract_date_from_html -v

# With coverage
pytest tests/test_vietnamese_crawler.py --cov=src.vietnamese_form_crawler
```

### Manual Testing

```bash
# Test với 1 URL
export CRAWLER_TARGETS="https://thuvienphapluat.vn/hoi-dap-phap-luat/tong-hop-mau-don-xin-viec-moi-nhat-va-huong-dan-cach-viet-11482"
python3 src/vietnamese_form_crawler.py
```

## Troubleshooting

### "No files downloaded"

**Nguyên nhân**:

- URLs không có files mới sau `DB_DATE`
- Từ khóa không match với nội dung trang
- Website bị anti-bot block

**Giải pháp**:

```bash
# Giảm DB_DATE để test
DB_DATE=2020-01-01

# Thêm từ khóa
CRITICAL_KEYWORDS="mẫu,đơn,tải,download"

# Check logs
tail -f crawler_output/crawler.log
```

### "Cloudscraper failed"

**Nguyên nhân**: Website có Cloudflare protection mạnh

**Giải pháp**:

```bash
# Install latest cloudscraper
pip install --upgrade cloudscraper

# Hoặc dùng Selenium (chậm hơn)
# Chỉnh sửa code để dùng Selenium
```

### "Date not found"

**Nguyên nhân**: Website không có ngày đăng hoặc format khác

**Giải pháp**:

- Thêm date pattern mới vào `DATE_PATTERNS`
- Hoặc tắt date filtering (set `DB_DATE=2000-01-01`)

## Architecture

```
VietnameseFormCrawler
├── __init__()           # Initialize session, CSV
├── extract_date()       # Parse Vietnamese dates
├── extract_form_links() # Find links with keywords
├── download_file()      # Download & save to CSV
└── crawl_all()          # Main crawl logic (2 levels)
```

### Flow Diagram

```
1. Read CRAWLER_TARGETS from env
2. For each target URL:
   ├── Level 1: Extract links + date
   ├── Filter by date (> DB_DATE)
   ├── For each link:
   │   ├── If file link → download
   │   └── If sub-page link:
   │       ├── Level 2: Extract sub-links
   │       └── Download files from Level 2
3. Save CSV & logs
4. Print summary
```

## Performance

- **Speed**: ~1-2 pages/second (với `DELAY_BETWEEN_REQUESTS=1.0`)
- **Storage**: ~100-500 MB cho 100 forms
- **Memory**: ~50-100 MB RAM

## Security

- ✅ No credentials stored in code
- ✅ Environment variables cho sensitive data
- ✅ GitHub Secrets cho CI/CD
- ✅ Respectful crawling (delays, User-Agent)
- ⚠️ Tuân thủ `robots.txt` của từng website

## Roadmap

- [ ] Playwright/Selenium support cho JavaScript-heavy sites
- [ ] OCR cho images/scanned PDFs
- [ ] Duplicate detection (checksum-based)
- [ ] Webhook notifications (Discord/Slack)
- [ ] S3/Cloud storage integration
- [ ] Form classification (ML-based)

## License

MIT License - Xem file `LICENSE` để biết thêm chi tiết.
