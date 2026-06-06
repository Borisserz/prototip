#!/usr/bin/env bash
set -euo pipefail

# Copies the project source files into the macOS clipboard in an LLM-friendly format.
# Run from anywhere. By default it uses the directory where this script is located.
# Usage:
#   ./copy_project_to_clipboard.sh
#   ./copy_project_to_clipboard.sh /path/to/prototip

PROJECT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
OUTPUT_FILE="${TMPDIR:-/tmp}/prototip_llm_context.txt"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project directory not found: $PROJECT_DIR" >&2
  exit 1
fi

if ! command -v pbcopy >/dev/null 2>&1; then
  echo "pbcopy not found. This script is intended for macOS." >&2
  exit 1
fi

cd "$PROJECT_DIR"

# Files and folders that should not be pasted to an LLM.
# Add/remove patterns here if needed.
EXCLUDES=(
  "./.git/*"
  "./.venv/*"
  "./venv/*"
  "./__pycache__/*"
  "*/__pycache__/*"
  "./.pytest_cache/*"
  "./.ruff_cache/*"
  "./.mypy_cache/*"
  "./.DS_Store"
  "*/.DS_Store"
  "./out/*"
  "./*.png"
  "./*.jpg"
  "./*.jpeg"
  "./*.gif"
  "./*.webp"
  "./*.pdf"
  "./*.pptx"
  "./*.xlsx"
  "./*.parquet"
  "./*.sqlite"
  "./*.db"
  "./*.pyc"
  "./*.log"
)

find_args=(.)
for pattern in "${EXCLUDES[@]}"; do
  find_args+=( -not -path "$pattern" )
done

{
  echo "# Project context: prototip"
  echo
  echo "Generated at: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "Project directory: $PROJECT_DIR"
  echo
  echo "## Git status"
  echo '```text'
  git status --short --branch 2>/dev/null || true
  echo '```'
  echo
  echo "## File tree"
  echo '```text'
  find "${find_args[@]}" -type f | sort | sed 's#^./##'
  echo '```'
  echo
  echo "## Files"

  while IFS= read -r file; do
    rel="${file#./}"
    echo
    echo "===== FILE: $rel ====="

    ext="${rel##*.}"
    case "$ext" in
      py) lang="python" ;;
      md) lang="markdown" ;;
      toml) lang="toml" ;;
      txt) lang="text" ;;
      csv) lang="csv" ;;
      json) lang="json" ;;
      yaml|yml) lang="yaml" ;;
      sh) lang="bash" ;;
      *) lang="text" ;;
    esac

    echo '```'"$lang"
    cat "$file"
    echo
    echo '```'
  done < <(find "${find_args[@]}" -type f | sort)
} > "$OUTPUT_FILE"

pbcopy < "$OUTPUT_FILE"

bytes=$(wc -c < "$OUTPUT_FILE" | tr -d ' ')
files=$(grep -c '^===== FILE:' "$OUTPUT_FILE" || true)

echo "Copied project context to clipboard."
echo "Files included: $files"
echo "Size: $bytes bytes"
echo "Temp file: $OUTPUT_FILE"
echo
echo "Now paste it into the AI chat."
