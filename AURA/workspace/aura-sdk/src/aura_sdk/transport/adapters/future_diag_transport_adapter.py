"""Future DSP/diag transport adapter placeholder."""

from __future__ import annotations

from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    TransportMetadata,
    TransportResponse,
    make_blocked_response,
)


class FutureDiagTransportAdapter:
    def __init__(self, target: str | None = None):
        self.metadata = TransportMetadata(transport="future_diag", target=target)

    def execute(self, command: str, *, timeout_ms: int = 10_000, classification: CommandClassification | None = None, operator_approved: bool = False) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, command, classification or CommandClassification.REQUIRES_OPERATOR_APPROVAL, "future_diag_not_implemented")

    def push_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"push {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "future_diag_not_implemented")

    def pull_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"pull {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "future_diag_not_implemented")

    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "capture_stream", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "future_diag_not_implemented")

    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "wait_for_prompt", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "future_diag_not_implemented")

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "check_connectivity", CommandClassification.SAFE_READ, "future_diag_not_implemented")

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "collect_environment_metadata", CommandClassification.SAFE_READ, "future_diag_not_implemented")
