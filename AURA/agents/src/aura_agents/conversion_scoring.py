"""Deterministic conversion scoring for AURA driver comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCORING_ENGINE = "aura_conversion_scoring_v1"
SCORING_ENGINE_VERSION = "1.2.0"

FUNCTION_MATCH = "FUNCTION_MATCH"
API_COVERAGE = "API_COVERAGE"
REGISTER_COVERAGE = "REGISTER_COVERAGE"
DAPM_WIDGETS = "DAPM_WIDGETS"
DAPM_ROUTES = "DAPM_ROUTES"
DAPM_CONTROLS = "DAPM_CONTROLS"
LIFECYCLE_PATTERN = "LIFECYCLE_PATTERN"
DT_PROPERTY_COVERAGE = "DT_PROPERTY_COVERAGE"
VENDOR_ELIMINATION = "VENDOR_ELIMINATION"
INCLUDE_ALIGNMENT = "INCLUDE_ALIGNMENT"

CATEGORY_ORDER = (
    FUNCTION_MATCH,
    API_COVERAGE,
    REGISTER_COVERAGE,
    DAPM_WIDGETS,
    DAPM_ROUTES,
    DAPM_CONTROLS,
    LIFECYCLE_PATTERN,
    DT_PROPERTY_COVERAGE,
    VENDOR_ELIMINATION,
    INCLUDE_ALIGNMENT,
)

REGISTER_NORMALIZATION_RULES = (
    "strip _MACRO_ infix",
    "strip LPASS_ prefix",
)

DEFAULT_BANNED_SYMBOL_PATTERNS = (
    {"name": "lpass_cdc_register_macro", "pattern": r"\blpass_cdc_register_macro\b", "regex": True},
    {"name": "lpass_cdc_unregister_macro", "pattern": r"\blpass_cdc_unregister_macro\b", "regex": True},
    {"name": "lpass_cdc_clk_rsc", "pattern": r"\blpass_cdc_clk_rsc\b", "regex": True},
    {"name": "lpass_cdc_rsc_clk", "pattern": r"\blpass_cdc_rsc_clk\b", "regex": True},
    {"name": "swrm_wcd_notify", "pattern": r"\bswrm_wcd_notify\b", "regex": True},
    {"name": "SWR_DEVICE_SSR", "pattern": r"\bSWR_DEVICE_SSR\b", "regex": True},
    {"name": "SWR_SET_PORT_MAP", "pattern": r"\bSWR_SET_PORT_MAP\b", "regex": True},
    {"name": "SWR_REGISTER_WAKE_IRQ", "pattern": r"\bSWR_REGISTER_WAKE_IRQ\b", "regex": True},
    {"name": "msm_cdc_pinctrl", "pattern": r"\bmsm_cdc_pinctrl\b", "regex": True},
    {
        "name": "LINUX_VERSION_CODE_in_if",
        "pattern": r"^\s*#\s*if.*\bLINUX_VERSION_CODE\b",
        "regex": True,
    },
    {
        "name": "KERNEL_VERSION_in_if",
        "pattern": r"^\s*#\s*if.*\bKERNEL_VERSION\b",
        "regex": True,
    },
    {"name": "CONFIG_BOLERO", "pattern": r"\bCONFIG_BOLERO\b", "regex": True},
    {"name": "include_swr-wcd.h", "pattern": r"^\s*#\s*include\s*[<\"].*swr-wcd\.h[>\"]", "regex": True},
    {"name": "include_swr-common.h", "pattern": r"^\s*#\s*include\s*[<\"].*swr-common\.h[>\"]", "regex": True},
    {"name": "include_lpass-cdc.h", "pattern": r"^\s*#\s*include\s*[<\"].*lpass-cdc\.h[>\"]", "regex": True},
    {
        "name": "include_lpass-cdc-registers.h",
        "pattern": r"^\s*#\s*include\s*[<\"].*lpass-cdc-registers\.h[>\"]",
        "regex": True,
    },
    {
        "name": "include_lpass-cdc-clk-rsc.h",
        "pattern": r"^\s*#\s*include\s*[<\"].*lpass-cdc-clk-rsc\.h[>\"]",
        "regex": True,
    },
    {"name": "include_linux/version.h", "pattern": r"^\s*#\s*include\s*[<\"].*linux/version\.h[>\"]", "regex": True},
    {
        "name": "include_msm-cdc-pinctrl.h",
        "pattern": r"^\s*#\s*include\s*[<\"].*msm-cdc-pinctrl\.h[>\"]",
        "regex": True,
    },
)


KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "do",
    "case",
}

API_PREFIXES = (
    "devm_",
    "clk_",
    "regmap_",
    "snd_soc_",
    "sdw_",
    "pm_runtime_",
    "platform_",
    "of_",
    "device_",
    "module_",
    "__module_",
    "regulator_",
    "reset_",
    "thermal_",
    "hwmon_",
    "mutex_",
    "spin_",
)
API_EXACT = {"kfree", "kzalloc", "dev_err", "dev_info", "dev_dbg"}

FUNCTION_DEF_RE = re.compile(
    r"^\s*(?:static\s+)?(?:[\w\*]+\s+)+(\w+)\s*\([^;{}]*\)\s*\{",
    re.MULTILINE,
)
FUNCTION_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
REGISTER_DEFINE_RE = re.compile(
    r"^\s*#define\s+(CDC_\w+|WSA\w+|VA\w+|TX\w+|RX\w+|LPASS_\w+|WCD\w+)\s+",
    re.MULTILINE,
)
DAPM_WIDGET_RE = re.compile(r"\bSND_SOC_DAPM_[A-Z_]+\s*\(")
DAPM_ROUTE_ARRAY_RE = re.compile(
    r"(?:struct\s+)?snd_soc_dapm_route\s+\w+\s*\[\]\s*=\s*\{(?P<body>.*?)\};",
    re.DOTALL,
)
DAPM_ROUTE_ENTRY_RE = re.compile(r"\{\s*\"[^\"]*\"\s*,\s*(?:NULL|\"[^\"]*\")\s*,\s*\"[^\"]*\"\s*\}")
DAPM_ROUTE_ENTRY_FALLBACK_RE = re.compile(r"\{\s*\"[^\"]*\"\s*,\s*(?:NULL|\"[^\"]*\")\s*,\s*\"[^\"]*\"\s*\}")
DAPM_CONTROL_RE = re.compile(r"\bSOC_(?:SINGLE\w*|ENUM\w*|DAPM\w*|VALUE\w*)\s*\(")
INCLUDE_RE = re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE)
QUOTED_INCLUDE_RE = re.compile(r"^\s*#\s*include\s*\"([^\"]+)\"", re.MULTILINE)

OF_PROP_LITERAL_RE = re.compile(r"\bof_property_read_\w+\s*\([^;]*?\"([A-Za-z0-9_\-]+)\"", re.DOTALL)
DEV_PROP_LITERAL_RE = re.compile(r"\bdevice_property_read_\w+\s*\([^;]*?\"([A-Za-z0-9_\-]+)\"", re.DOTALL)
FWNODE_PROP_LITERAL_RE = re.compile(r"\bfwnode_property_read_\w+\s*\([^;]*?\"([A-Za-z0-9_\-]+)\"", re.DOTALL)

# Extract second-argument symbolic property names from read calls.
PROP_SYMBOL_CALL_RE = re.compile(
    r"\b(?:of_property_read_\w+|device_property_read_\w+|fwnode_property_read_\w+)\s*\([^,]+,\s*([A-Za-z_]\w*)\s*,",
    re.DOTALL,
)

STRING_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_]\w*)\s+\"([^\"]+)\"", re.MULTILINE)
CHAR_PTR_ASSIGN_RE = re.compile(
    r"\b(?:const\s+)?char\s*\*\s*([A-Za-z_]\w*)\s*=\s*\"([^\"]+)\"\s*;",
    re.MULTILINE,
)
PLAIN_ASSIGN_RE = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*\"([^\"]+)\"\s*;", re.MULTILINE)

REGULATOR_GET_LITERAL_RE = re.compile(
    r"\b(?:devm_)?regulator_get(?:_optional|_exclusive)?\s*\([^;]*?\"([A-Za-z0-9_\-]+)\"",
    re.DOTALL,
)
CLK_GET_LITERAL_RE = re.compile(r"\bdevm_clk_get\w*\s*\([^;]*?\"([A-Za-z0-9_\-]+)\"", re.DOTALL)
CLK_PROVIDER_RE = re.compile(r"\b(?:devm_)?of_clk_add_hw_provider\s*\(")
FWNODE_PROP_CALL_RE = re.compile(r"\bfwnode_property_read_\w+\s*\(")
DEVICE_CHILD_NODE_RE = re.compile(r"\bdevice_for_each_child_node(?:_scoped)?\s*\(")

LIFECYCLE_ELEMENTS = (
    ("probe function exists", lambda text, fnames: any(name.endswith("_probe") or name == "probe" for name in fnames)),
    ("remove function exists", lambda text, fnames: any(name.endswith("_remove") or name == "remove" for name in fnames)),
    ("component_probe exists", lambda text, fnames: any(name.endswith("component_probe") for name in fnames)),
    ("runtime_suspend exists", lambda text, fnames: any(name.endswith("runtime_suspend") for name in fnames)),
    ("runtime_resume exists", lambda text, fnames: any(name.endswith("runtime_resume") for name in fnames)),
    ("SET_RUNTIME_PM_OPS or RUNTIME_PM_OPS present", lambda text, fnames: bool(re.search(r"\b(?:SET_RUNTIME_PM_OPS|RUNTIME_PM_OPS)\s*\(", text))),
    (
        "devm_regmap_init (mmio/sdw/i2c/spi/any) present",
        lambda text, fnames: bool(re.search(r"\bdevm_regmap_init(?:_(?:mmio|sdw|i2c|spi))?\s*\(", text)),
    ),
    ("devm_snd_soc_register_component present", lambda text, fnames: bool(re.search(r"\bdevm_snd_soc_register_component\s*\(", text))),
    ("of_device_id table present", lambda text, fnames: bool(re.search(r"\bof_device_id\b", text))),
    (
        "module_platform_driver OR module_sdw_driver OR module_i2c_driver present",
        lambda text, fnames: bool(re.search(r"\bmodule_(?:platform|sdw|i2c)_driver\s*\(", text)),
    ),
)


def _round_score(value: float) -> float:
    return round(float(value), 2)


def _sorted_unique(values: Iterable[str]) -> list[str]:
    dedup = {v.strip() for v in values if v and str(v).strip()}
    return sorted(dedup)


def _safe_division_score(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 100.0
    return (float(numerator) / float(denominator)) * 100.0


def _symmetric_count_match_score(upstream_count: int, converted_count: int) -> float:
    upper = max(upstream_count, converted_count)
    if upper == 0:
        return 100.0
    lower = min(upstream_count, converted_count)
    return (float(lower) / float(upper)) * 100.0


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_function_names(text: str) -> list[str]:
    names: list[str] = []
    for match in FUNCTION_DEF_RE.finditer(text):
        name = match.group(1)
        if name and name not in KEYWORDS:
            names.append(name)
    return _sorted_unique(names)


def _extract_api_calls(text: str) -> list[str]:
    names: list[str] = []
    for match in FUNCTION_CALL_RE.finditer(text):
        name = match.group(1)
        if not name or name in KEYWORDS:
            continue
        if name in API_EXACT or any(name.startswith(prefix) for prefix in API_PREFIXES):
            names.append(name)
    return _sorted_unique(names)


def _extract_register_defines(text: str) -> list[str]:
    return _sorted_unique(match.group(1) for match in REGISTER_DEFINE_RE.finditer(text))


def _extract_dapm_widget_count(text: str) -> int:
    return len(DAPM_WIDGET_RE.findall(text))


def _extract_dapm_route_count(text: str) -> int:
    total = 0
    for match in DAPM_ROUTE_ARRAY_RE.finditer(text):
        total += len(DAPM_ROUTE_ENTRY_RE.findall(match.group("body")))
    if total == 0:
        total = len(DAPM_ROUTE_ENTRY_FALLBACK_RE.findall(text))
    return total


def _extract_dapm_control_count(text: str) -> int:
    return len(DAPM_CONTROL_RE.findall(text))


def _extract_string_symbol_map(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for match in STRING_DEFINE_RE.finditer(text):
        mapping[match.group(1)] = match.group(2)

    for match in CHAR_PTR_ASSIGN_RE.finditer(text):
        mapping[match.group(1)] = match.group(2)

    for match in PLAIN_ASSIGN_RE.finditer(text):
        mapping[match.group(1)] = match.group(2)

    return mapping


def _extract_dt_properties(text: str) -> tuple[list[str], dict[str, bool]]:
    names: list[str] = []
    names.extend(OF_PROP_LITERAL_RE.findall(text))
    names.extend(DEV_PROP_LITERAL_RE.findall(text))
    names.extend(FWNODE_PROP_LITERAL_RE.findall(text))

    symbol_map = _extract_string_symbol_map(text)
    for match in PROP_SYMBOL_CALL_RE.finditer(text):
        symbol = match.group(1)
        literal = symbol_map.get(symbol)
        if literal:
            names.append(literal)

    for reg_name in REGULATOR_GET_LITERAL_RE.findall(text):
        names.append(f"{reg_name}-supply")

    for clk_name in CLK_GET_LITERAL_RE.findall(text):
        names.append(clk_name)

    if CLK_PROVIDER_RE.search(text):
        names.append("clock-output-names")

    signals = {
        "has_fwnode_property_read": bool(FWNODE_PROP_CALL_RE.search(text)),
        "has_device_for_each_child_node": bool(DEVICE_CHILD_NODE_RE.search(text)),
        "has_of_clk_add_hw_provider": bool(CLK_PROVIDER_RE.search(text)),
    }

    return _sorted_unique(names), signals


def _extract_includes(text: str) -> list[str]:
    return _sorted_unique(INCLUDE_RE.findall(text))


def _to_set(values: Iterable[str]) -> set[str]:
    return set(values)


def _overlap_payload(upstream_items: list[str], converted_items: list[str], formula: str) -> dict[str, Any]:
    upstream_set = _to_set(upstream_items)
    converted_set = _to_set(converted_items)
    matched = _sorted_unique(upstream_set.intersection(converted_set))
    missing = _sorted_unique(upstream_set.difference(converted_set))
    extra = _sorted_unique(converted_set.difference(upstream_set))
    score = _round_score(_safe_division_score(len(matched), len(upstream_set)))
    return {
        "score": score,
        "formula": formula,
        "upstream_count": len(upstream_set),
        "converted_count": len(converted_set),
        "matched_count": len(matched),
        "missing_from_converted": missing,
        "extra_in_converted": extra,
    }


def _normalize_register_symbol(symbol: str) -> str:
    value = symbol
    while value.startswith("LPASS_"):
        value = value[len("LPASS_") :]
    value = value.replace("_MACRO_", "_")
    return value


def _register_overlap_payload(upstream_raw: list[str], converted_raw: list[str]) -> dict[str, Any]:
    raw_upstream_set = _to_set(upstream_raw)
    raw_converted_set = _to_set(converted_raw)
    raw_matched = raw_upstream_set.intersection(raw_converted_set)

    upstream_normalized = _sorted_unique(_normalize_register_symbol(item) for item in upstream_raw)
    converted_normalized = _sorted_unique(_normalize_register_symbol(item) for item in converted_raw)

    normalized_payload = _overlap_payload(
        upstream_items=upstream_normalized,
        converted_items=converted_normalized,
        formula="|normalized_upstream_registers ∩ normalized_converted_registers| / |normalized_upstream_registers| * 100",
    )

    normalized_payload["register_normalization_applied"] = True
    normalized_payload["normalization_rules"] = list(REGISTER_NORMALIZATION_RULES)
    normalized_payload["raw_upstream_count"] = len(raw_upstream_set)
    normalized_payload["raw_converted_count"] = len(raw_converted_set)
    normalized_payload["raw_matched_count"] = len(raw_matched)
    normalized_payload["raw_score_before_normalization"] = _round_score(
        _safe_division_score(len(raw_matched), len(raw_upstream_set))
    )

    return normalized_payload


def _source_prefix_pattern(source_path: Path) -> str:
    stem = source_path.stem
    return f"{stem}*.h"


def _parse_quoted_local_includes(source_text: str) -> list[str]:
    return _sorted_unique(QUOTED_INCLUDE_RE.findall(source_text))


def _resolve_local_include_path(source_path: Path, include_value: str) -> Path | None:
    include_path = Path(include_value)
    search_candidates = [
        (source_path.parent / include_path).resolve(),
        (source_path.parent.parent / include_path).resolve(),
    ]
    for candidate in search_candidates:
        if candidate.exists() and candidate.is_file() and candidate.suffix == ".h":
            return candidate
    return None


def _default_scoped_header_paths(source_path: Path, source_text: str) -> list[Path]:
    resolved: list[Path] = []

    # Rule 1: same driver prefix headers (driver.h, driver-*.h).
    for item in sorted(source_path.parent.glob(_source_prefix_pattern(source_path))):
        if item.is_file() and item.suffix == ".h":
            resolved.append(item.resolve())

    # Rule 2: quoted local includes resolved in same dir / one level up.
    for include_value in _parse_quoted_local_includes(source_text):
        local = _resolve_local_include_path(source_path, include_value)
        if local is not None:
            resolved.append(local)

    unique: dict[str, Path] = {}
    for path in resolved:
        unique[str(path)] = path
    return [unique[key] for key in sorted(unique.keys())]


def _resolve_header_paths(source_path: Path, explicit_headers: Sequence[str | Path] | None) -> list[Path]:
    resolved: list[Path] = []

    if explicit_headers:
        for item in explicit_headers:
            item_path = Path(item)
            candidate = item_path if item_path.is_absolute() else (source_path.parent / item_path)
            candidate = candidate.resolve()
            if candidate.exists() and candidate.is_file() and candidate.suffix == ".h":
                resolved.append(candidate)
    else:
        resolved.extend(_default_scoped_header_paths(source_path=source_path, source_text=_read_text(source_path)))

    unique: dict[str, Path] = {}
    for path in resolved:
        unique[str(path)] = path
    return [unique[key] for key in sorted(unique.keys())]


def _extract_registers_for_source(
    source_path: Path,
    source_text: str,
    explicit_headers: Sequence[str | Path] | None,
) -> tuple[list[str], list[Path], list[str]]:
    header_paths = _resolve_header_paths(source_path, explicit_headers)
    all_symbols: list[str] = []
    all_symbols.extend(_extract_register_defines(source_text))

    header_text_hashes: list[str] = []
    for header_path in header_paths:
        header_text = _read_text(header_path)
        all_symbols.extend(_extract_register_defines(header_text))
        header_text_hashes.append(hashlib.sha256(header_text.encode("utf-8")).hexdigest())

    return _sorted_unique(all_symbols), header_paths, header_text_hashes


def _load_banned_patterns(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(entry) for entry in DEFAULT_BANNED_SYMBOL_PATTERNS]

    raw = _read_text(path)
    payload = json.loads(raw)
    entries: list[dict[str, Any]] = []

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str) and item:
                entries.append({"name": item, "pattern": re.escape(item), "regex": True})
        return sorted(entries, key=lambda item: item["name"])

    if isinstance(payload, dict):
        if isinstance(payload.get("symbols"), list):
            for item in payload["symbols"]:
                if isinstance(item, str) and item:
                    entries.append({"name": item, "pattern": re.escape(item), "regex": True})
        if isinstance(payload.get("entries"), list):
            for item in payload["entries"]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                pattern = str(item.get("pattern", "")).strip()
                is_regex = bool(item.get("regex", True))
                if name and pattern:
                    entries.append({"name": name, "pattern": pattern if is_regex else re.escape(pattern), "regex": True})

    if entries:
        return sorted(entries, key=lambda item: item["name"])
    return [dict(entry) for entry in DEFAULT_BANNED_SYMBOL_PATTERNS]


def _score_vendor_elimination(converted_text: str, banned_patterns: list[dict[str, Any]]) -> dict[str, Any]:
    per_symbol: list[dict[str, Any]] = []
    total = 0
    for entry in banned_patterns:
        name = str(entry["name"])
        pattern = str(entry["pattern"])
        count = len(list(re.finditer(pattern, converted_text, re.MULTILINE)))
        total += count
        per_symbol.append({"symbol": name, "occurrences": count})

    computed_score = 100.0 if total == 0 else 0.0
    return {
        "score": _round_score(computed_score),
        "formula": "0 occurrences found -> 100, any found -> 0",
        "total_occurrences": total,
        "per_symbol_occurrences": sorted(per_symbol, key=lambda item: item["symbol"]),
    }


def _score_lifecycle(upstream_text: str, converted_text: str, upstream_functions: list[str], converted_functions: list[str]) -> dict[str, Any]:
    per_element: list[dict[str, Any]] = []
    upstream_present = 0
    converted_present = 0
    for name, detector in LIFECYCLE_ELEMENTS:
        in_upstream = bool(detector(upstream_text, upstream_functions))
        in_converted = bool(detector(converted_text, converted_functions))
        if in_upstream:
            upstream_present += 1
            if in_converted:
                converted_present += 1
        per_element.append({"name": name, "in_upstream": in_upstream, "in_converted": in_converted})

    score_value = _round_score(_safe_division_score(converted_present, upstream_present))
    return {
        "score": score_value,
        "formula": "elements_present_in_converted / elements_present_in_upstream * 100",
        "upstream_present_count": upstream_present,
        "converted_present_count": converted_present,
        "per_element": per_element,
    }


def _deterministic_timestamp(seed_parts: list[str]) -> str:
    digest = hashlib.sha256("\n".join(seed_parts).encode("utf-8")).hexdigest()
    base_epoch = 946684800  # 2000-01-01T00:00:00Z
    window = 3155760000  # 100 years (365.25 days)
    offset = int(digest[:16], 16) % window
    ts = datetime.fromtimestamp(base_epoch + offset, tz=timezone.utc).replace(microsecond=0)
    return ts.isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_text(path).encode("utf-8")).hexdigest()


def _scoring_logic_sha256() -> str:
    return _file_sha256(Path(__file__))


def score_conversion(
    converted_source: str | Path,
    upstream_source: str | Path,
    banned_symbols_file: str | Path | None = None,
    dt_binding_file: str | Path | None = None,
    converted_headers: Sequence[str | Path] | None = None,
    upstream_headers: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Score converted source against upstream source using fixed deterministic categories."""

    converted_path = Path(converted_source).resolve()
    upstream_path = Path(upstream_source).resolve()
    banned_path = Path(banned_symbols_file).resolve() if banned_symbols_file else None
    dt_path = Path(dt_binding_file).resolve() if dt_binding_file else None

    converted_text = _read_text(converted_path)
    upstream_text = _read_text(upstream_path)
    dt_binding_text = _read_text(dt_path) if dt_path else ""

    upstream_functions = _extract_function_names(upstream_text)
    converted_functions = _extract_function_names(converted_text)

    upstream_apis = _extract_api_calls(upstream_text)
    converted_apis = _extract_api_calls(converted_text)

    upstream_registers, upstream_header_paths, upstream_header_hashes = _extract_registers_for_source(
        source_path=upstream_path,
        source_text=upstream_text,
        explicit_headers=upstream_headers,
    )
    converted_registers, converted_header_paths, converted_header_hashes = _extract_registers_for_source(
        source_path=converted_path,
        source_text=converted_text,
        explicit_headers=converted_headers,
    )

    upstream_widgets = _extract_dapm_widget_count(upstream_text)
    converted_widgets = _extract_dapm_widget_count(converted_text)

    upstream_routes = _extract_dapm_route_count(upstream_text)
    converted_routes = _extract_dapm_route_count(converted_text)

    upstream_controls = _extract_dapm_control_count(upstream_text)
    converted_controls = _extract_dapm_control_count(converted_text)

    upstream_dt_props, upstream_dt_signals = _extract_dt_properties(upstream_text)
    converted_dt_props, converted_dt_signals = _extract_dt_properties(converted_text)

    upstream_includes = _extract_includes(upstream_text)
    converted_includes = _extract_includes(converted_text)

    categories: dict[str, Any] = {}
    categories[FUNCTION_MATCH] = _overlap_payload(
        upstream_functions,
        converted_functions,
        "|upstream ∩ converted| / |upstream| * 100",
    )
    categories[API_COVERAGE] = _overlap_payload(
        upstream_apis,
        converted_apis,
        "|upstream ∩ converted| / |upstream| * 100",
    )
    categories[REGISTER_COVERAGE] = _register_overlap_payload(
        upstream_raw=upstream_registers,
        converted_raw=converted_registers,
    )

    categories[DAPM_WIDGETS] = {
        "score": _round_score(_symmetric_count_match_score(upstream_widgets, converted_widgets)),
        "formula": "min(upstream_count, converted_count) / max(upstream_count, converted_count) * 100; if both zero -> 100",
        "upstream_count": upstream_widgets,
        "converted_count": converted_widgets,
        "difference": abs(upstream_widgets - converted_widgets),
    }
    categories[DAPM_ROUTES] = {
        "score": _round_score(_symmetric_count_match_score(upstream_routes, converted_routes)),
        "formula": "min(upstream_count, converted_count) / max(upstream_count, converted_count) * 100; if both zero -> 100",
        "upstream_count": upstream_routes,
        "converted_count": converted_routes,
        "difference": abs(upstream_routes - converted_routes),
    }
    categories[DAPM_CONTROLS] = {
        "score": _round_score(_symmetric_count_match_score(upstream_controls, converted_controls)),
        "formula": "min(upstream_count, converted_count) / max(upstream_count, converted_count) * 100; if both zero -> 100",
        "upstream_count": upstream_controls,
        "converted_count": converted_controls,
        "difference": abs(upstream_controls - converted_controls),
    }
    categories[LIFECYCLE_PATTERN] = _score_lifecycle(
        upstream_text,
        converted_text,
        upstream_functions,
        converted_functions,
    )

    dt_overlap = _overlap_payload(
        upstream_dt_props,
        converted_dt_props,
        "|upstream_properties ∩ converted_properties| / |upstream_properties| * 100",
    )
    dt_score = dt_overlap["score"]
    if not upstream_dt_props:
        dt_score = 100.0

    categories[DT_PROPERTY_COVERAGE] = {
        "score": _round_score(dt_score),
        "formula": "|upstream_properties ∩ converted_properties| / |upstream_properties| * 100 (if upstream empty -> 100)",
        "upstream_properties": upstream_dt_props,
        "converted_properties": converted_dt_props,
        "matched": _sorted_unique(_to_set(upstream_dt_props).intersection(_to_set(converted_dt_props))),
        "missing": _sorted_unique(_to_set(upstream_dt_props).difference(_to_set(converted_dt_props))),
        "extra": _sorted_unique(_to_set(converted_dt_props).difference(_to_set(upstream_dt_props))),
        "upstream_extraction_signals": upstream_dt_signals,
        "converted_extraction_signals": converted_dt_signals,
    }

    banned_patterns = _load_banned_patterns(banned_path)
    categories[VENDOR_ELIMINATION] = _score_vendor_elimination(converted_text, banned_patterns)

    include_overlap = _overlap_payload(
        upstream_includes,
        converted_includes,
        "|upstream_includes ∩ converted_includes| / |upstream_includes| * 100",
    )
    categories[INCLUDE_ALIGNMENT] = {
        "score": include_overlap["score"],
        "formula": "|upstream_includes ∩ converted_includes| / |upstream_includes| * 100",
        "upstream_includes": upstream_includes,
        "converted_includes": converted_includes,
        "matched": _sorted_unique(_to_set(upstream_includes).intersection(_to_set(converted_includes))),
        "missing": _sorted_unique(_to_set(upstream_includes).difference(_to_set(converted_includes))),
        "extra": _sorted_unique(_to_set(converted_includes).difference(_to_set(upstream_includes))),
    }

    ordered_categories = {name: categories[name] for name in CATEGORY_ORDER}
    overall_score = _round_score(
        sum(float(ordered_categories[name]["score"]) for name in CATEGORY_ORDER) / float(len(CATEGORY_ORDER))
    )

    scoring_sha = _scoring_logic_sha256()
    timestamp = _deterministic_timestamp(
        [
            str(converted_path),
            str(upstream_path),
            str(banned_path) if banned_path else "",
            str(dt_path) if dt_path else "",
            ";".join(str(p) for p in converted_header_paths),
            ";".join(str(p) for p in upstream_header_paths),
            hashlib.sha256(converted_text.encode("utf-8")).hexdigest(),
            hashlib.sha256(upstream_text.encode("utf-8")).hexdigest(),
            ";".join(converted_header_hashes),
            ";".join(upstream_header_hashes),
            hashlib.sha256(dt_binding_text.encode("utf-8")).hexdigest() if dt_path else "",
            scoring_sha,
        ]
    )

    return {
        "scoring_engine": SCORING_ENGINE,
        "scoring_engine_version": SCORING_ENGINE_VERSION,
        "timestamp": timestamp,
        "inputs": {
            "converted_source": str(converted_path),
            "upstream_source": str(upstream_path),
            "converted_headers": [str(path) for path in converted_header_paths],
            "upstream_headers": [str(path) for path in upstream_header_paths],
            "banned_symbols_file": str(banned_path) if banned_path else None,
            "dt_binding_file": str(dt_path) if dt_path else None,
        },
        "categories": ordered_categories,
        "overall": {
            "score": overall_score,
            "formula": "arithmetic_mean(10 categories)",
            "category_count": len(CATEGORY_ORDER),
        },
        "metadata": {
            "deterministic": True,
            "reproducible": True,
            "scoring_logic_sha256": scoring_sha,
        },
    }


def render_score_json(report: dict[str, Any]) -> str:
    """Render deterministic JSON for a score report."""

    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic conversion scoring")
    parser.add_argument("--converted", required=True, help="Path to converted source file")
    parser.add_argument("--upstream", required=True, help="Path to upstream target source file")
    parser.add_argument("--converted-headers", nargs="*", default=None, help="Optional list of converted header files to include")
    parser.add_argument("--upstream-headers", nargs="*", default=None, help="Optional list of upstream header files to include")
    parser.add_argument("--banned-symbols", help="Optional path to banned symbols JSON")
    parser.add_argument("--dt-binding", help="Optional path to DT binding YAML")
    parser.add_argument("--output", help="Optional path to write JSON output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = score_conversion(
        converted_source=args.converted,
        upstream_source=args.upstream,
        converted_headers=args.converted_headers,
        upstream_headers=args.upstream_headers,
        banned_symbols_file=args.banned_symbols,
        dt_binding_file=args.dt_binding,
    )
    rendered = render_score_json(report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
