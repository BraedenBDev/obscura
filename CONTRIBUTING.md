# Contributing to Obscura

Thanks for your interest in contributing to Obscura! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch from `main`
4. Make your changes
5. Submit a pull request

## Development Setup

### Backend (Python)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Chrome Extension

```bash
cd extension
bun install  # or: npm install
```

Load the extension in Chrome:
1. Navigate to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `extension/` directory

## Running Tests

### Backend

```bash
cd backend
source venv/bin/activate
python -m pytest tests/ -v
python -m pytest tests/ --cov=obscura --cov-report=term-missing
```

### Extension

```bash
cd extension
bun test              # Unit tests
bun test --coverage   # With coverage
bun run test:e2e      # End-to-end tests
```

## Pull Request Process

1. Ensure all tests pass before submitting
2. Update documentation if your changes affect user-facing behavior
3. Follow existing code style and patterns
4. Write clear commit messages (imperative mood: "Add feature" not "Added feature")
5. Keep PRs focused — one feature or fix per PR

## Code Style

### Python
- Follow PEP 8
- Use type hints for function signatures
- Docstrings for public functions and classes

### JavaScript
- ES module syntax (`import`/`export`) for core modules
- Descriptive variable names
- Comments for non-obvious logic

## Reporting Issues

- Use the GitHub issue templates (Bug Report or Feature Request)
- Include your environment details (OS, Chrome version, Python version)
- For bugs, include steps to reproduce

## Security

If you discover a security vulnerability, please report it responsibly via GitHub's private vulnerability reporting feature rather than opening a public issue.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
