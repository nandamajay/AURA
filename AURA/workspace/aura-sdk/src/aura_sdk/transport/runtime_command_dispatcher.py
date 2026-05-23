"""Transport-agnostic runtime command dispatcher.

All commands are logged deterministically and fail closed on errors.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    RuntimeTransportAPI,
    TransportResponse,
)


class RuntimeCommandDispatcher:
    def __init__(self, log_path: str | Path | None = None):
        self._adapters: dict[str, RuntimeTransportAPI] = {}
        self._log_path = Path(log_path) if log_path else None
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def register(self, name: str, adapter: RuntimeTransportAPI) -> None:
        self._adapters[name] = adapter

    def execute(
        self,
        transport: str,
        command: str,
        *,
        timeout_ms: int = 10_000,
        classification: CommandClassification | None = None,
        operator_approved: bool = False,
    ) -> TransportResponse:
        adapter = self._adapters.get(transport)
        if not adapter:
            resp = TransportResponse(
                transport=transport,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"transport_not_registered:{transport}",
                timestamp=str(time.time()),
                duration_ms=0,
                runtime_state="unknown",
                confidence="unknown",
                classification=classification or CommandClassification.SAFE_READ,
            )
            self._log(resp)
            return resp

        resp = adapter.execute(
            command,
            timeout_ms=timeout_ms,
            classification=classification,
            operator_approved=operator_approved,
        )
        self._log(resp)
        return resp

    def _log(self, response: TransportResponse) -> None:
        if not self._log_path:
            return
        payload: dict[str, Any] = response.model_dump(mode="json")
        payload["logged_at"] = time.time()
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
