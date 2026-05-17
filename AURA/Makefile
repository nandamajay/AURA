# AURA Platform — Phase 0 Foundation
# Makefile for development, testing, and operations

.PHONY: help up down dev logs shell-core test lint bootstrap backup health metrics export-knowledge compliance-export hardening-check clean status

# ── Help ───────────────────────────────────────────
help: ## Show this help
	@echo "AURA Platform — Available Commands"
	@echo "=================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# ── Docker ─────────────────────────────────────────
up: ## Start all services in production mode
	docker compose up --build -d

down: ## Stop all services
	docker compose down

dev: ## Start in development mode with hot reload
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build -d

logs: ## Follow service logs
	docker compose logs -f

logs-core: ## Follow core service logs
	docker compose logs -f aura-core

logs-llm: ## Follow LLM gateway logs
	docker compose logs -f llm-gateway

# ── Shell Access ───────────────────────────────────
shell-core: ## Open shell in core service
	docker compose exec aura-core bash

shell-llm: ## Open shell in LLM gateway
	docker compose exec llm-gateway bash

shell-db: ## Open SQLite CLI on database
	docker compose exec aura-core sqlite3 /data/aura.db

# ── Testing ────────────────────────────────────────
test: ## Run all tests
	docker compose exec -u 0 aura-core sh -lc 'if [ -d /workspace/aura-sdk/tests ] && ls /workspace/aura-sdk/tests/test*.py >/dev/null 2>&1; then python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(\"pytest\") else 1)" || python -m pip install --no-cache-dir pytest pytest-asyncio >/dev/null; cd /workspace/aura-sdk && python -m pytest tests/ -v; else echo "aura-sdk tests: not yet implemented"; fi'
	docker compose exec -u 0 aura-core sh -lc 'if [ -d /app/tests ] && ls /app/tests/test*.py >/dev/null 2>&1; then python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(\"pytest\") else 1)" || python -m pip install --no-cache-dir pytest pytest-asyncio >/dev/null; cd /app && python -m pytest tests/ -v; else echo "core tests: not yet implemented"; fi'
	docker compose exec llm-gateway sh -lc 'if [ -d /app/tests ] && ls /app/tests/test*.py >/dev/null 2>&1; then python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(\"pytest\") else 1)" || python -m pip install --no-cache-dir pytest pytest-asyncio >/dev/null; cd /app && python -m pytest tests/ -v; else echo "llm-gateway tests: not yet implemented"; fi'
	docker compose exec ws-server sh -lc 'if [ -d /app/tests ] && ls /app/tests/test*.py >/dev/null 2>&1; then python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(\"pytest\") else 1)" || python -m pip install --no-cache-dir pytest pytest-asyncio >/dev/null; cd /app && python -m pytest tests/ -v; else echo "ws-server tests: not yet implemented"; fi'

test-sdk: ## Run aura-sdk tests
	docker compose exec -u 0 aura-core sh -lc 'python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(\"pytest\") else 1)" || python -m pip install --no-cache-dir pytest pytest-asyncio >/dev/null; cd /workspace/aura-sdk && python -m pytest tests/ -v'

# ── Linting ────────────────────────────────────────
lint: ## Lint all Python code
	cd workspace/aura-sdk && ruff check . 2>/dev/null || echo "aura-sdk lint: ruff not installed"
	cd services/core && ruff check . 2>/dev/null || echo "core lint: ruff not installed"
	cd services/llm-gateway && ruff check . 2>/dev/null || echo "llm-gateway lint: ruff not installed"
	cd services/ws-server && ruff check . 2>/dev/null || echo "ws-server lint: ruff not installed"

format: ## Format all Python code
	cd workspace/aura-sdk && ruff format . 2>/dev/null || echo "aura-sdk format: ruff not installed"
	cd services/core && ruff format . 2>/dev/null || echo "core format: ruff not installed"

# ── Bootstrap ──────────────────────────────────────
bootstrap: ## Run first-time setup wizard
	./scripts/bootstrap.sh

# ── Health & Monitoring ────────────────────────────
health: ## Check system health
	@curl -s http://localhost:8000/health/ready | python -m json.tool 2>/dev/null || echo "Health check failed — is the system running?"

health-live: ## Quick liveness check
	@curl -s http://localhost:8000/health/live | python -m json.tool 2>/dev/null || echo "Liveness check failed"

metrics: ## Get Prometheus metrics
	@curl -s http://localhost:8000/metrics

status: ## Show system status
	@echo "=== AURA System Status ==="
	@echo ""
	@echo "Docker Services:"
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  Docker not running"
	@echo ""
	@echo "Health:"
	@curl -s http://localhost:8000/health/ready 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print(f'  Status: {d[\"status\"]}\n  Uptime: {d.get(\"uptime_seconds\",0):.0f}s')" 2>/dev/null || echo "  Not available"

# ── Operations ─────────────────────────────────────
backup: ## Backup SQLite database
	./scripts/backup.sh

export-knowledge: ## Export knowledge base
	./scripts/export-knowledge.sh

compliance-export: ## Export compliance bundle (audit/users/approvals/patches/tasks)
	./scripts/compliance-export.sh

hardening-check: ## Run infrastructure hardening checks
	./scripts/hardening-check.sh

clean: ## Clean build artifacts and Docker volumes
	docker compose down -v --remove-orphans
	rm -rf data/aura.db data/aura.db-wal data/aura.db-shm
	rm -rf dashboard/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# ── Development ────────────────────────────────────
install-sdk: ## Install aura-sdk in development mode
	pip install -e workspace/aura-sdk[all,dev]

install-core: ## Install core service dependencies
	pip install -e services/core

dashboard-dev: ## Start dashboard dev server
	cd dashboard && npm install && npm run dev

.PHONY: install-sdk install-core dashboard-dev
