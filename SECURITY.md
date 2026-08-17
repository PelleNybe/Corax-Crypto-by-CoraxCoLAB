# Security Policy

## Reporting a Vulnerability

We take the security of the Corax-Crypto project seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**Please do not open public GitHub issues for security vulnerabilities.**

Instead, please email your findings to: [Your contact email]

Include:
- Description of the vulnerability
- Steps to reproduce (if applicable)
- Potential impact
- Suggested fix (if available)

## Security Update Timeline

We aim to:
- Acknowledge vulnerability reports within 48 hours
- Provide an initial assessment within 5 days
- Release a patch or mitigation plan within 30 days for critical vulnerabilities

## Supported Versions

| Version | Status | Support Until |
|---------|--------|---|
| 0.1.x   | Current | Active |
| < 0.1   | Unsupported | N/A |

## Security Best Practices

### For Users
- Keep dependencies updated using `poetry update`
- Review dependency security advisories regularly
- Follow the project's security announcements

### For Developers
- Never commit secrets or API keys
- Use `python-dotenv` for local configuration
- Follow the contribution guidelines
- Perform security code reviews before merging

## Dependency Management

This project uses:
- **Poetry** for dependency management
- **Dependabot** for automated version updates
- **CodeQL** for security scanning
- **GitHub security scanning** for vulnerability detection

## Responsible Disclosure

We appreciate responsible disclosure and will acknowledge your contribution once the issue is resolved.
