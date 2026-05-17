# AURA — Audio Upstream Refactor Agent

Autonomous multi-agent platform for upstreaming Qualcomm Audio drivers to the Linux kernel.

## Quick Start

```bash
# 1. Configure
export OPENAI_API_KEY=sk-your-key
export JWT_SECRET=$(openssl rand -hex 16)

# 2. Launch
make up

# 3. Access
curl http://localhost:8000/health/ready
open http://localhost:3000  # Dashboard
```

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │────▶│  aura-core   │────▶│ llm-gateway  │──▶ OpenAI
│   Port 3000  │◄────│   Port 8000  │     │   Port 8002  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴──────┐
                     │   ws-server  │
                     │   Port 8001  │
                     └─────────────┘
                            │
                     ┌──────┴──────┐
                     │   SQLite     │
                     │  /data/aura  │
                     └─────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| aura-core | 8000 | Orchestrator, REST API, governance |
| llm-gateway | 8002 | OpenAI proxy with caching |
| ws-server | 8001 | WebSocket + SSE streaming |
| dashboard | 3000 | React dashboard |

## Development

```bash
# Dev mode with hot reload
make dev

# Run tests
make test

# Lint code
make lint

# View logs
make logs-core

# Database shell
make shell-db
```

## Project Structure

```
AURA/
├── workspace/aura-sdk/   # Shared library
├── services/
│   ├── core/             # Orchestrator
│   ├── llm-gateway/      # LLM proxy
│   └── ws-server/        # WebSocket server
├── agents/               # CLI agents
├── dashboard/            # React frontend
├── plugins/              # Subsystem plugins
├── knowledge/schema/     # SQLite migrations
├── scripts/              # Operational scripts
├── docker-compose.yml    # Service topology
└── Makefile             # Dev commands
```

## Documentation

- [Architecture Specs](specs/) — Full P0/P1/P2 specifications
- [Constitution](AURA_IMMUTABLE_ARCHITECTURE_CONSTITUTION.md) — Immutable architecture rules

## License

Proprietary — All rights reserved.
