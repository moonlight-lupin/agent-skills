# Agent Skills

[![Tests](https://github.com/moonlight-lupin/agent_skills/actions/workflows/test.yml/badge.svg)](https://github.com/moonlight-lupin/agent_skills/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

A collection of AI agent skills built for [Hermes Agent](https://hermes-agent.nousresearch.com), organised by domain. Each skill is self-contained in its own folder — pick and choose which to install.

> **Portability:** These skills are written for Hermes's tool architecture (`web_search`, `web_extract`, `terminal`, `delegate_task`, `cronjob`, etc.) and SKILL.md format. However, the workflows, prompts, and scripts are agent-agnostic — an AI agent on any platform (Claude Code, Codex, OpenCode, LangGraph, etc.) should be able to adapt them by mapping the tool names and adjusting the skill loader conventions to their own environment.

## Repository structure

```text
agent_skills/
├── README.md                         ← you are here (repo-level)
├── LICENSE
├── creative/                         ← image and video generation workflows
│   ├── image-studio/                 ← staged fal.ai image generation/editing/cleanup
│   ├── clips-studio/                 ← staged fal.ai short-video generation/animation/camera moves
│   └── pexels-stock-photos/          ← free real-world stock photo search + download (Pexels API)
├── research/                         ← source-grounded research, enrichment, and RAG skills
│   ├── deep-research/                ← iterative Think→Search→Extract→Synthesize→Stop research engine
│   ├── entity-research/              ← cited entity/person background dossiers + sanctions signals
│   ├── news-monitoring/              ← recurring news digests with cron delivery + multi-language
│   ├── notebooklm-mode/              ← NotebookLM-style source vault + grounded answers
│   ├── people-enrichment/            ← PDL person/company enrichment/search to styled .xlsx
│   ├── library-rag/                  ← bge-m3 + sqlite-vec semantic search engine
│   ├── source-tracker/               ← persistent citation database + URL health + bibliography export
│   ├── fact-checker/                 ← targeted claim verification + confidence rating + cited reports
│   ├── media-analyzer/               ← rhetorical technique detection (loaded language, framing, omission)
│   └── youtube-topic-research/       ← YouTube search + transcript summarization
├── mlops/                            ← model evaluation and ops skills
│   └── model-compare/                ← blind multi-model A/B comparison with tool calling + token efficiency
├── web-scraping/                     ← web data-extraction skills
│   └── website-scraping/             ← recon → lightest-tool extraction → JSONL output
├── productivity/                     ← personal / business-ops skills
│   ├── fill-template/                ← bulk-fill Word/Excel templates from a data table (mail-merge)
│   ├── travel-itinerary/             ← business-trip itineraries: parse → structure → export
│   ├── decision-log/                 ← ADR-style decision journal + superseding chains + cron reviews
│   ├── document-converter/           ← wide-range format converter (Markdown↔HTML, CSV↔JSON, YAML↔TOML, PDF)
│   ├── scheduled-summary/            ← cron-driven cross-session digest for messaging platforms
│   └── task-brief/                   ← goal/context/constraints brief compiled + confirmed before substantial tasks
└── agent-ops/                        ← agent infrastructure and maintenance skills
    ├── claude-plugin-converter/      ← convert Claude Code plugins → self-contained Hermes plugins
    ├── skill-maintainer/             ← end-to-end skill library maintenance + upstream sync
    └── log-analyzer/                 ← log pattern detection: error clusters, rate limits, timeouts
```

New skills are added as folders under the relevant domain directory.

## Skills

| Skill | Domain | What it does | Pairs with |
|-------|--------|-------------|------------|
| [image-studio](creative/image-studio/) | creative | Staged fal.ai image gen/edit/upscale/cleanup with cost logging + `--dry-run` | pexels-stock-photos |
| [clips-studio](creative/clips-studio/) | creative | Staged fal.ai short-video: text-to-video, animate still, camera moves | image-studio |
| [pexels-stock-photos](creative/pexels-stock-photos/) | creative | Free real-world stock photos (Pexels API, 20k/month) with attribution handling | image-studio |
| [deep-research](research/deep-research/) | research | Autonomous Think→Search→Extract→Synthesize→Stop loop → cited report | fact-checker, source-tracker |
| [entity-research](research/entity-research/) | research | Cited company/person dossiers: ownership, adverse media, sanctions, litigation | deep-research |
| [people-enrichment](research/people-enrichment/) | research | PDL person/company lookup → styled `.xlsx` | entity-research |
| [library-rag](research/library-rag/) | research | Semantic search over personal library (bge-m3 + sqlite-vec) | notebooklm-mode |
| [notebooklm-mode](research/notebooklm-mode/) | research | Source-grounded Q&A from a source vault, strict or augmented grounding | library-rag, deep-research |
| [news-monitoring](research/news-monitoring/) | research | Recurring news digests with cron delivery + multi-language + dedup | source-tracker |
| [youtube-topic-research](research/youtube-topic-research/) | research | YouTube search → transcript → summary pipeline | notebooklm-mode |
| [source-tracker](research/source-tracker/) | research | Persistent citation DB: URL dedup, topic tags, link health, bibliography export | deep-research, fact-checker |
| [fact-checker](research/fact-checker/) | research | Claim verification → confidence rating (verified→outdated) + cited report | deep-research, source-tracker |
| [media-analyzer](research/media-analyzer/) | research | Rhetorical technique detection (loaded language, framing, omission) — not political labels | fact-checker, deep-research |
| [model-compare](mlops/model-compare/) | mlops | Blind multi-model A/B comparison: simple, tools, coding, review modes | — |
| [website-scraping](web-scraping/website-scraping/) | web-scraping | Recon → lightest extraction tool → JSONL + run manifest | source-tracker |
| [fill-template](productivity/fill-template/) | productivity | Bulk-fill Word/Excel templates from a data table (mail-merge) | — |
| [travel-itinerary](productivity/travel-itinerary/) | productivity | Business-trip itineraries from emails/PDFs → Markdown + `.ics` + chat variants | — |
| [decision-log](productivity/decision-log/) | productivity | ADR-style decision journal with superseding chains + cron review reminders | — |
| [document-converter](productivity/document-converter/) | productivity | Wide-range format converter: Markdown↔HTML, CSV↔JSON, YAML↔TOML, PDF, Excel | fill-template |
| [scheduled-summary](productivity/scheduled-summary/) | productivity | Cron-driven cross-session digest — surfaces activity invisible on chat platforms | decision-log, news-monitoring |
| [task-brief](productivity/task-brief/) | productivity | Goal/context/constraints/tooling brief compiled and confirmed before substantial work starts | — |
| [claude-plugin-converter](agent-ops/claude-plugin-converter/) | agent-ops | Two-phase converter: analyze Claude Code plugins → generate installable Hermes plugins | skill-maintainer |
| [skill-maintainer](agent-ops/skill-maintainer/) | agent-ops | Skill library maintenance: author, curate, upstream drift tracking, publish | — |
| [log-analyzer](agent-ops/log-analyzer/) | agent-ops | Log pattern detection: error clusters, rate limits, timeout clusters, tool failures | scheduled-summary |

> **Related work:** [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) (PewDiePie's self-hosted AI workspace) ships similar features as a standalone web app — "Deep Research" and "Compare" — while `deep-research` and `model-compare` cover the same ground as pure-prompt workflows + stdlib scripts inside any agent's tool loop.

## Skill maturity

| Skill | Status | Tests | Dependencies |
|-------|--------|-------|-------------|
| image-studio | Stable | ✓ | fal.ai key |
| clips-studio | Stable | ✓ | fal.ai key |
| pexels-stock-photos | Stable | ✓ | Pexels API key (free) |
| deep-research | Stable | evals | None (prompt-only) |
| entity-research | Stable | ✓ | None (stdlib) |
| people-enrichment | Stable | ✓ | openpyxl; PDL API key |
| library-rag | Stable | ✓ | sqlite-vec, requests, pyyaml; optional PDF/EPUB/MCP deps |
| notebooklm-mode | Stable | ✓ | library-rag |
| news-monitoring | Stable | evals | None (prompt-only) |
| youtube-topic-research | Stable | ✓ | ddgs, youtube-transcript-api, jinja2, pyyaml |
| source-tracker | Stable | ✓ | None (stdlib) |
| fact-checker | Stable | ✓ | None (stdlib) |
| media-analyzer | Stable | ✓ | None (stdlib) |
| model-compare | Stable | ✓ | None (stdlib); tool mode needs SEARXNG_URL or ddgs CLI |
| website-scraping | Stable | evals | None (prompt-only) |
| fill-template | Stable | ✓ | python-docx, openpyxl |
| travel-itinerary | Stable | ✓ | None (stdlib) |
| decision-log | Stable | ✓ | None (stdlib) |
| document-converter | Stable | ✓ | pandoc (PDF), openpyxl (Excel), PyYAML (optional) |
| scheduled-summary | Stable | ✓ | None (stdlib) |
| task-brief | Beta | — | None (prompt-only) |
| claude-plugin-converter | Beta | ✓ | None (stdlib) |
| skill-maintainer | Beta | ✓ | None (stdlib; curl for GitHub API). Unix-first — cron, curl, `which`, shell loops. Windows via WSL/MSYS2 untested. |
| log-analyzer | Stable | ✓ | None (stdlib) |

> *Stable* = production-tested with real workflows. *Tests* column: ✓ = has a pytest suite; *evals* = ships routing/output-contract fixtures under `evals/` (sample request → expected routing, required output fields, forbidden patterns), validated by `tests/test_routing_fixtures.py` — no live-model execution in CI. *Dependencies* lists pip/runtime requirements beyond Python stdlib.

## Quick start

1. **Clone:**
   ```bash
   git clone https://github.com/moonlight-lupin/agent_skills.git
   cd agent_skills
   ```
2. **Open the skill you want** — each skill folder has a `SKILL.md` with setup and usage instructions.

> **Never commit credentials.** API keys, config files with secrets, and generated artifacts are all gitignored.

## License

[MIT](LICENSE) — all skills in this repository are original works by moonlight-lupin and are covered by the MIT License.
