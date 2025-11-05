"""
Unit tests for Vietnamese Form Crawler
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.vietnamese_form_crawler import VietnameseFormCrawler


@pytest.fixture
def crawler():
    """Create a crawler instance for testing"""
    with patch("src.vietnamese_form_crawler.SAVE_CSV", False):
        return VietnameseFormCrawler()


@pytest.fixture
def mock_response_vietnamese():
    """Mock HTTP response with Vietnamese content"""
    mock = Mock()
    mock.status_code = 200
    mock.text = """
    <html>
        <head><title>Mẫu đơn đăng ký biến động đất đai</title></head>
        <body>
            <div>Ngày đăng: 15/01/2024</div>
            <a href="/download/mau-don-dang-ky.pdf">Tải mẫu đơn</a>
            <a href="/huong-dan/dien-don">Hướng dẫn điền đơn</a>
            <a href="https://external.com/file.pdf">External file</a>
        </body>
    </html>
    """
    return mock


class TestVietnameseFormCrawler:
    """Test cases for VietnameseFormCrawler"""

    def test_initialization(self, crawler):
        """Test crawler initializes correctly"""
        assert crawler.session is not None
        assert crawler.total_downloaded == 0

    def test_parse_date_str_dd_mm_yyyy(self, crawler):
        """Test parsing dd/mm/yyyy format"""
        date = crawler._parse_date_str("15/01/2024")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_parse_date_str_yyyy_mm_dd(self, crawler):
        """Test parsing yyyy-mm-dd format"""
        date = crawler._parse_date_str("2024-01-15")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_parse_date_str_with_day_of_week(self, crawler):
        """Test parsing with Vietnamese day of week"""
        date = crawler._parse_date_str("Thứ Hai, 15/01/2024")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_parse_date_str_rejects_old_dates(self, crawler):
        """Test that dates before 2000 are rejected"""
        date = crawler._parse_date_str("15/01/1999")
        assert date is None

    def test_extract_date_from_html(self, crawler):
        """Test extracting date from HTML"""
        html = "Ngày đăng: 15/01/2024"
        date = crawler.extract_date(html)
        assert date is not None
        assert date.year == 2024

    def test_extract_date_returns_most_recent(self, crawler):
        """Test that most recent date is returned"""
        html = "Cập nhật: 10/01/2024, Đăng: 15/01/2024, Sửa: 12/01/2024"
        date = crawler.extract_date(html)
        assert date is not None
        assert date.day == 15  # Most recent

    @patch("src.vietnamese_form_crawler.VietnameseFormCrawler.session")
    def test_extract_form_links(self, mock_session, crawler, mock_response_vietnamese):
        """Test extracting links from Vietnamese page"""
        mock_session.get.return_value = mock_response_vietnamese

        links, date, title = crawler.extract_form_links("https://example.com")

        assert date is not None
        assert title == "Mẫu đơn đăng ký biến động đất đai"
        assert len(links) > 0

    @patch("src.vietnamese_form_crawler.VietnameseFormCrawler.session")
    def test_download_file(self, mock_session, crawler):
        """Test file download"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"PDF content"
        mock_session.get.return_value = mock_response

        with patch("builtins.open", create=True) as mock_open:
            success, filename = crawler.download_file(
                "https://example.com/mau-don.pdf", "Test Page", datetime(2024, 1, 15)
            )

        assert success is True
        assert filename == "mau-don.pdf"

    def test_file_extension_detection(self, crawler):
        """Test that only valid file extensions are accepted"""
        valid_files = ["mau-don.pdf", "bieu-mau.doc", "to-khai.xlsx"]

        for filename in valid_files:
            ext = next((e for e in crawler.FILE_EXTENSIONS if filename.endswith(e)), None)
            assert ext is not None

    @patch("src.vietnamese_form_crawler.CRITICAL_KEYWORDS", ["mẫu", "đơn"])
    def test_keyword_filtering(self, crawler):
        """Test that links are filtered by keywords"""
        from src.vietnamese_form_crawler import CRITICAL_KEYWORDS

        # Link with critical keyword should be accepted
        assert any(k in "mau-don.pdf" for k in CRITICAL_KEYWORDS)

        # Link without keyword should be rejected
        assert not any(k in "random-file.pdf" for k in CRITICAL_KEYWORDS)
