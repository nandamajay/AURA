"""LLM Gateway service — FastAPI app."""

import asyncio
import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from aura_sdk.logging.logger import configure_logging, get_logger
from llm_gateway.budget import TokenBudgetManager
from llm_gateway.cache import ResponseCache
from llm_gateway.config import Config

# Configure logging
configure_logging(Config.LOG_LEVEL)
logger = get_logger("llm_gateway")

# Validate config on import
config_errors = Config.validate()
if config_errors:
    for err in config_errors:
        logger.warning(f"Config issue: {err}")

# Service state
cache = ResponseCache(maxsize=Config.CACHE_SIZE)
budget = TokenBudgetManager(daily_limit=Config.TOKEN_BUDGET_DAILY)
app = FastAPI(title="AURA LLM Gateway", version="0.1.0")


class CompletionRequest(BaseModel):
    """Validated completion request body."""

    agent_type: str = "unknown"
    task_id: str = ""
    model: str = Config.DEFAULT_MODEL
    messages: list[dict[str, object]] = Field(default_factory=list)
    temperature: float = 0.1
    max_tokens: int = 4000
    seed: int = 42


@app.on_event("startup")
async def startup():
    logger.info(
        "llm_gateway.startup",
        provider=Config.LLM_PROVIDER,
        mock_mode=Config.LLM_MOCK_MODE,
        gateway_url=Config.OPENAI_BASE_URL,
        qgenie_command=Config.QGENIE_COMMAND,
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "llm-gateway",
        "version": "0.1.0",
        "provider": Config.LLM_PROVIDER,
        "mock_mode": Config.LLM_MOCK_MODE,
    }


@app.get("/")
async def root():
    return {
        "service": "llm-gateway",
        "status": "ok",
        "provider": Config.LLM_PROVIDER,
        "mock_mode": Config.LLM_MOCK_MODE,
        "endpoints": ["/health", "/budget", "/cache/clear", "/v1/completions"],
    }


@app.get("/budget")
async def get_budget():
    return budget.get_usage()


@app.post("/cache/clear")
async def clear_cache():
    cleared = cache.clear()
    return {"cleared": cleared}


@app.post("/v1/completions")
async def completions(body: CompletionRequest):
    """Proxy completion request to provider with caching and budget control."""
    start_time = time.time()
    agent_type = body.agent_type
    task_id = body.task_id
    model = body.model
    selected_model = model
    messages = body.messages
    temperature = body.temperature
    max_tokens = body.max_tokens
    seed = body.seed

    # Check budget
    estimated = _estimate_tokens(messages, max_tokens)
    allowed, budget_info = budget.check_budget(estimated)
    if not allowed:
        logger.warning("budget_exceeded", agent_type=agent_type, task_id=task_id)
        raise HTTPException(status_code=429, detail="Daily token budget exceeded")

    # Check cache
    cache_key_data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "seed": seed,
        "max_tokens": max_tokens,
    }
    cached = cache.get(cache_key_data)
    if cached:
        logger.info("cache_hit", agent_type=agent_type, task_id=task_id)
        return {
            **cached,
            "cached": True,
            "latency_ms": int((time.time() - start_time) * 1000),
        }

    # Call provider
    provider = Config.LLM_PROVIDER
    try:
        if Config.LLM_MOCK_MODE:
            content = _call_mock(
                model=model,
                messages=messages,
                agent_type=agent_type,
                task_id=task_id,
            )
            prompt_tokens = _estimate_tokens(messages, 0)
            completion_tokens = max(1, len(content) // 4)
            total_tokens = prompt_tokens + completion_tokens
            cost_usd = 0.0
        elif provider == "qgenie":
            content, selected_model = await _call_qgenie_with_fallback(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            prompt_tokens = _estimate_tokens(messages, 0)
            completion_tokens = max(1, len(content) // 4)
            total_tokens = prompt_tokens + completion_tokens
            cost_usd = 0.0
        else:
            response_data = await _call_openai(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            )
            prompt_tokens = response_data.get("usage", {}).get("prompt_tokens", 0)
            completion_tokens = response_data.get("usage", {}).get("completion_tokens", 0)
            total_tokens = prompt_tokens + completion_tokens
            # Pricing: GPT-4o ~$5/1M input tokens, $15/1M output tokens
            cost_usd = (prompt_tokens / 1_000_000 * 5.0) + (completion_tokens / 1_000_000 * 15.0)
            content = response_data["choices"][0]["message"]["content"] if response_data.get("choices") else ""
    except httpx.HTTPStatusError as e:
        logger.error("openai_error", status=e.response.status_code, detail=str(e))
        if e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="OpenAI rate limit")
        raise HTTPException(status_code=502, detail="OpenAI error")
    except httpx.TimeoutException:
        logger.error("openai_timeout", task_id=task_id)
        raise HTTPException(status_code=504, detail="OpenAI timeout")
    except asyncio.TimeoutError:
        logger.error("qgenie_timeout", task_id=task_id)
        raise HTTPException(status_code=504, detail="QGenie timeout")
    except FileNotFoundError:
        logger.error("qgenie_missing", command=Config.QGENIE_COMMAND)
        raise HTTPException(status_code=503, detail="QGenie command not found")
    except RuntimeError as e:
        logger.error("qgenie_error", detail=str(e))
        raise HTTPException(status_code=502, detail="QGenie error")

    latency_ms = int((time.time() - start_time) * 1000)

    # Record budget usage
    budget.record_usage(agent_type, total_tokens)

    # Build response
    result = {
        "content": content,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
        },
        "cached": False,
        "provider": provider,
        "mock_mode": Config.LLM_MOCK_MODE,
        "model": selected_model,
        "latency_ms": latency_ms,
    }

    # Cache result
    cache.put(cache_key_data, {k: v for k, v in result.items() if k != "latency_ms"})

    logger.info(
        "completion",
        agent_type=agent_type,
        task_id=task_id,
        tokens=total_tokens,
        cost_usd=round(cost_usd, 6),
        latency_ms=latency_ms,
    )

    return result


async def _call_openai(model: str, messages: list, temperature: float, max_tokens: int, seed: int) -> dict:
    """Make async request to OpenAI API."""
    async with httpx.AsyncClient(timeout=Config.REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{Config.OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "seed": seed,
            },
        )
        response.raise_for_status()
        return response.json()


async def _call_qgenie(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """Run qgenie CLI as completion backend."""
    prompt = _build_qgenie_prompt(messages)
    cmd = [
        Config.QGENIE_COMMAND,
        "ask",
        "--model",
        model,
        "--temperature",
        str(temperature),
        "--max-tokens",
        str(max_tokens),
        prompt,
    ]

    env = os.environ.copy()
    if Config.QGENIE_API_KEY:
        env["QGENIE_API_KEY"] = Config.QGENIE_API_KEY
    if Config.QGENIE_CLI_HOME:
        env["QGENIE_CLI_HOME"] = Config.QGENIE_CLI_HOME

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=Config.REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        raise

    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())

    return stdout.decode("utf-8", errors="replace").strip()


async def _call_qgenie_with_fallback(
    model: str,
    messages: list,
    temperature: float,
    max_tokens: int,
) -> tuple[str, str]:
    """Run qgenie with compatibility fallback for legacy model IDs.

    Some callers still send OpenAI-style model names (for example `gpt-4o-*`).
    When QGenie returns an invalid-model error, retry once with the configured
    gateway default model so agent executions do not fail open into fallback text.
    """
    selected_model = model or Config.DEFAULT_MODEL
    try:
        content = await _call_qgenie(
            model=selected_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content, selected_model
    except RuntimeError as exc:
        error_text = str(exc)
        can_retry = (
            selected_model != Config.DEFAULT_MODEL
            and ("Invalid Model" in error_text or "Invalid model" in error_text)
        )
        if not can_retry:
            raise
        logger.warning(
            "qgenie_model_fallback",
            requested_model=selected_model,
            fallback_model=Config.DEFAULT_MODEL,
        )
        content = await _call_qgenie(
            model=Config.DEFAULT_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content, Config.DEFAULT_MODEL


def _build_qgenie_prompt(messages: list[dict]) -> str:
    """Convert chat-style messages to a single prompt for qgenie ask."""
    if not messages:
        return ""
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = str(message.get("content", ""))
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _call_mock(model: str, messages: list, agent_type: str, task_id: str) -> str:
    """Deterministic local response for development/test without API credentials."""
    last_user = ""
    for msg in reversed(messages):
        if str(msg.get("role", "")).lower() == "user":
            last_user = str(msg.get("content", "")).strip()
            break
    if not last_user and messages:
        last_user = str(messages[-1].get("content", "")).strip()
    last_user = last_user[:240]
    return (
        "MOCK_RESPONSE\n"
        f"provider={Config.LLM_PROVIDER}\n"
        f"model={model}\n"
        f"agent_type={agent_type}\n"
        f"task_id={task_id}\n"
        f"echo={last_user}"
    )


def _estimate_tokens(messages: list, max_tokens: int) -> int:
    """Rough token estimation for budget pre-check.

    ~4 chars per token for English text.
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        total_chars += len(content)
    estimated_input = total_chars // 4
    return estimated_input + max_tokens
