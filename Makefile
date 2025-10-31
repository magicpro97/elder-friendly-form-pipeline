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
