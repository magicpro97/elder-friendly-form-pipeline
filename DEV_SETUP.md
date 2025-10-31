# Development Setup Guide

## Quick Start

### 1. Setup Virtual Environment
```bash
# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
```

### 2. Install Dependencies
```bash
# Install dev dependencies + setup pre-commit hooks
make install-dev

# Or manually:
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
```

### 3. Start Development
```bash
# Start Redis
make redis

# Run app locally
make dev
```

## Pre-commit Hooks

Pre-commit hooks automatically run before each commit to ensure code quality.

### What runs automatically:
- ✅ **Black** - Code formatting (line length 120)
- ✅ **isort** - Import sorting
- ✅ **Ruff** - Fast linting + auto-fixes
- ✅ **Flake8** - Additional linting
- ✅ **MyPy** - Type checking
- ✅ **Trailing whitespace** removal
- ✅ **End of file** fixer
- ✅ **YAML/JSON** validation

### Manual Commands

```bash
# Format code manually
make format

# Run linting checks
make lint

# Run pre-commit on all files
make pre-commit

# Run specific hook
pre-commit run black --all-files
```

## VS Code Integration

The `.vscode/settings.json` automatically:
- Formats on save with Black
- Organizes imports on save
- Fixes lint issues on save
- Shows type hints with Pylance

## Git Workflow

```bash
# 1. Make your changes
vim app.py

# 2. Stage files
git add app.py

# 3. Commit (pre-commit hooks run automatically)
git commit -m "feat: add new feature"

# If hooks fail, they'll auto-fix most issues
# Just re-stage and commit again:
git add app.py
git commit -m "feat: add new feature"
```

## Bypassing Hooks (Not Recommended)

```bash
# Skip pre-commit hooks (emergency only!)
git commit --no-verify -m "urgent fix"
```

## Configuration Files

- **`.pre-commit-config.yaml`** - Pre-commit hooks configuration
- **`pyproject.toml`** - Tool configurations (black, isort, ruff, mypy, pytest)
- **`.vscode/settings.json`** - VS Code editor settings
- **`requirements-dev.txt`** - Development dependencies

## Testing

```bash
# Run all tests with coverage
make test

# Run tests without coverage (faster)
make test-fast

# Run specific test file
pytest tests/test_api.py -v
```

## Troubleshooting

### Pre-commit hooks not running?
```bash
# Reinstall hooks
pre-commit install

# Update hooks to latest versions
pre-commit autoupdate
```

### Black/Ruff conflicts?
The configuration in `pyproject.toml` ensures compatibility between tools.

### Want to disable a specific hook?
Edit `.pre-commit-config.yaml` and comment out the hook or add to `exclude:` pattern.
