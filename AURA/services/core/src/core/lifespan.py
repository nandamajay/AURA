"""Application lifespan — startup and shutdown hooks."""

import time

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aura_sdk.db.connection import init_db
from aura_sdk.logging.logger import configure_logging, get_logger
from aura_sdk.models.event import EventType
from aura_sdk.replay import TaskRecorder
from aura_sdk.transport.runtime_execution_contract import resolve_runtime_contract
from core.config import Config
from core.contracts.transport_artifact_contracts import runtime_environment_diagnostics
from core.events import publish_event, start_event_bus, stop_event_bus
from core.services.agent_runtime import AgentRuntimeManager
from core.services.circuit_breaker import CircuitBreakerManager
from core.services.task_queue import TaskQueueManager
from core.services.watchdog import WatchdogConfig, WatchdogManager

_startup_time = time.time()

configure_logging(Config.LOG_LEVEL)
logger = get_logger("core")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Startup:
    1. Validate environment
    2. Initialize database (run migrations)
    3. Initialize plugin registry
    4. Start event bus dispatcher
    5. Mark ready
    """
    # Startup
    logger.info("core.startup.begin", version=Config.VERSION)

    # Validate config
    errors = Config.validate()
    for err in errors:
        logger.warning("config_issue", error=err)

    execution_contract = resolve_runtime_contract("core-service")
    app.state.runtime_execution_contract = execution_contract.as_dict()
    logger.info(
        "runtime_execution_contract",
        classification=execution_contract.classification,
        python_version=execution_contract.python_version,
        containerized=execution_contract.containerized,
        fail_closed_reasons=execution_contract.fail_closed_reasons,
    )
    if execution_contract.classification != "PASS":
        raise RuntimeError(
            "core-service runtime execution contract failed: "
            + ",".join(execution_contract.fail_closed_reasons)
        )

    # Initialize database
    try:
        migration_count = await init_db(Config.SQLITE_PATH)
        logger.info("db_initialized", migrations=migration_count)
    except Exception as e:
        logger.error("db_init_failed", error=str(e))
        raise

    runtime_env = runtime_environment_diagnostics(sqlite_path=Config.SQLITE_PATH)
    app.state.runtime_environment = runtime_env.model_dump(mode="json")
    logger.info(
        "runtime_environment_validated",
        classification=runtime_env.classification,
        repo_root=runtime_env.repo_root,
        transport_root_exists=runtime_env.transport_root_exists,
        evidence_root_exists=runtime_env.evidence_root_exists,
        replay_store_exists=runtime_env.replay_store_exists,
    )
    if runtime_env.classification == "FAIL_CLOSED":
        logger.warning(
            "runtime_environment_fail_closed",
            fail_closed_reasons=runtime_env.fail_closed_reasons,
        )

    # Bootstrap admin user if no users exist
    await _bootstrap_admin()

    # Start event bus + ws forwarding bridge
    await start_event_bus(app, Config.WS_SERVER_URL)
    app.state.circuit_breakers = CircuitBreakerManager(event_bus=app.state.event_bus)
    app.state.watchdog = WatchdogManager(
        event_bus=app.state.event_bus,
        config=WatchdogConfig(max_watches=Config.MAX_CONCURRENT_AGENTS),
        replay_recorder=TaskRecorder(Config.SQLITE_PATH),
    )
    await app.state.watchdog.start()
    app.state.agent_runtime = AgentRuntimeManager(
        watchdog=app.state.watchdog,
        event_bus=app.state.event_bus,
        llm_gateway_url=Config.LLM_GATEWAY_URL,
        rules_path=Config.RULES_PATH,
        default_timeout_seconds=Config.AGENT_TIMEOUT_SECONDS,
    )
    app.state.task_queue = TaskQueueManager(
        runtime=app.state.agent_runtime,
        event_bus=app.state.event_bus,
        max_concurrent_agents=Config.MAX_CONCURRENT_AGENTS,
    )
    await app.state.task_queue.start()
    logger.info(
        "circuit_breaker_manager_started",
        failure_threshold=app.state.circuit_breakers.config.failure_threshold,
        window_seconds=app.state.circuit_breakers.config.window_seconds,
        cooldown_seconds=app.state.circuit_breakers.config.cooldown_seconds,
    )
    logger.info(
        "watchdog_manager_started",
        heartbeat_interval_seconds=app.state.watchdog.config.heartbeat_interval_seconds,
        missed_threshold=app.state.watchdog.config.missed_threshold,
        check_interval_seconds=app.state.watchdog.config.check_interval_seconds,
        sigterm_wait_seconds=app.state.watchdog.config.sigterm_wait_seconds,
        max_watches=app.state.watchdog.config.max_watches,
    )
    await publish_event(
        app,
        EventType.SERVICE_STARTED,
        {"service": Config.SERVICE_NAME, "version": Config.VERSION},
        trace_id="core-startup",
    )

    logger.info("core.startup.complete", uptime=round(time.time() - _startup_time, 2))

    yield

    # Shutdown
    watchdog = getattr(app.state, "watchdog", None)
    agent_runtime = getattr(app.state, "agent_runtime", None)
    task_queue = getattr(app.state, "task_queue", None)
    if task_queue is not None:
        await task_queue.stop()
    if agent_runtime is not None:
        await agent_runtime.stop()
    if watchdog is not None:
        await watchdog.stop()

    await publish_event(
        app,
        EventType.SERVICE_STOPPED,
        {"service": Config.SERVICE_NAME, "version": Config.VERSION},
        trace_id="core-shutdown",
    )
    await stop_event_bus(app)
    logger.info("core.shutdown")


async def _bootstrap_admin() -> None:
    """Create admin user on first startup if users table is empty."""
    from aura_sdk.db.connection import get_db
    import bcrypt

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE email = ?",
            (Config.ADMIN_EMAIL,),
        )
        row = await cursor.fetchone()
        if row and row[0] == 0:
            # Create admin user
            password_hash = bcrypt.hashpw(
                Config.ADMIN_PASSWORD.encode(), bcrypt.gensalt(rounds=12)
            ).decode()
            await db.execute(
                """
                INSERT INTO users (email, password_hash, role, display_name)
                VALUES (?, ?, 'admin', 'Administrator')
                """,
                (Config.ADMIN_EMAIL, password_hash),
            )
            await db.commit()
            logger.info(
                "bootstrap_admin_created",
                email=Config.ADMIN_EMAIL,
                message="Bootstrap complete. Login with ADMIN_EMAIL/ADMIN_PASSWORD",
            )


def get_uptime() -> float:
    return time.time() - _startup_time
