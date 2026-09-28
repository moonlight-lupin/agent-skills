#!/usr/bin/env bash
# The bundled scripts must render inline <svg>/HTML (i.e. pass --html).
# Usage: bash tests/test_scripts.sh   (needs Node, pdftotext; set CHROME_PATH if needed)
set -u; cd "$(dirname "$0")/.."
T=$(mktemp -d); cp tests/fixtures/component-deck.md "$T/deck.md"; mkdir "$T/prev"; cp "$T/deck.md" "$T/prev/p.md"
pass=0; fail=0; ok(){ echo "PASS  $1"; pass=$((pass+1)); }; ko(){ echo "FAIL  $1"; fail=$((fail+1)); }
bash scripts/export.sh "$T/deck.md" pdf </dev/null >/dev/null 2>&1
txt=$(pdftotext "$T/deck.pdf" - 2>/dev/null)
[[ $txt == *SVG-SENTINEL* && $txt != *"<svg"* ]] && ok "export.sh pdf renders inline SVG" || ko "export.sh pdf renders inline SVG"
bash scripts/export.sh "$T/deck.md" html </dev/null >/dev/null 2>&1
grep -q '&lt;svg' "$T/deck.html" && ko "export.sh html renders inline SVG" || ok "export.sh html renders inline SVG"
grep -q -- '--html' scripts/preview.sh && ok "preview.sh passes --html" || ko "preview.sh passes --html"
bash scripts/preview.sh "$T/prev" </dev/null >/dev/null 2>&1
ls "$T"/prev/p*.png >/dev/null 2>&1 && ok "preview.sh writes PNGs" || ko "preview.sh writes PNGs"
rm -rf "$T"; echo "---- $pass passed, $fail failed"; [[ $fail -eq 0 ]]
