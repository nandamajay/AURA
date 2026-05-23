"""AURA Core Orchestrator — FastAPI app with all routers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from aura_sdk.logging.logger import configure_logging, get_logger
from core.config import Config
from core.lifespan import lifespan, get_uptime
from core.routers import (
    agents,
    auth,
    charter,
    engineering,
    governance,
    health,
    knowledge,
    memory,
    patches,
    provenance,
    simulation,
    tasks,
)

configure_logging(Config.LOG_LEVEL)
logger = get_logger("core")

app = FastAPI(
    title="AURA Core Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(patches.router, prefix="/api/v1/patches", tags=["patches"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(governance.router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(engineering.router, prefix="/api/v1/engineering", tags=["engineering"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["simulation"])
app.include_router(memory.router, prefix="/api/v1/memory", tags=["memory"])
app.include_router(charter.router, prefix="/api/v1/charter", tags=["charter"])
app.include_router(provenance.router, prefix="/api/v1/provenance", tags=["provenance"])

# ── Metrics endpoint (Prometheus format) ──
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    uptime = get_uptime()
    return f"""# HELP aura_uptime_seconds Service uptime
# TYPE aura_uptime_seconds gauge
aura_uptime_seconds {{service="core"}} {uptime}

# HELP aura_info Service information
# TYPE aura_info gauge
aura_info {{version="{Config.VERSION}"}} 1
"""
