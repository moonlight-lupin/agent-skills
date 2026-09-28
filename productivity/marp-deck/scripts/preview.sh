#!/usr/bin/env bash
# Render style-preview slides to PNG so the user can SEE candidate themes
# before committing (the "show, don't tell" step, Marp edition).
#
# Usage:
#   bash preview.sh <previews_dir>
#
# Expects <previews_dir> to contain one or more single-slide Marp files
# (e.g. style-a.md, style-b.md, style-c.md). Each is rendered to a PNG of
# the same basename. The PNGs are what you show/open for the user to pick.
#
# --html is passed so inline <svg>/HTML render in the preview.
# Requires Node.js (npx). marp-cli is fetched on first run.
set -euo pipefail

DIR="${1:-}"
if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "Usage: bash preview.sh <previews_dir>" >&2
  exit 1
fi

shopt -s nullglob
mds=("$DIR"/*.md)
if [[ ${#mds[@]} -eq 0 ]]; then
  echo "No .md preview files found in $DIR" >&2
  exit 1
fi

for md in "${mds[@]}"; do
  echo "→ rendering $(basename "$md") → PNG"
  # --images png writes <name>.001.png; single-slide files yield one image.
  npx --yes @marp-team/marp-cli "$md" --html --allow-local-files --images png
done

echo "Done. PNG previews written into $DIR — open them for the user to choose."
