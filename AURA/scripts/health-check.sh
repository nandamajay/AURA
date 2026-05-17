#!/usr/bin/env bash
# AURA Health Check — Quick system diagnostics
# Usage: ./scripts/health-check.sh

set -e

echo "AURA System Diagnostics"
echo "======================="
echo ""

# Check Docker
echo -n "Docker:         "
if docker info > /dev/null 2>&1; then
    echo "✓ Running"
else
    echo "✗ Not running"
    exit 1
fi

# Check services
echo -n "Core Service:   "
if curl -s http://localhost:8000/health/live > /dev/null 2>&1; then
    STATUS=$(curl -s http://localhost:8000/health/ready | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    echo "✓ ${STATUS}"
else
    echo "✗ Not responding"
fi

echo -n "LLM Gateway:    "
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "✓ Healthy"
else
    echo "✗ Not responding"
fi

echo -n "WS Server:      "
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "✓ Healthy"
else
    echo "✗ Not responding"
fi

echo -n "Dashboard:      "
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "✓ Responding"
else
    echo "✗ Not responding"
fi

echo ""
echo "Database:"
DB_SIZE=$(du -h ./data/aura.db 2>/dev/null | cut -f1 || echo "N/A")
echo "  Size: ${DB_SIZE}"

# Check disk space
DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}')
echo "  Disk: ${DISK_USAGE} used"

echo ""
