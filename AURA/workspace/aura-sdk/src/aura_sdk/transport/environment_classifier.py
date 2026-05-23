"""Runtime target environment classifier for governed transport cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EnvironmentClassification:
    primary_environment: str
    detected_environments: list[str]
    confidence: str
    evidence: dict[str, list[str]]


def _lower(text: str | None) -> str:
    return (text or "").lower()


def _collect_markers(text: str, markers: Mapping[str, list[str]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for key, values in markers.items():
        hits = [marker for marker in values if marker in text]
        if hits:
            found[key] = hits
    return found


def classify_target_environment(probe_outputs: Mapping[str, dict[str, Any]]) -> EnvironmentClassification:
    """Classify runtime target from probe evidence.

    The classifier is heuristic and fail-closed: unknown signals are not promoted to
    certainty. All evidence markers are preserved for operator review.
    """

    combined = "\n".join(
        _lower(entry.get("stdout", "")) + "\n" + _lower(entry.get("stderr", ""))
        for entry in probe_outputs.values()
    )

    markers = {
        "android": ["android", "ro.build", "/system/bin", "zygote", "init.rc"],
        "embedded_linux": ["linux version", "busybox", "buildroot", "init "],
        "qemu": ["qemu", "virtio", "ranchu", "goldfish", "qemuarm"],
        "yocto": ["yocto", "poky", "oe-core", "openembedded"],
        "qualcomm_linux": ["qcom", "qualcomm", "qcs", "rb3", "adsp", "qdsp", "msm"],
        "ubuntu": ["ubuntu", "debian"],
    }
    evidence = _collect_markers(combined, markers)

    detected: list[str] = []

    # Android signal includes explicit getprop success.
    getprop = probe_outputs.get("getprop ro.build.fingerprint")
    if getprop:
        getprop_ok = int(getprop.get("exit_code", 1)) == 0 and bool(
            str(getprop.get("stdout", "")).strip()
        )
        if getprop_ok:
            evidence.setdefault("android", []).append("getprop ro.build.fingerprint")

    if "android" in evidence and "getprop ro.build.fingerprint" in evidence.get("android", []):
        detected.append("Android")

    if "embedded_linux" in evidence or "android" not in evidence:
        detected.append("Embedded Linux")

    if "qemu" in evidence:
        detected.append("QEMU")
    if "yocto" in evidence:
        detected.append("Yocto")
    if "qualcomm_linux" in evidence:
        detected.append("Qualcomm Linux")
    if "ubuntu" in evidence:
        detected.append("Ubuntu")

    # Deduplicate while preserving order.
    dedup: list[str] = []
    for value in detected:
        if value not in dedup:
            dedup.append(value)

    if not dedup:
        dedup = ["Unknown"]

    primary = dedup[0]
    confidence = "LOW"
    if len(evidence) >= 4:
        confidence = "HIGH"
    elif len(evidence) >= 2:
        confidence = "MEDIUM"

    return EnvironmentClassification(
        primary_environment=primary,
        detected_environments=dedup,
        confidence=confidence,
        evidence=evidence,
    )
