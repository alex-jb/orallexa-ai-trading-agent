# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. Email: [create a private security advisory](https://github.com/alex-jb/orallexa-ai-trading-agent/security/advisories/new)
3. Include: description, steps to reproduce, potential impact

We will respond within 48 hours and work on a fix.

## Scope

| In Scope | Out of Scope |
|----------|-------------|
| API server authentication bypass | Trading strategy performance |
| Secret leakage in code/logs | UI cosmetic issues |
| Injection vulnerabilities (SQL/XSS/SSRF) | Feature requests |
| Sandbox escape in strategy evolver | Third-party dependency CVEs (report upstream) |

## Best Practices

- Never commit API keys or secrets to the repository
- Use `.env` files (gitignored) for local secrets
- The strategy evolver sandbox restricts `__builtins__` and blocks file I/O
- All user inputs are validated before processing
