# Contributing to Agent Skills

Thank you for your interest in contributing! This repo collects AI agent skills built for [Hermes Agent](https://hermes-agent.nousresearch.com), but the workflows and scripts are agent-agnostic — contributions that improve portability are welcome.

## Repository structure

Each skill lives in its own folder under a domain directory (`creative/`, `research/`, `mlops/`, `web-scraping/`, `productivity/`). A skill folder contains:

- `SKILL.md` — the main instruction file with YAML frontmatter
- `scripts/` — deterministic Python scripts (pure stdlib where possible)
- `references/` — deeper material loaded on demand
- `examples/` — runnable worked examples
- `tests/` — pytest test suite
- `templates/` — output templates (optional)

## Skill conventions

### SKILL.md frontmatter

Every skill must have this frontmatter:

```yaml
---
name: my-skill
description: >
  Clear description of what the skill does and when to use it.
version: 1.0.0
author: your-name
license: MIT
platforms: [linux, macos, windows]
---
```

### Design principles

1. **Deterministic scripts for computable tasks, LLM for judgment only** — if something can be a script, make it a script.
2. **Pure stdlib where possible** — avoid pip dependencies unless necessary. If you need them, declare in `requirements.txt` and `requirements-dev.txt`.
3. **Agent-agnostic** — use generic tool names or document the mapping. Don't hardcode platform-specific paths.
4. **Self-contained** — each skill folder should work independently. No cross-skill imports unless documented.
5. **Cost-aware** — if a skill calls paid APIs, include `--dry-run` support and cost estimates.

### Tests

- Every script with non-trivial logic should have tests in `tests/`.
- Tests must pass with plain `pytest` (the repo `pyproject.toml` configures `--import-mode=importlib`).
- Use synthetic fixtures — never real API keys or PII in tests.

## How to contribute

1. **Fork & clone** the repo.
2. **Create a branch** — `feat/my-new-skill` or `fix/some-issue`.
3. **Add or modify skills** following the conventions above.
4. **Run tests** — `python3 -m pytest` from the repo root. All tests must pass.
5. **Check for secrets** — ensure no API keys, tokens, or personal data are committed.
6. **Submit a pull request** with a clear description of what the skill does and why it belongs here.

## Pull request checklist

- [ ] SKILL.md has all required frontmatter fields
- [ ] Scripts compile (`python3 -m py_compile scripts/*.py`)
- [ ] Tests pass (`python3 -m pytest`)
- [ ] No secrets or PII in the diff
- [ ] No hardcoded local paths (use `~` or env vars)
- [ ] New dependencies declared in `requirements.txt` if needed

## Reporting issues

Use [GitHub Issues](https://github.com/moonlight-lupin/agent_skills/issues) to report bugs, request new skills, or suggest improvements.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).