#!/usr/bin/env bash
# AURA Knowledge Export — Export rules as JSON/CSV
# Usage: ./scripts/export-knowledge.sh [format] [output_path]

set -e

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMAT="${1:-json}"
OUTPUT_PATH="${2:-${AURA_DIR}/data/exports/knowledge_$(date +%Y%m%d_%H%M%S).${FORMAT}}"

echo "AURA Knowledge Export"
echo "====================="
echo "Format: ${FORMAT}"
echo "Output: ${OUTPUT_PATH}"
echo ""

mkdir -p "$(dirname "${OUTPUT_PATH}")"

if [ "$FORMAT" = "json" ]; then
    curl -s http://localhost:8000/api/v1/knowledge/export \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{"format":"json"}' \
        > "${OUTPUT_PATH}"
    echo "✓ JSON export complete"
else
    echo "✗ Unsupported format: ${FORMAT}"
    echo "Supported: json"
    exit 1
fi

echo ""
echo "File: ${OUTPUT_PATH}"
echo "Size: $(du -h "${OUTPUT_PATH}" | cut -f1)"
