#!/usr/bin/env bash
# Batch generate missing thumbnails for all PDFs in references/
# Usage: bash scripts/gen_thumb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REFS_DIR="$SCRIPT_DIR/../references"
THUMBS_DIR="$REFS_DIR/thumbs"

# Detect pdftoppm
if command -v /opt/homebrew/bin/pdftoppm &>/dev/null; then
  PDFTOPPM=/opt/homebrew/bin/pdftoppm
elif command -v pdftoppm &>/dev/null; then
  PDFTOPPM=pdftoppm
else
  echo "Error: pdftoppm not found."
  echo "  macOS: brew install poppler"
  echo "  Linux: sudo apt-get install poppler-utils"
  exit 1
fi

mkdir -p "$THUMBS_DIR"

generated=0
skipped=0

for pdf in "$REFS_DIR"/*.pdf; do
  [ -f "$pdf" ] || continue
  base="$(basename "$pdf" .pdf)"
  thumb="$THUMBS_DIR/${base}-01.png"

  if [ -f "$thumb" ]; then
    skipped=$((skipped + 1))
    continue
  fi

  echo "Generating thumbnail: $base"
  prefix="$THUMBS_DIR/$base"
  "$PDFTOPPM" -f 1 -l 1 -r 150 -png "$pdf" "$prefix" 2>/dev/null || {
    echo "  Warning: failed to process $pdf"
    continue
  }

  # Normalize filename: prefix-1.png or prefix-01.png → prefix-01.png
  created="$(ls "${prefix}-"*.png 2>/dev/null | head -1 || true)"
  if [ -n "$created" ] && [ "$created" != "$thumb" ]; then
    mv "$created" "$thumb"
  fi

  generated=$((generated + 1))
done

echo "Done: $generated generated, $skipped already existed."
