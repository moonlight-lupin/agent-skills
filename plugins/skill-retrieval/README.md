# skill-retrieval

BM25-based skill retrieval plugin for [Hermes Agent](https://hermes-agent.nousresearch.com). Replaces the full skill list in the system prompt with a names-only compact view (~2K tokens) and injects top-K relevant skill descriptions per turn (~300 tokens), saving ~9K tokens/turn while keeping skills discoverable by name. Those figures were measured on a Hermes install with ~300 skills; the saving scales with your own skill count.

This is a **Hermes Agent** plugin. It is not a Claude Code plugin and will not load in Claude Code — that runtime has no `pre_llm_call` event, no Python `register()` entry point, and reads `.claude-plugin/plugin.json` rather than `plugin.yaml`. Developed against Hermes Agent >=0.20.0.

See [SKILL.md](SKILL.md) for full architecture, token measurements, how it works, performance, limitations, and how to verify a healthy install.

## Installation

```bash
# From the agent_skills repo root
ln -s "$(pwd)/plugins/skill-retrieval" ~/.hermes/plugins/skill-retrieval

# Dependencies (Hermes Python env)
# pyyaml is the only dependency — usually already present in a Hermes env
pip install pyyaml
```

Restart the Hermes session so the plugin's `register()` runs.

## Configuration

| Setting | Default | Override |
|---------|---------|----------|
| Top-K results | `6` | `SKILL_RETRIEVAL_TOP_K` env var |
| BM25 k1 | `1.5` | edit `scripts/bm25_retriever.py` |
| BM25 b | `0.75` | edit `scripts/bm25_retriever.py` |

```bash
export SKILL_RETRIEVAL_TOP_K=8
```

## Uninstall

1. Remove the plugin from the Hermes plugins folder:
   ```bash
   # If symlinked:
   rm ~/.hermes/plugins/skill-retrieval
   # If copied:
   rm -rf ~/.hermes/plugins/skill-retrieval
   ```
2. Restart the Hermes session
3. The system prompt reverts on restart (the patch is in-process only, not persistent)

## License

MIT. See [LICENSE](LICENSE) for the upstream SR-Agents notice and this project's notice.
