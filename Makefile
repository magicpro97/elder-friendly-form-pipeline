.PHONY: help build up down restart logs clean install install-dev test lint format dev redis pre-commit

help:
	@echo "Elder-Friendly Form Pipeline - Development Commands"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build       - Build Docker images"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make restart     - Restart all services"
	@echo "  make logs        - View application logs"
	@echo "  make clean       - Remove containers and volumes"
	@echo ""
	@echo "Development Commands:"
	@echo "  make install     - Install Python dependencies"
	@echo "  make install-dev - Install dev dependencies + setup pre-commit"
	@echo "  make dev         - Run app locally (requires Redis)"
	@echo "  make redis       - Start Redis container for local dev"
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run linting checks"
	@echo "  make format      - Format code with black and isort"
	@echo "  make pre-commit  - Run pre-commit hooks on all files"
	@echo ""
	@echo "Crawler Commands:"
	@echo "  make crawler-install  - Install crawler dependencies"
	@echo "  make crawler-test     - Test crawler locally (single URL)"
	@echo "  make crawler-run      - Run crawler with full config"
	@echo "  make crawler-results  - View crawler results"
	@echo "  make crawler-clean    - Clean crawler output"
	@echo ""
	@echo "Form Processing Commands:"
	@echo "  make forms-process    - Process crawled files → JSON"
	@echo "  make forms-merge      - Merge manual + crawled forms"
	@echo "  make forms-search Q=  - Search forms (e.g., Q='đơn xin việc')"
	@echo "  make forms-list       - List all forms"
	@echo "  make forms-pipeline   - Run full pipeline (process + merge)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make backup      - Backup Redis data"
	@echo "  make ps          - Show running containers"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started. App running at http://localhost:8000"

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f app

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pre-commit install
	@echo "✅ Development environment setup complete!"
	@echo "Pre-commit hooks installed - will run automatically on git commit"

dev:
	uvicorn app:app --reload --port 8000

redis:
	docker run -d -p 6379:6379 --name redis-dev redis:7-alpine

test:
	pytest tests/ -v --cov=. --cov-report=term --cov-report=html

test-fast:
	pytest tests/ -v

lint:
	@echo "Running flake8..."
	flake8 app.py tests/ --max-line-length=120 --ignore=E501,W503,E203
	@echo "Running ruff..."
	ruff check app.py tests/
	@echo "Running mypy..."
	mypy app.py --ignore-missing-imports --no-strict-optional
	@echo "Checking black formatting..."
	black --check app.py tests/
	@echo "Checking isort..."
	isort --check-only app.py tests/

format:
	@echo "Formatting with black..."
	black app.py tests/
	@echo "Sorting imports with isort..."
	isort app.py tests/
	@echo "Auto-fixing with ruff..."
	ruff check --fix app.py tests/
	@echo "✅ Code formatted successfully!"

pre-commit:
	pre-commit run --all-files

backup:
	@mkdir -p backup
	docker exec fastapi_form_redis redis-cli BGSAVE
	@sleep 2
	docker cp fastapi_form_redis:/data/dump.rdb backup/dump-$$(date +%Y%m%d-%H%M%S).rdb
	@echo "Backup created in backup/ directory"

ps:
	docker-compose ps

shell:
	docker exec -it fastapi_form_app /bin/bash

redis-cli:
	docker exec -it fastapi_form_redis redis-cli

# Crawler commands
crawler-install:
	pip install -r requirements-crawler.txt

crawler-test:
	python3 test_crawler_local.py

crawler-run:
	python3 src/vietnamese_form_crawler.py

crawler-results:
	@echo "=== CSV Results ==="
	@cat crawler_output/downloaded_files.csv 2>/dev/null || echo "No CSV file found"
	@echo ""
	@echo "=== Downloaded Files ==="
	@ls -lh crawler_output/*.{pdf,doc,docx,xlsx,xls} 2>/dev/null || echo "No files downloaded"
	@echo ""
	@echo "=== Recent Logs ==="
	@tail -20 crawler_output/crawler.log 2>/dev/null || echo "No log file found"

crawler-clean:
	rm -rf crawler_output/*
	mkdir -p crawler_output

# OCR commands
ocr-deps-mac:
	@echo "Installing OCR dependencies for macOS..."
	brew install tesseract tesseract-lang poppler
	@echo "✅ Tesseract, Vietnamese language pack, and poppler installed"

ocr-deps-ubuntu:
	@echo "Installing OCR dependencies for Ubuntu..."
	sudo apt-get update
	sudo apt-get install -y tesseract-ocr tesseract-ocr-vie poppler-utils
	@echo "✅ OCR dependencies installed"

ocr-test:
	@echo "Testing OCR on downloaded files..."
	python3 test_ocr_validator.py

ocr-test-file:
	@echo "Usage: make ocr-test-file FILE=<path>"
	@test -n "$(FILE)" || (echo "Error: FILE parameter required" && exit 1)
	python3 src/ocr_validator.py $(FILE)

ocr-validate-all:
	@echo "Validating all downloaded files..."
	@for f in crawler_output/*.{pdf,doc,docx,jpg,png}; do \
		if [ -f "$$f" ]; then \
			echo "Validating $$f..."; \
			python3 src/ocr_validator.py "$$f" 2>&1 | grep -E "(VALID|confidence|keywords_found)"; \
			echo ""; \
		fi \
	done

# Form processing commands
forms-process:
	@echo "Processing crawled files into structured forms..."
	python3 src/form_processor.py --input crawler_output --output forms/crawled_forms
	@echo "✅ Forms processed. Check forms/crawled_forms/"

forms-merge:
	@echo "Merging manual and crawled forms..."
	python3 src/form_merger.py
	@echo "✅ Forms merged. Check forms/all_forms.json"

forms-search:
	@test -n "$(Q)" || (echo "Usage: make forms-search Q='query'" && exit 1)
	python3 src/form_search.py "$(Q)"

forms-list:
	@echo "Listing all forms..."
	python3 src/form_search.py --list

forms-list-crawled:
	@echo "Listing crawled forms only..."
	python3 src/form_search.py --list --source crawler

forms-list-manual:
	@echo "Listing manual forms only..."
	python3 src/form_search.py --list --source manual

forms-pipeline:
	@echo "Running full form processing pipeline..."
	@echo "Step 1/2: Processing crawled files..."
	python3 src/form_processor.py --input crawler_output --output forms/crawled_forms
	@echo ""
	@echo "Step 2/2: Merging forms..."
	python3 src/form_merger.py
	@echo ""
	@echo "✅ Pipeline complete!"
	@echo "   - Crawled forms: forms/crawled_forms/"
	@echo "   - Merged index: forms/all_forms.json"
	@echo ""
	@echo "Try: make forms-search Q='đơn xin việc'"

forms-clean:
	@echo "Cleaning processed forms..."
	rm -rf forms/crawled_forms/*
	rm -f forms/all_forms.json
	@echo "✅ Cleaned"
