# Contributing to Corax-Crypto

Thank you for your interest in contributing to the Corax-Crypto project! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Poetry 2.4.1 or higher
- Git

### Development Setup

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Corax-Crypto-by-CoraxCoLAB.git
   cd Corax-Crypto-by-CoraxCoLAB
   ```

2. **Install dependencies**
   ```bash
   poetry install
   poetry install --with dev --with test
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Code Style

- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Maximum line length: 100 characters

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=.

# Run specific test file
poetry run pytest tests/test_specific.py
```

### Pre-commit Checks

Before committing, ensure:
- Code passes all tests
- No import errors
- Code follows style guidelines
- No security issues

## Making Changes

### Commit Messages

Follow conventional commits format:

```
type(scope): subject

body

footer
```

**Types:**
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring without feature changes
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Dependency updates, build configuration
- `ci`: CI/CD configuration changes

**Example:**
```
feat(execution): add new arbitrage engine

- Implement core arbitrage detection
- Add risk management checks
- Include unit tests

Closes #123
```

### Pull Requests

1. **Create a descriptive PR title** following conventional commits
2. **Write a clear PR description**
   - What changes were made?
   - Why were they needed?
   - How to test the changes?
3. **Link related issues** using `Closes #issue_number`
4. **Ensure all checks pass**
   - CodeQL analysis
   - Test suite
   - Code coverage

### Code Review Process

- PRs require at least one approval
- Address reviewer comments constructively
- Push additional commits to address feedback
- Don't force-push after review has started

## Documentation

- Update README.md for user-facing changes
- Add docstrings for new functions/classes
- Update relevant docs in `/docs` folder
- Include examples for complex features

## Security

- Never commit secrets, API keys, or passwords
- Use `.env` files for local configuration
- Report security vulnerabilities via SECURITY.md
- Follow security best practices in code reviews

## Questions?

- Open a GitHub Discussion for questions
- Check existing issues and PRs before asking
- Review the main README.md and docs

Thank you for contributing!
