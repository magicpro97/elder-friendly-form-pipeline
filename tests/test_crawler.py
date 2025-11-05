"""
Unit tests for crawler module
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.crawler import Crawler


@pytest.fixture
def crawler():
    """Create a crawler instance for testing"""
    return Crawler()


@pytest.fixture
def mock_response():
    """Mock HTTP response"""
    mock = Mock()
    mock.status_code = 200
    mock.text = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <form action="/submit" method="post">
                <input type="text" name="name" required>
                <input type="email" name="email">
            </form>
            <a href="/page1">Link 1</a>
            <a href="/page2">Link 2</a>
        </body>
    </html>
    """
    return mock


class TestCrawler:
    """Test cases for Crawler class"""

    def test_crawler_initialization(self, crawler):
        """Test crawler is initialized correctly"""
        assert crawler.session is not None
        assert crawler.results == []
        assert "User-Agent" in crawler.session.headers

    @patch("src.crawler.requests.Session.get")
    def test_fetch_page_success(self, mock_get, crawler, mock_response):
        """Test successful page fetch"""
        mock_get.return_value = mock_response

        response = crawler.fetch_page("https://example.com")

        assert response is not None
        assert response.status_code == 200
        mock_get.assert_called_once()

    @patch("src.crawler.requests.Session.get")
    def test_fetch_page_retry_on_failure(self, mock_get, crawler):
        """Test retry logic on failed requests"""
        mock_get.side_effect = Exception("Connection error")

        response = crawler.fetch_page("https://example.com", retries=3)

        assert response is None
        assert mock_get.call_count == 3

    def test_parse_page(self, crawler, mock_response):
        """Test HTML parsing"""
        data = crawler.parse_page("https://example.com", mock_response.text)

        assert data["url"] == "https://example.com"
        assert data["title"] == "Test Page"
        assert data["status"] == "success"
        assert "crawled_at" in data
        assert len(data["forms"]) == 1
        assert data["forms"][0]["method"] == "POST"
        assert len(data["forms"][0]["inputs"]) == 2

    @patch("src.crawler.requests.Session.get")
    def test_crawl_target_success(self, mock_get, crawler, mock_response):
        """Test crawling a single target"""
        mock_get.return_value = mock_response

        result = crawler.crawl_target("https://example.com")

        assert result is not None
        assert result["status"] == "success"
        assert len(crawler.results) == 1

    @patch("src.crawler.requests.Session.get")
    def test_crawl_target_failure(self, mock_get, crawler):
        """Test crawling with failed request"""
        mock_get.side_effect = Exception("Connection error")

        result = crawler.crawl_target("https://example.com")

        assert result is not None
        assert result["status"] == "failed"
        assert "error" in result

    @patch("src.crawler.Crawler.crawl_target")
    @patch("src.crawler.CRAWLER_TARGETS", ["https://example1.com", "https://example2.com"])
    def test_crawl_all(self, mock_crawl_target, crawler):
        """Test crawling multiple targets"""
        mock_crawl_target.return_value = {"status": "success"}

        results = crawler.crawl_all()

        assert len(results) >= 0
        # crawl_target is called for each target
        assert mock_crawl_target.call_count == 2
