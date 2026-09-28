#!/usr/bin/env bash
# Export a Marp Markdown deck to PDF, PPTX, or HTML via marp-cli.
#
# Usage:
#   bash export.sh <deck.md> [pdf|pptx|html|all] [--editable]
#
# Notes:
#   - Requires Node.js (npx). marp-cli is fetched on first run.
#   - --html is always passed so inline <svg> charts and HTML components render
#     (without it marp-cli prints <svg> as literal text).
#   - --allow-local-files is always passed so relative ./assets/ images resolve.
#   - PPTX is image-per-slide by default. Add --editable for editable shapes
#     (requires LibreOffice installed and on PATH; uses --pptx-editable).
#   - If --pptx-editable fails (LibreOffice 24.2+ removed the Impress HTML
#     import filter), the script falls back to md2pptx-officecli.py, which
#     builds an editable PPTX via the officecli CLI (no LibreOffice needed).
#     The fallback drops CSS fidelity: theme colours are carried over from the
#     deck's :root variables, HTML components and SVG charts become plain text.
#   - Animations and <details> interactivity survive ONLY in HTML export.
set -euo pipefail

DECK="${1:-}"
FORMAT="${2:-pdf}"
EDITABLE="${3:-}"

if [[ -z "$DECK" || ! -f "$DECK" ]]; then
  echo "Usage: bash export.sh <deck.md> [pdf|pptx|html|all] [--editable]" >&2
  exit 1
fi

run() {
  echo "→ marp $*"
  npx --yes @marp-team/marp-cli "$DECK" --html --allow-local-files "$@"
}

case "$FORMAT" in
  pdf)  run --pdf ;;
  html) run -o "${DECK%.md}.html" ;;
  pptx)
    if [[ "$EDITABLE" == "--editable" ]]; then
      if ! run --pptx --pptx-editable; then
        echo "→ marp --pptx-editable failed (this machine's LibreOffice cannot" >&2
        echo "  import HTML into Impress — true for LibreOffice 24.2+)." >&2
        echo "→ Falling back to officecli editable build." >&2
        python3 "$(dirname "$0")/md2pptx-officecli.py" "$DECK" "${DECK%.md}-editable.pptx"
      fi
    else
      run --pptx
    fi
    ;;
  all)
    run --pdf
    run -o "${DECK%.md}.html"
    if [[ "$EDITABLE" == "--editable" ]]; then
      if ! run --pptx --pptx-editable; then
        echo "→ marp --pptx-editable failed; falling back to officecli." >&2
        python3 "$(dirname "$0")/md2pptx-officecli.py" "$DECK" "${DECK%.md}-editable.pptx"
      fi
    else
      run --pptx
    fi
    ;;
  *)
    echo "Unknown format: $FORMAT (use pdf|pptx|html|all)" >&2
    exit 1 ;;
esac

echo "Done. Output written next to $DECK"
