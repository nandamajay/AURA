# Executor Heartbeat Spec

## Purpose
Track untrusted executor liveness without granting governance authority.

## Required fields
- `heartbeat_counter` (integer, monotonic per executor)
- `heartbeat_timestamp` (string epoch timestamp)
- `connection_state` (`connected|disconnected|rejected|unknown`)

## Validation behavior (Linux governance)
- missing heartbeat payload -> advisory downgrade
- malformed heartbeat timestamp -> advisory downgrade
- stale heartbeat (older than configured threshold) -> advisory downgrade

## Trust model
- heartbeat informs transport confidence only
- heartbeat does not imply runtime or semantic correctness
