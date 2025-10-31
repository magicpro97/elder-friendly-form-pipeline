# Contributing to Elder-Friendly Form Pipeline

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Development Setup

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git
- Redis (for local development without Docker)

### Local Setup

1. **Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/fastapi_form_pipeline.git
cd fastapi_form_pipeline
```

2. **Create virtual environment**
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings (OPENAI_API_KEY is optional)
```

5. **Run Redis**
```bash
# Option 1: Docker
docker run -d -p 6379:6379 redis:7-alpine

# Option 2: Local installation
redis-server
```

6. **Run application**
```bash
uvicorn app:app --reload --port 8000
```

## Running Tests

### All Tests
```bash
pytest tests/ -v --cov=. --cov-report=term --cov-report=html
```

### Specific Test File
```bash
pytest tests/test_validation.py -v
```

### With Coverage Report
```bash
pytest tests/ --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

## Code Style

### Linting
```bash
# Install linters
pip install flake8 black isort

# Check syntax errors
flake8 app.py --count --select=E9,F63,F7,F82 --show-source --statistics

# Format code
black app.py

# Sort imports
isort app.py
```

### Vietnamese Code Comments
- Use Vietnamese for user-facing strings
- Use English for code comments and docstrings
- Maintain respectful tone ("bác"/"cháu") in Vietnamese messages

## Contribution Workflow

### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Changes
- Write tests for new features
- Update documentation if needed
- Follow existing code patterns
- Maintain >80% test coverage

### 3. Commit Changes
```bash
# Use conventional commits
git commit -m "feat: add new form type"
git commit -m "fix: resolve session expiration bug"
git commit -m "docs: update API documentation"
git commit -m "test: add validation tests"
```

Commit types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding/updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

### 4. Push and Create PR
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub with:
- Clear description of changes
- Reference to related issues
- Screenshots (if UI changes)
- Test results

## Testing Guidelines

### Writing Tests
```python
# tests/test_example.py
import pytest
from app import your_function

def test_your_function_valid_input():
    """Test function with valid input."""
    result = your_function("valid_input")
    assert result is not None
    assert result["status"] == "success"

def test_your_function_invalid_input():
    """Test function with invalid input."""
    with pytest.raises(ValueError):
        your_function("invalid_input")
```

### Test Structure
- Use descriptive test names
- One assertion per test when possible
- Use fixtures for common setup
- Mock external dependencies (OpenAI, Redis)

### Coverage Requirements
- Minimum 80% overall coverage
- 100% coverage for critical paths (validation, session management)
- All new features must include tests

## Adding New Forms

1. **Update `forms/form_samples.json`**
```json
{
  "form_id": "new_form",
  "title": "Form Title",
  "aliases": ["keyword1", "keyword2"],
  "fields": [
    {
      "id": "field_name",
      "label": "Vietnamese label",
      "type": "text",
      "required": true,
      "normalizers": ["strip_spaces", "title_case"],
      "validators": [
        {"type": "length", "min": 2, "max": 100}
      ]
    }
  ]
}
```

2. **Add tests**
```python
# tests/test_forms.py
def test_pick_new_form():
    """Test new form selection."""
    form = pick_form("keyword1")
    assert form["form_id"] == "new_form"
```

3. **Test both modes**
- With OpenAI API key (full functionality)
- Without OpenAI API key (fallback mode)

## Docker Development

### Build and Test
```bash
# Build image
docker build -t form-pipeline .

# Run container
docker run -p 8000:8000 --env-file .env form-pipeline

# With docker-compose
docker-compose up --build
```

### Testing in Docker
```bash
# Run tests in container
docker-compose run app pytest tests/ -v

# Check logs
docker-compose logs -f app
```

## CI/CD Pipeline

The GitHub Actions workflow runs on every push and PR:

1. **Lint & Test**: Pytest with coverage
2. **Security Scan**: Trivy vulnerability scanning
3. **Build**: Docker image creation
4. **Deploy**: Automatic deployment on main branch

Ensure all checks pass before requesting review.

## Documentation

### Update When Changing:
- **README.md**: Feature changes, setup instructions
- **DEPLOYMENT.md**: Production deployment steps
- **.github/copilot-instructions.md**: Code patterns, architecture
- **Docstrings**: Function/class documentation

### Documentation Style
```python
def validate_field(value: str, field: dict) -> tuple[bool, str, str]:
    """
    Validate field value against field rules.

    Args:
        value: User input to validate
        field: Field definition with validators

    Returns:
        Tuple of (is_valid, error_message, normalized_value)

    Raises:
        ValueError: If field definition is invalid
    """
```

## Getting Help

- **Issues**: Create GitHub issue with bug/feature template
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check README.md and copilot-instructions.md

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help newcomers get started

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
