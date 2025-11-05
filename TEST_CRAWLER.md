# Test Crawler Locally - Quick Guide

## ✅ Đã test thành công

Crawler đã được test và hoạt động tốt với luatsubaoho.com

### Kết quả test

- **Downloaded**: 5 files (4 .doc, 1 .jpg)
- **CSV generated**: ✅
- **Logs**: ✅
- **2-level crawling**: ✅
- **Date filtering**: ✅
- **Keyword matching**: ✅

## 🚀 Cách test trên local

### Bước 1: Activate virtual environment

```bash
source .venv/bin/activate
```

### Bước 2: Install dependencies (chỉ cần 1 lần)

```bash
pip install -r requirements-crawler.txt
```

### Bước 3: Run test

```bash
# Option 1: Quick test với single URL
python test_crawler_local.py

# Option 2: Test với custom URLs
CRAWLER_TARGETS="https://your-url.com" \
DB_DATE="2020-01-01" \
python src/vietnamese_form_crawler.py

# Option 3: Dùng Makefile
make crawler-test
```

### Bước 4: Xem kết quả

```bash
# View CSV
cat crawler_output/downloaded_files.csv

# List downloaded files
ls -lh crawler_output/*.{pdf,doc,docx,xlsx}

# View logs
tail -f crawler_output/crawler.log

# Hoặc dùng Makefile
make crawler-results
```

## 📊 Output mẫu

### CSV Format

```csv
Tieu_de_trang,Link_file,Ten_file,Dang_tep,Ngay_dang
"Mẫu đơn xin việc",https://...,mau-don.doc,.doc,2025-11-05
```

### Files Downloaded

```
crawler_output/
├── mau-don-phan-to.docx (24K)
├── mau-giay-cam-ket.doc (35K)
├── mau-to-khai-khai-tu.doc (44K)
└── downloaded_files.csv (1.5K)
```

## 🛠️ Makefile Commands

```bash
make crawler-install   # Install dependencies
make crawler-test      # Quick test
make crawler-run       # Full run
make crawler-results   # View results
make crawler-clean     # Clean output
```

## 🎯 Test URLs đã thử

### ✅ Hoạt động tốt

- `https://luatsubaoho.com/phapluat/mau-don-dang-ky-bien-dong-dat-dai-co-huong-dan-cach-viet/`
- Crawl được 5 files (.doc, .docx, .jpg)
- Date parsing OK
- 2-level crawling OK

### ❌ Bị chặn (403 Forbidden)

- `https://thuvienphapluat.vn/*` - Cloudflare protection mạnh

### 💡 Gợi ý

Một số websites có anti-bot mạnh (Cloudflare, reCAPTCHA). Nếu gặp lỗi 403:

1. Thử URL khác
2. Tăng delay: `DELAY_BETWEEN_REQUESTS=3.0`
3. Dùng Selenium (chậm hơn nhưng bypass được JS)

## 🔧 Troubleshooting

### Lỗi: "No files downloaded"

```bash
# Giảm date cutoff
DB_DATE=2020-01-01 python test_crawler_local.py
```

### Lỗi: "403 Forbidden"

```bash
# Test với URL khác
# Hoặc tăng delay
DELAY_BETWEEN_REQUESTS=5.0 python src/vietnamese_form_crawler.py
```

### Lỗi: "Import bs4 not found"

```bash
source .venv/bin/activate
pip install -r requirements-crawler.txt
```

## ✨ Next Steps

Sau khi test OK trên local:

1. Commit code: `git add . && git commit -m "Test crawler OK"`
2. Push: `git push origin main`
3. GitHub Action sẽ tự động chạy daily lúc 2AM UTC

Hoặc trigger manual:

- Vào GitHub Actions tab
- Chọn "Daily Crawler"
- Click "Run workflow"

## 📝 Notes

- Virtual env: `.venv/` (đã có sẵn trong project)
- Output: `crawler_output/`
- Config: `.env` hoặc environment variables
- Logs: `crawler_output/crawler.log`
