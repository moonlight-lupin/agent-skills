# website-scraping

A generic playbook for turning websites into structured data — recon, picking the lightest
extraction tool that works, surviving anti-bot defences, and writing clean JSONL output.

## License

This skill is licensed under the repository's [MIT License](../../LICENSE).

## Layout

```
SKILL.md                     # the 7-step workflow
references/                  # deeper material, loaded on demand
  recon.md  extraction.md  anti-bot.md  playwright.md  agentic-browsing.md
scripts/recon.py             # python recon.py <url>  — probe a site's extraction strategy
examples/                    # runnable worked examples
evals/                       # skill eval set
```
