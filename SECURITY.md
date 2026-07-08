# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in this repository, please report it responsibly:

1. **Do not** open a public GitHub issue.
2. Email the repository owner via GitHub's security advisory feature:
   - Go to the **Security** tab → **Advisories** → **Report a vulnerability**
   - Or visit: https://github.com/moonlight-lupin/agent_skills/security/advisories/new
3. Include a description of the vulnerability, steps to reproduce, and potential impact.

You will receive a response within 72 hours. Please do not disclose the vulnerability publicly until it has been addressed.

## What to report

- Secrets or credentials accidentally committed to the repository
- Scripts that execute arbitrary code from untrusted input without sanitisation
- Skills that leak sensitive data (API keys, PII) in their output
- Any security issue in the skill workflows or scripts

## What NOT to report

- Issues with third-party APIs or services that skills call (report to the API provider)
- Skill behaviour that is explicitly documented as out of scope
- Questions about configuration or usage (use GitHub Issues instead)

## Credential safety

This repository follows a strict no-secrets policy:

- `.env` files, API keys, tokens, and credentials are gitignored
- Skills read secrets from environment variables, never from committed files
- Tests use synthetic data only — no real API keys or PII
- If you accidentally commit a secret, **rotate it immediately** — git history is permanent