# Crawler Module

## Overview

Daily crawler for monitoring form-related resources, scraping government websites, or performing health checks.

## Configuration

### Environment Variables

Create/update `.env` file:

```bash
# Crawler targets (comma-separated URLs)
CRAWLER_TARGETS=https://example.com/forms,https://another.com/resources

# Request settings
USER_AGENT=Mozilla/5.0 (compatible; ElderFormCrawler/1.0)
REQUEST_TIMEOUT=30
MAX_RETRIES=3
DELAY_BETWEEN_REQUESTS=1.0

# Output settings
SAVE_HTML=false
SAVE_JSON=true
OUTPUT_FORMAT=json

# Logging
LOG_LEVEL=INFO
```

### GitHub Secrets (for Actions)

Add in repository Settings → Secrets → Actions:

- `CRAWLER_TARGETS`: Comma-separated URLs to crawl

## Usage

### Local Execution

```bash
# Install crawler dependencies
pip install -r requirements-crawler.txt

# Set environment variables
export CRAWLER_TARGETS="https://example.com,https://another.com"

# Run crawler
python src/crawler.py
```

### GitHub Actions

Crawler runs automatically:

- **Daily at 2:00 AM UTC** (9:00 AM Vietnam time)
- **Manual trigger**: Go to Actions → Daily Crawler → Run workflow

### Customization

#### Custom Parsing Logic

Edit `src/crawler.py` → `Crawler.parse_page()` method:

```python
def parse_page(self, url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    # Your custom extraction logic
    data = {
        "url": url,
        "custom_field": soup.find("div", class_="target-class").text
    }

    return data
```

## Output

### File Structure

```
crawler_output/
├── crawler.log                         # Execution logs
├── crawl_results_20240101_020000.json  # Crawl results
└── example.com_20240101_020000.html    # Raw HTML (if SAVE_HTML=true)
```

### Result Format

```json
{
  "crawled_at": "2024-01-01T02:00:00",
  "total_targets": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "url": "https://example.com",
      "title": "Example Form Site",
      "status": "success",
      "crawled_at": "2024-01-01T02:00:00",
      "links": [...],
      "forms": [...]
    }
  ]
}
```

## Use Cases

### 1. Government Form Monitoring

```bash
CRAWLER_TARGETS="https://dangky.gov.vn,https://thuetncn.gdt.gov.vn"
```

Monitor for form updates or changes.

### 2. Health Check

```bash
CRAWLER_TARGETS="https://your-production-app.com/health"
```

Daily uptime monitoring.

### 3. Data Collection

Customize `parse_page()` to extract specific data from target sites.

## Testing

```bash
# Run crawler tests
pytest tests/test_crawler.py -v

# Run with coverage
pytest tests/test_crawler.py --cov=src.crawler
```

## Troubleshooting

### "All retries failed"

- Check target URL is accessible
- Verify `REQUEST_TIMEOUT` is sufficient
- Check network connectivity in GitHub Actions

### "Import errors"

- Ensure `requirements-crawler.txt` is installed
- Check `PYTHONPATH` includes project root

### Rate Limiting

Increase `DELAY_BETWEEN_REQUESTS` if getting rate-limited:

```bash
DELAY_BETWEEN_REQUESTS=2.0  # Wait 2 seconds between requests
```

## Advanced Features

### Selenium (JavaScript Rendering)

For sites requiring JavaScript:

```python
from selenium import webdriver

def fetch_page_with_selenium(self, url: str):
    driver = webdriver.Chrome()
    driver.get(url)
    html = driver.page_source
    driver.quit()
    return html
```

### Scrapy (Large-scale Crawling)

For complex multi-page crawls, consider using Scrapy framework (included in requirements-crawler.txt).

## Security Notes

- Never commit `.env` with real credentials
- Use GitHub Secrets for sensitive URLs
- Respect robots.txt and rate limits
- Add User-Agent to identify your crawler
