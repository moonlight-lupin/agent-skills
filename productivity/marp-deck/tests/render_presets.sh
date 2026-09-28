#!/usr/bin/env bash
# Render the sample deck under every theme in references/themes.md to
# tests/renders/<theme>.00N.png, then look at the PNGs.
# Usage: bash tests/render_presets.sh   (set CHROME_PATH if marp-cli can't find a browser)
set -u; cd "$(dirname "$0")/.."
rm -rf tests/renders; mkdir -p tests/renders
python3 tests/extract_css.py . tests/renders || exit 1
fail=0
for md in tests/renders/*.md; do
  if npx --yes @marp-team/marp-cli "$md" --html --allow-local-files --images png </dev/null >/dev/null 2>&1 \
     && ls "${md%.md}".0*.png >/dev/null 2>&1; then echo "PASS  render $(basename "$md")"; else echo "FAIL  render $(basename "$md")"; fail=1; fi
done
exit $fail
