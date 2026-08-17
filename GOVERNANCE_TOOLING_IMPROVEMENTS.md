# Repository Governance & Tooling Improvements

## Summary

This document describes the governance, CI/CD, and development tooling improvements added to the Corax-Crypto project.

**Commit:** `2a8e8af` | **Date:** 2024-08-17 | **Files Added:** 9 new files, 1 modified

## Files Added

### 1. Security & Governance Documentation

#### `SECURITY.md`
- Establishes vulnerability reporting process
- Defines security update timeline (48h acknowledgment, 5d assessment, 30d patch)
- Documents supported versions
- Provides security best practices for users and developers
- **Impact:** Enables responsible disclosure and security cooperation

#### `CONTRIBUTING.md`
- Provides comprehensive development setup guide
- Documents code style guidelines (PEP 8, 100 char line length)
- Explains testing workflow (`poetry run pytest`)
- Defines commit message conventions (Conventional Commits)
- Details PR review process and code standards
- **Impact:** Streamlines onboarding and maintains code consistency

#### `CODE_OF_CONDUCT.md`
- Adopts Contributor Covenant standards
- Establishes community expectations
- Defines enforcement process for violations
- **Impact:** Creates safe, inclusive community environment

### 2. Automated Issue & PR Management

#### `.github/dependabot.yml`
- **Scope:** Automated dependency updates
- **Frequency:** Weekly (Mondays at 3 AM UTC)
- **Coverage:** 
  - pip dependencies (up to 10 PRs open)
  - GitHub Actions
- **Labels:** dependencies, python, ci
- **Commit Format:** Conventional commits (`chore(deps):`, `ci:`)
- **Reviewers:** PelleNybe
- **Impact:** Reduces manual dependency management burden, keeps deps up-to-date

#### `.github/ISSUE_TEMPLATE/bug_report.md`
- Structured bug report template
- Enforces required fields: description, reproduction steps, expected behavior, environment
- Includes error log section and confirmation checkboxes
- **Impact:** Improves bug report quality and clarity

#### `.github/ISSUE_TEMPLATE/feature_request.md`
- Structured feature request template
- Captures: description, motivation, implementation, alternatives
- Confirmation that user searched existing requests
- **Impact:** Streamlines feature request evaluation process

#### `.github/pull_request_template.md`
- PR description structure
- Type of change classification (bug/feature/breaking/docs)
- Issue linking and testing instructions
- Checklist for completeness (code review, tests, documentation, etc.)
- **Impact:** Ensures comprehensive PR reviews and complete changesets

### 3. Pre-Commit Hooks Configuration

#### `.pre-commit-config.yaml`
- **Code Formatting:**
  - Black (line length: 100)
  - isort (import sorting with black profile)
- **Linting:** 
  - flake8 (with extended ignores)
  - Ruff (fast linting)
- **Type Checking:** 
  - mypy (with type-all dependencies)
- **Security:** 
  - bandit (security vulnerability scanning)
- **Quality:**
  - interrogate (docstring coverage, 50% threshold)
- **General Checks:**
  - YAML validation
  - Merge conflict detection
  - Private key detection
  - File ending and trailing whitespace fixes

**Installation:**
```bash
pip install pre-commit
pre-commit install
# Run manually: pre-commit run --all-files
```

**Impact:** Catches issues before commit, enforces consistency automatically

### 4. Development Tool Configuration

#### `pyproject.toml` (Enhanced)
Added comprehensive tool configurations:

**[tool.black]**
- Line length: 100
- Target Python: 3.10, 3.11, 3.12
- Excludes: venv, .git, __pycache__, dist, etc.

**[tool.isort]**
- Profile: black-compatible
- Line length: 100
- Known first-party packages: core, data_engine, execution, intelligence, schemas, ui
- Skip venv, git, build directories

**[tool.pytest.ini_options]**
- Test discovery: tests/ directory, test_*.py files
- Async mode: auto
- Markers: unit, integration, slow, asyncio
- Strict marker validation
- Filter deprecation warnings

**[tool.coverage.run]**
- Branch coverage enabled
- Sources: core, data_engine, execution, intelligence, schemas, ui
- Omits: tests, __init__.py, venv

**[tool.coverage.report]**
- Excludes: pragma, representations, assertions, __main__, type checking
- Precision: 2 decimal places
- Shows missing lines

**[tool.mypy]**
- Python version: 3.10
- Strict optional checking
- Return type warnings
- Detailed error reporting
- Ignores missing imports (optional library stubs)
- Test overrides: lenient

**[tool.ruff]**
- Fast Python linter (Rust-based)
- Line length: 100
- Rules: E/W (pycodestyle), F (Pyflakes), I (isort), etc.
- Ignores: E501 (line too long), E203, W503

**[tool.bandit]**
- Security scanning configuration
- Excludes: tests, venv, build directories
- Skips: B101 (assert_used - OK in tests)

**Added Dev Dependencies:**
- black 24.1.0+
- isort 5.13.0+
- flake8 7.0.0+
- mypy 1.8.0+
- bandit 1.7.5+
- interrogate 1.5.0+
- ruff 0.1.8+

## Development Workflow Improvements

### Before
- No structured issue/PR templates
- Manual dependency management
- No automated code quality checks
- No security scanning pre-commit
- No standard for code style/type checking

### After
1. **Contributors** follow structured process with issue/PR templates
2. **Dependabot** automatically creates PRs for updates (weekly)
3. **Pre-commit hooks** catch issues before commit (locally)
4. **Code quality** enforced by: black, isort, flake8, mypy, bandit
5. **Tests** run with pytest in async mode with coverage tracking
6. **Security** scanning via bandit for vulnerability patterns

## Integration Points

### GitHub Actions
- CodeQL workflow (existing) continues Python-only analysis
- Dependabot workflow (new) creates automated update PRs
- User must go to Settings → Code Security → CodeQL to disable automatic config

### Local Development
```bash
# Setup
poetry install --with dev --with test
pre-commit install

# Before commit
pre-commit run --all-files
poetry run pytest --cov=.

# Code formatting
poetry run black .
poetry run isort .

# Type checking
poetry run mypy core data_engine execution intelligence schemas
```

### CI/CD Pipeline
- CodeQL scans on push/PR/weekly schedule
- Dependabot creates PRs weekly
- Contributors use issue/PR templates
- Code review checklist guides reviewers

## Vulnerabilities Detected

GitHub security scanner detected 10 vulnerabilities (8 high, 2 moderate):
- See: https://github.com/PelleNybe/Corax-Crypto-by-CoraxCoLAB/security/dependabot
- Dependabot will create PRs to address these automatically

## Next Steps

1. **Immediate (Recommended):**
   - Install pre-commit: `pip install pre-commit && pre-commit install`
   - Run tests locally: `poetry run pytest --cov=.`
   - Review Dependabot PRs as they arrive

2. **Short-term (GitHub Settings):**
   - Go to Settings → Code Security → CodeQL
   - Disable "Enable CodeQL" to use only explicit workflow
   - New CodeQL runs will use Python-only configuration

3. **Optional Enhancements:**
   - Monitor CodeQL analysis results
   - Review Dependabot PRs for compatibility
   - Adjust tool configurations based on team preferences
   - Add branch protection rules (require reviews, pass checks)

## Files Modified

```
Modified: pyproject.toml
- Added dev dependencies for tools
- Added 8 [tool.*] configuration sections
- 150+ lines of configuration added
```

## Benefits Summary

| Area | Benefit |
|------|---------|
| **Security** | Bandit scanning, Dependabot updates, CodeQL analysis |
| **Quality** | Black formatting, isort imports, mypy types, flake8 linting |
| **Automation** | Pre-commit hooks, Dependabot PRs, issue templates |
| **Testing** | Pytest configuration, coverage tracking, async support |
| **Documentation** | SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md |
| **Governance** | Issue/PR templates, Dependabot config, PR checklist |

## References

- Conventional Commits: https://www.conventionalcommits.org/
- Contributor Covenant: https://www.contributor-covenant.org/
- Black: https://black.readthedocs.io/
- pytest: https://docs.pytest.org/
- Dependabot: https://docs.github.com/en/code-security/dependabot
- Pre-commit: https://pre-commit.com/
