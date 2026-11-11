# Agent Skills

[![Tests](https://github.com/moonlight-lupin/agent-skills/actions/workflows/test.yml/badge.svg)](https://github.com/moonlight-lupin/agent-skills/actions/workflows/test.yml)
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
│   ├── deep-research/                ← iterative research engine with structured evidence, source quality ranking, refute polarity, four-label evidence-basis discipline, deterministic validation gates, verbatim quote anchoring, per-round search budgets
│   ├── entity-research/              ← cited entity/person background dossiers + sanctions signals
│   ├── news-monitoring/              ← recurring news digests with cron delivery + multi-language
│   ├── notebooklm-mode/              ← NotebookLM-style source vault + grounded answers
│   ├── people-enrichment/            ← PDL person/company enrichment/search to styled .xlsx
│   ├── library-rag/                  ← Nemotron-3-Embed-1B + sqlite-vec semantic search engine
│   └── endpoint-probe/               ← API/MCP surface discovery (REST, GraphQL, SOAP, JSON-RPC)
├── mlops/                            ← model evaluation and ops skills
│   ├── model-compare/                ← blind multi-model A/B comparison + embedding benchmark
│   └── paired-agent-eval/            ← paired A/B pilot harness: matched task pairs, blinded defect scoring, behavioral text-variant batteries
├── web-scraping/                     ← web data-extraction skills
│   └── website-scraping/             ← recon → lightest-tool extraction → JSONL output
├── productivity/                     ← personal / business-ops skills
│   ├── fill-template/                ← bulk-fill Word/Excel templates from a data table (mail-merge)
│   ├── travel-itinerary/             ← business-trip itineraries: parse → structure → export
│   ├── decision-log/                 ← ADR-style decision journal + superseding chains + cron reviews
│   ├── scheduled-summary/            ← cron-driven cross-session digest for messaging platforms
│   ├── file-organizer/               ← LLM-powered directory organizer: scan → propose → confirm → move
│   ├── receipt-compiler/             ← phone-camera receipt photos → straightened B&W A4 expense-claim PDF
│   ├── task-brief/                   ← goal/context/constraints brief compiled + confirmed before substantial tasks
│   ├── marp-deck/                    ← Marp Markdown decks → PPTX/PDF/HTML render
│   └── pdf2epub/                     ← text-layer PDF book → structured EPUB (cover, TOC nav, illustrations, endnotes; classifier calibration rules absorbed)
├── agent-ops/                        ← agent infrastructure and maintenance skills
│   ├── claude-plugin-converter/      ← convert Claude Code plugins → self-contained Hermes plugins
│   ├── log-analyzer/                 ← log pattern detection: error clusters, rate limits, timeouts
│   ├── input-token-overheads/        ← audit input token cost, two scopes: per-turn prompt overhead + aggregate spend (cost accounting)
│   ├── operator-brain/               ← 10-module behavioral stack (Fable 5 + 5.1): act, lead with outcome, ground claims, narrate long work
│   └── hermes-onboarding/            ← 21-step customer onboarding: gateway, dashboard, memory, crons
├── software-development/              ← skill development, review, and methodology skills
│   └── skill-quality-review/          ← batch skill audit: 9 checks, writing-for-agents levers, efficacy testing
├── devops/                           ← infrastructure and system maintenance skills
│   └── disk-triage/                  ← triage survey → safe/ask buckets → execute → verify delta (renamed from disk-cleanup — bundled Hermes plugin now owns that name)
└── plugins/                          ← installable Hermes Agent plugins
    ├── skill-retrieval/              ← BM25 retrieval that injects the top-K relevant skills per turn
    ├── dev-pipeline/              ← five-stage development pipeline (grill/spec/test-evals/build/review-commit) with a pre_tool_call create-gate hook
    ├── skill-governance/          ← skill provenance + drift acks + advisory contrastive probes behind one composed hook surface (successor to the retired skill-manifest + contrastive-advisor plugins)
    └── lumen/                     ← LLM wiki plugin: methodology + memory-fed curator
```

New skills are added as folders under the relevant domain directory.

## Skills

| Skill | Domain | What it does | Dependencies |
|-------|--------|-------------|-------------|
| [image-studio](creative/image-studio/) | creative | Staged fal.ai image gen/edit/upscale/cleanup with cost logging + `--dry-run` | pexels-stock-photos |
| [clips-studio](creative/clips-studio/) | creative | Staged fal.ai short-video: text-to-video, animate still, camera moves | image-studio |
| [pexels-stock-photos](creative/pexels-stock-photos/) | creative | Free real-world stock photos (Pexels API, 20k/month) with attribution handling | image-studio |
| [deep-research](research/deep-research/) | research | Iterative research engine: structured evidence, source quality ranking (primary/secondary/tertiary), refute polarity, overview-first reports, four-label evidence-basis discipline ([VERIFIED]/[SOURCED]/[REASONED]/[ESTIMATED]), deterministic validation gates (claim-support, citations, structure), verbatim quote anchoring, per-round search budgets, provider-neutral search and page-reader fallbacks, referent disambiguation probe, firmware support-status triangulation recipe, provider head-to-head benchmarking, follow-up report revision, persistent citation DB scripts (absorbed source-tracker) | — |
| [entity-research](research/entity-research/) | research | Cited company/person dossiers: ownership, adverse media, sanctions, litigation; optional cited organisation-evidence run (Exa Agent API) | deep-research |
| [people-enrichment](research/people-enrichment/) | research | PDL person/company lookup → styled `.xlsx`; email-list enrichment (free triage, one lookup per domain); shared mailboxes never kept as a person's email | entity-research |
| [library-rag](research/library-rag/) | research | Semantic search over personal library (Nemotron-3-Embed-1B + sqlite-vec), incremental + prune-missing | notebooklm-mode |
| [notebooklm-mode](research/notebooklm-mode/) | research | Source-grounded Q&A from a source vault, strict or augmented grounding | library-rag, deep-research |
| [news-monitoring](research/news-monitoring/) | research | Recurring news digests with cron delivery + multi-language + dedup | — |
| [endpoint-probe](research/endpoint-probe/) | research | Discover API/MCP surfaces (REST, GraphQL, SOAP, JSON-RPC) — probe script + interpretation guide | website-scraping |
| [model-compare](mlops/model-compare/) | mlops | Blind multi-model A/B comparison: simple, tools, coding, review modes + embedding benchmark; dated battery findings library | paired-agent-eval |
| [paired-agent-eval](mlops/paired-agent-eval/) | mlops | Does tiered pipeline processing justify its cost: matched single-agent vs pipeline pairs, acceptance suites, blinded severity-weighted defect scoring; behavioral skill-text variant A/B batteries (operating methodology for the operator-brain text-variant evals) | model-compare |
| [website-scraping](web-scraping/website-scraping/) | web-scraping | Recon → lightest extraction tool → JSONL + run manifest | — |
| [fill-template](productivity/fill-template/) | productivity | Bulk-fill Word/Excel templates from a data table (mail-merge) | — |
| [travel-itinerary](productivity/travel-itinerary/) | productivity | Business-trip itineraries from emails/PDFs → Markdown + `.ics` + chat variants | — |
| [decision-log](productivity/decision-log/) | productivity | ADR-style decision journal with superseding chains + cron review reminders | — |
| [scheduled-summary](productivity/scheduled-summary/) | productivity | Cron-driven cross-session digest — surfaces activity invisible on chat platforms | decision-log, news-monitoring |
| [file-organizer](productivity/file-organizer/) | productivity | LLM-powered directory organizer: scan → propose structure → confirm → chunked moves | — |
| [receipt-compiler](productivity/receipt-compiler/) | productivity | Phone-camera receipt photos → straightened B&W scans → A4 expense-claim PDF with confirmation gate | pdf |
| [task-brief](productivity/task-brief/) | productivity | Goal/context/constraints/tooling brief compiled and confirmed before substantial work starts | — |
| [pdf2epub](productivity/pdf2epub/) | productivity | Text-layer PDF book → structured EPUB: cover, printed-TOC nav, inline illustrations, linked endnotes; classifier calibration rules absorbed into `references/calibration.md` | document-toolkit, opendataloader-pdf |
| [marp-deck](productivity/marp-deck/) | productivity | Marp presentations: Markdown source of truth → PDF/PPTX/HTML, with themes, SVG components, PPTX import, and render tests | — |
| [claude-plugin-converter](agent-ops/claude-plugin-converter/) | agent-ops | Two-phase converter: analyze Claude Code plugins → generate installable Hermes plugins | — |
| [skill-quality-review](software-development/skill-quality-review/) | software-development | Batch skill audit: 9 automated checks, writing-for-agents levers, per-skill grep methodology, efficacy A/B testing, frontmatter/description fixes | — |
| [log-analyzer](agent-ops/log-analyzer/) | agent-ops | Log pattern detection: error clusters, rate limits, timeout clusters, tool failures | scheduled-summary |
| [input-token-overheads](agent-ops/input-token-overheads/) | agent-ops | Audit input token cost at two scopes: per-turn prompt overhead (tool schemas, skills index, system text, profile, memory — measured live, ranked, reduced) and aggregate spend/cost accounting across sessions, cron fires, and tool traffic (cache-aware interpretation, pre-checked config levers, scheduled delta checks) | — |
| [operator-brain](agent-ops/operator-brain/) | agent-ops | 10-module behavioral stack from Anthropic's Fable 5 and Fable 5.1 guides: act, lead with outcome, ground every claim, narrate long work, stay surgical | — |
| [hermes-onboarding](agent-ops/hermes-onboarding/) | agent-ops | 21-step customer onboarding: gateway, dashboard, memory, search, guardrails, maintenance crons | disk-triage, log-analyzer |
| [disk-triage](devops/disk-triage/) | devops | Triage disk space: survey all mounts → safe/ask buckets → execute approved set → verify delta (renamed from disk-cleanup; the bundled Hermes `disk-cleanup` plugin owns that name) | — |
| [dev-pipeline](plugins/dev-pipeline/) | plugins | Five-stage development pipeline: grill → spec → test-evals → build → review-commit, planned by S0-S3 complexity and reviewed by R0-R3 risk (T0-T3 review-tier aliases), with a review-lessons library and a pre_tool_call create-gate that blocks new software-development skills unless a single-use allow flag is consumed | skill-quality-review |
| [skill-governance](plugins/skill-governance/) | plugins | Consolidated skill provenance and governance: manifest fingerprints + drift acks and advisory-only contrastive probes behind one composed hook surface, conservative `governance.records` join, non-destructive legacy state import, and one clearance Automation Blueprint (`/blueprint`-adopted, no self-installed cron; sole successor to the retired skill-manifest + contrastive-advisor plugins) | — |

> **Related work:** [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) (PewDiePie's self-hosted AI workspace) ships similar features as a standalone web app — "Deep Research" and "Compare" — while `deep-research` and `model-compare` cover the same ground as pure-prompt workflows + stdlib scripts inside any agent's tool loop.

## Plugins

Beyond skills, the repo ships installable [Hermes Agent](https://hermes-agent.nousresearch.com) plugins under `plugins/`.

### skill-retrieval

A Hermes plugin that scales skill usage to large libraries. As a skill catalog grows past a few dozen entries, the per-turn `<available_skills>` block costs input tokens and buries the right skill in noise. This plugin replaces the full block with BM25 retrieval: each user turn is scored against a stdlib inverted index built from skill names and descriptions, and only the top-K most relevant skills are injected into the prompt (default K=6, configurable via `plugin.yaml`).

- **Stdlib only** — no numpy/scipy; the index builds in milliseconds and retrieval is sub-millisecond for 128+ skills.
- **Profile-aware discovery** — paths resolve through Hermes' own helpers (`get_hermes_home`, `get_skills_dir`), so named profiles, `skills.external_dirs`, trusted project-local skills, disabled lists, and platform/condition gates all match what the agent itself sees. The index cache is keyed per Hermes home, so multiplexed profiles never share an index.
- **Windows-safe** — skill ids normalize to forward slashes; `$HERMES_HOME`-aware path resolution.
- **Optional Jev rerank** — reranks the BM25 top-K with the Jev system-one judgment model (`api.typesafe.ai`) when `SKILL_RETRIEVAL_RERANK` is enabled and `TYPESAFE_API_KEY` is present (the legacy `TYPESAFE_KEY` name is accepted, from `os.environ`). Fail-soft: on timeout or error it logs and falls back to pure BM25. An A/B log (`rerank_ab_report.py`) records per-query decisions for trial review; it rotates past 5 MB; runs on a cron, no runtime dependency.
- **Graceful degradation** — if Hermes core modules are unavailable, it falls back to a standalone loader; malformed configs never abort the index build. A/B logging and rerank never abort retrieval.

Or install from the Hermes plugin catalog (pinned, version-tracked):

```bash
hermes plugins install skill-retrieval
```

Install by copying or symlinking `plugins/skill-retrieval/` into `~/.hermes/plugins/` (or your profile's `plugins/`), then restart the gateway. Tests: `python3 -m pytest plugins/skill-retrieval/tests/`.

### lumen

A Hermes plugin that turns an agent's conversation history and memory into a maintained markdown wiki (Karpathy-style LLM wiki). Two skills: `lumen:wiki` (the methodology: OKF frontmatter, three-layer page layout, ingest/query/lint workflows) and `lumen:curator` (the `wiki_curator.py` script plus a read-only memory-source adapter layer — the Hermes conversation history via read-only SQLite, Mnemosyne via the `hermes` CLI export, plain JSON files, or none).

- **Sessions-first by default** — the default memory source is the agent's own conversation history (read-only SQLite over `state.db`); `auto` prefers sessions, then Mnemosyne, then JSON files. The conversation record is treated as ground truth; memory stores hold derived notes.
- **Cap-bounded curation** — batch ingest, update, and validate runs are capped per run, with per-page backups and atomic replace.
- **Source attribution contract** — every generated line is `[source: id]` attributed; operator-authored text outside generated sections is preserved on update (verified through 7 review rounds with independent confirm reviewers).
- **Stdlib + PyYAML only** — no network calls except the `hermes` CLI for memory export; adapters read exports, never provider internals.

Install by copying or symlinking `plugins/lumen/` into `~/.hermes/plugins/` (or your profile's `plugins/`), enable it with `hermes plugins enable lumen` (user plugins are opt-in), then restart the gateway. Tests: `python3 -m pytest plugins/lumen/tests/`.

### dev-pipeline

A Hermes plugin that guards skill creation and carries the development pipeline as five bundled stage skills (`dev-pipeline:orchestrator` → `dev-pipeline:grill` → `dev-pipeline:spec` → `dev-pipeline:test-evals` → `dev-pipeline:build` → `dev-pipeline:review-commit`), plus a `review-lessons` library split out of the review stage. A `pre_tool_call` gate blocks bare-name creation of new software-development skills unless a single-use `.allow-create` flag is consumed — the loop concepts that used to live in a standalone build-review-loop skill now ship as these bundled skills.

Install by copying or symlinking `plugins/dev-pipeline/` into `~/.hermes/plugins/` (or your profile's `plugins/`), then restart the gateway. Tests: `python3 -m pytest plugins/dev-pipeline/tests/`.

### skill-governance

A Hermes plugin that consolidates the provenance engine and the advisory edit-observation engine behind one composed hook surface (`on_skill_lifecycle`, `on_session_start`, `pre_tool_call`, `pre_llm_call`). It bundles the `contrastive-refinement` skill (`plugins/skill-governance/skills/contrastive-refinement/`, registered as `skill-governance:contrastive-refinement`): behavioral skill edits get one advisory reminder to run the probe cycle (fire ledger at `~/.hermes/skill-probes/fire-ledger.jsonl`). The manifest engine enforces `UPSTREAM_MANIFEST.md`: arrivals must have a manifest row, content changes in manifested skills must be re-acknowledged against a content fingerprint (`/skill-manifest-ack <name> <sha>`). `manifest.v1`/`advisor.v1` import legacy state by copy (destination-wins, sources never modified). v0.3.0 ships the clearance procedure as an adopted Automation Blueprint (`skill-governance:clearance`, daily `0 9 * * *`, delivery `origin`) registered through the public host surface — the plugin imports no private cron modules and writes no cron state; it replaces both legacy schedulers and preserves both clearance procedures verbatim. `governance.records` joins the two views conservatively — an acknowledged fingerprint never implies validated evidence.

Install from the Hermes plugin catalog:

```bash
hermes plugins install skill-governance
```

Or copy/symlink `plugins/skill-governance/` into `~/.hermes/plugins/` (or your profile's `plugins/`), then restart the gateway. Migrate from the retired `skill-manifest`/`contrastive-advisor` plugins per the checklist in `plugins/skill-governance/README.md`. Tests: `python3 -m pytest plugins/skill-governance/tests/`.

## Conventions

> Conventions: the *Dependencies* column on the Skills table lists pip/runtime requirements beyond Python stdlib; skills marked *evals* ship routing/output-contract fixtures under `evals/` (sample request → expected routing, required output fields, forbidden patterns), validated by `tests/test_routing_fixtures.py` — no live-model execution in CI. Plugins are tested separately (`plugins/<name>/tests/`) and tracked under Plugins above.

## Install

### One-command: install the whole catalog (`npx`)

```bash
npx skills add moonlight-lupin/agent-skills
```

Installs every skill into `.agents/skills/` (works for Cursor, Codex, Gemini CLI, Copilot, OpenCode, and more; Claude Code gets a symlinked copy) plus `.claude/skills/`, with a hash-pinned `skills-lock.json` so `npx skills update` can refresh later. Install one skill with `--skill <name>` — or omit it for an interactive pick-list.

### Pick a skill from GitHub (`gh`)

```bash
# Install one skill by exact path (fastest, no tree scan)
gh skill install moonlight-lupin/agent-skills creative/image-studio/SKILL.md

# ...or by name into a specific agent's directory
gh skill install moonlight-lupin/agent-skills creative/image-studio/SKILL.md --agent claude-code --scope user
```

### Manual

```bash
git clone https://github.com/moonlight-lupin/agent-skills.git
cd agent-skills
```

Each skill folder has a `SKILL.md` with setup and usage instructions — copy the ones you want into your agent's skills directory (e.g. `~/.claude/skills/`, `~/.cursor/skills/`, `~/.agents/skills/`).

> **Never commit credentials.** API keys, config files with secrets, and generated artifacts are all gitignored.

> **Spec compliance:** all skills validate against the [Agent Skills spec](https://agentskills.io/specification) (`npx skills-ref validate`). Author, version, and platform metadata live under `metadata:`.

## License

[MIT](LICENSE) — all skills in this repository are original works by moonlight-lupin and are covered by the MIT License.
