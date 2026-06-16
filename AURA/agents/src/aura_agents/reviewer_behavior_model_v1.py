#!/usr/bin/env python3
"""Build Reviewer_Behavior_Model_V1 from real Patchwork/lore data.

Outputs:
- reviewer_profiles.json
- reviewer_behavior_report.md
- reviewer_interaction_graph.json
- reviewer_prediction_benchmark.json
- maintainer_playbooks.md
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests

PATCHWORK_API = "https://patchwork.kernel.org/api/1.2"
TARGET_REVIEWERS = [
    "Mark Brown",
    "Pierre-Louis Bossart",
    "Vinod Koul",
    "Liam Girdwood",
]

SCOPE_QUERIES = [
    "ASoC: qcom",
    "ASoC: codecs",
    "ASoC: SoundWire",
    "soundwire: qcom",
    "ASoC: dt-bindings",
    "dt-bindings: sound: qcom",
    "runtime pm asoc",
    "wsa883x",
    "wsa884x",
    "wcd938x",
    "wcd93",
    "lpass",
]

SCOPE_RE = re.compile(
    r"(asoc|alsa|soundwire|\bsdw\b|runtime\s*pm|pm_runtime|"
    r"qcom|qualcomm|wsa\d+|wcd\d+|lpass|dt-bindings.*sound)",
    re.IGNORECASE,
)

STATE_ACCEPT = {"accepted", "mainlined", "superseded"}
STATE_REJECT = {"rejected", "changes-requested"}
STATE_PENDING = {"new", "under-review", "rfc", "deferred"}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "will", "your", "you",
    "are", "was", "were", "should", "could", "would", "into", "about", "please", "there",
    "they", "them", "their", "than", "then", "also", "just", "when", "what", "where",
    "which", "while", "been", "being", "because", "make", "does", "dont", "isnt", "cant",
    "need", "needs", "like", "have", "has", "had", "using", "used", "use", "code",
    "patch", "series", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10",
}

NAME_ALIASES = {
    "Pierre-Louis Bossart": "Pierre-Louis Bossart",
    "Pierre Louis Bossart": "Pierre-Louis Bossart",
    "PL Bossart": "Pierre-Louis Bossart",
    "broonie": "Mark Brown",
    "Krzysztof Kozlowski": "Krzysztof Kozlowski",
    "Krzysztof Kozlowski -": "Krzysztof Kozlowski",
    "Liam Girdwood": "Liam Girdwood",
    "Vinod Koul": "Vinod Koul",
}

OBJ_PATTERNS = {
    "patch_split": [
        r"\bsplit\b", r"separate (this|it)", r"one patch", r"(too|very) big", r"bisect",
        r"follow[- ]?up", r"cleanup.*separate", r"feature.*separate",
    ],
    "ownership_boundary": [
        r"belongs? in", r"move (this|it|code)", r"wrong layer", r"in the (core|codec|machine)",
        r"generic.*specific", r"specific.*generic",
    ],
    "dt_schema": [
        r"dt-binding", r"yaml", r"unevaluatedproperties", r"additionalproperties",
        r"compatible", r"dtbs_check", r"bindings?",
    ],
    "commit_message": [
        r"commit message", r"changelog", r"subject", r"describe why", r"explain why",
        r"Fixes:", r"Link:",
    ],
    "refactor": [
        r"refactor", r"cleanup", r"rename", r"rework", r"simplify",
    ],
    "feature_cleanup_mix": [
        r"separate.*cleanup", r"mixing.*cleanup", r"cleanup.*feature", r"no functional change",
    ],
    "runtime_pm": [
        r"runtime pm", r"pm_runtime", r"autosuspend", r"resume", r"suspend", r"power.*state",
    ],
    "soundwire": [
        r"soundwire", r"\bsdw\b", r"stream", r"port map", r"slave", r"master", r"enumeration",
    ],
    "dapm": [r"dapm", r"widget", r"route"],
    "controls": [r"kcontrol", r"control", r"mixer", r"enum"],
}

REJECTION_PATTERNS = [
    r"\bnack\b",
    r"do not",
    r"don't",
    r"should not",
    r"cannot",
    r"can't",
    r"wrong",
    r"not acceptable",
    r"please fix",
    r"needs? to",
    r"must",
]

ACCEPT_PATTERNS = [
    r"looks good",
    r"applied",
    r"queued",
    r"thanks",
    r"reviewed-by",
    r"acked-by",
]


@dataclasses.dataclass
class SeriesData:
    series_id: int
    name: str
    date: str
    version: int
    web_url: str
    submitter: str
    patch_count: int
    patch_states: Counter
    acceptance_ratio: float
    outcome: str
    scope_tags: Set[str]
    feature_tags: Set[str]
    diff_lines_total: int
    comments: List[Dict[str, Any]]


class PatchworkClient:
    def __init__(self, cache_dir: Path, workers: int = 12) -> None:
        self.session = requests.Session()
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers

    def _cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", key)
        return self.cache_dir / f"{safe}.json"

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None, cache_key: Optional[str] = None) -> Any:
        if cache_key:
            cp = self._cache_path(cache_key)
            if cp.exists():
                with cp.open() as f:
                    return json.load(f)
        else:
            cp = None

        for attempt in range(4):
            try:
                r = self.session.get(url, params=params, timeout=40)
                if r.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                if cp:
                    with cp.open("w") as f:
                        json.dump(data, f)
                return data
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError("unreachable")

    def query_series(self, q: str, pages: int, per_page: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for page in range(1, pages + 1):
            params = {
                "project": 121,
                "order": "-date",
                "page": page,
                "per_page": per_page,
                "q": q,
            }
            key = f"series_query_{q}_{page}_{per_page}"
            try:
                arr = self.get_json(f"{PATCHWORK_API}/series/", params=params, cache_key=key)
            except requests.exceptions.HTTPError:
                # Patchwork may return 404 for out-of-range pages instead of [].
                break
            if not isinstance(arr, list) or not arr:
                break
            out.extend([x for x in arr if isinstance(x, dict)])
        return out

    def fetch_series_detail(self, sid: int) -> Dict[str, Any]:
        return self.get_json(f"{PATCHWORK_API}/series/{sid}/", cache_key=f"series_{sid}")

    def fetch_patch(self, patch_url: str, patch_id: int) -> Dict[str, Any]:
        return self.get_json(patch_url, cache_key=f"patch_{patch_id}")

    def fetch_comments(self, comments_url: str, patch_id: int) -> List[Dict[str, Any]]:
        data = self.get_json(comments_url, cache_key=f"comments_{patch_id}")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []


def normalize_name(name: str) -> str:
    name = (name or "").strip()
    if name in NAME_ALIASES:
        return NAME_ALIASES[name]
    for k, v in NAME_ALIASES.items():
        if k.lower() in name.lower():
            return v
    return name


def parse_date(s: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return dt.datetime(1970, 1, 1)


def classify_scope(subject: str) -> Set[str]:
    s = subject.lower()
    tags: Set[str] = set()
    if "asoc" in s:
        tags.add("ASoC")
    if "alsa" in s:
        tags.add("ALSA")
    if "soundwire" in s or "sdw" in s:
        tags.add("SoundWire")
    if "runtime pm" in s or "pm_runtime" in s or "suspend" in s or "resume" in s:
        tags.add("PM")
    if "qcom" in s or "qualcomm" in s or re.search(r"\bwsa\d+|\bwcd\d+|\blpass\b", s):
        tags.add("QualcommAudio")
    if "dt-bindings" in s or "yaml" in s or "device tree" in s or "dt:" in s:
        tags.add("DT")
    return tags


def classify_feature_tags(subject: str) -> Set[str]:
    s = subject.lower()
    tags: Set[str] = set()
    if "dt-bindings" in s or "yaml" in s:
        tags.add("dt")
    if "soundwire" in s or "sdw" in s:
        tags.add("soundwire")
    if "runtime pm" in s or "pm_runtime" in s or "suspend" in s or "resume" in s:
        tags.add("runtime_pm")
    if "dapm" in s:
        tags.add("dapm")
    if "control" in s or "kcontrol" in s or "mixer" in s:
        tags.add("controls")
    if "refactor" in s or "cleanup" in s or "simplify" in s or "rename" in s:
        tags.add("cleanup_refactor")
    if "qcom" in s or re.search(r"\bwsa\d+|\bwcd\d+|\blpass\b", s):
        tags.add("qcom_audio")
    if "machine" in s or "soundcard" in s:
        tags.add("machine_driver")
    if not tags:
        tags.add("general")
    return tags


def comment_categories(text: str) -> Set[str]:
    t = (text or "").lower()
    cats: Set[str] = set()
    for cat, pats in OBJ_PATTERNS.items():
        for p in pats:
            if re.search(p, t, re.IGNORECASE):
                cats.add(cat)
                break
    return cats


def is_objection(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t, re.IGNORECASE) for p in REJECTION_PATTERNS)


def is_acceptance(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t, re.IGNORECASE) for p in ACCEPT_PATTERNS)


def normalize_subject_root(subject: str) -> str:
    s = subject
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"\b\d+/\d+\b", "", s)
    s = re.sub(r"\bpatch\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def patch_size_bin(diff_lines: int) -> str:
    if diff_lines < 60:
        return "tiny"
    if diff_lines < 220:
        return "small"
    if diff_lines < 700:
        return "medium"
    return "large"


def series_length_bin(n: int) -> str:
    if n <= 1:
        return "single"
    if n <= 3:
        return "short"
    if n <= 8:
        return "medium"
    return "long"


def extract_ngrams(texts: List[str], n: int = 3, topk: int = 12) -> List[Tuple[str, int]]:
    c = Counter()
    for t in texts:
        words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", t.lower()) if w not in STOPWORDS and len(w) > 2]
        if len(words) < n:
            continue
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i:i+n])
            c[gram] += 1
    return c.most_common(topk)


def avg(nums: Iterable[float], default: float = 0.0) -> float:
    arr = list(nums)
    return sum(arr) / len(arr) if arr else default


def f1(prec: float, rec: float) -> float:
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def compute_prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": f1(p, r)}


def build_dataset(client: PatchworkClient, min_year: int, pages_per_query: int, per_page: int, max_series: int) -> Tuple[List[SeriesData], Dict[str, Any]]:
    series_map: Dict[int, Dict[str, Any]] = {}
    for q in SCOPE_QUERIES:
        rows = client.query_series(q=q, pages=pages_per_query, per_page=per_page)
        for s in rows:
            sid = s.get("id")
            if sid is None:
                continue
            name = s.get("name", "")
            date = s.get("date", "")
            if parse_date(date).year < min_year:
                continue
            if not SCOPE_RE.search(name or ""):
                continue
            series_map[int(sid)] = s

    # prioritize Qualcomm audio + DT/SDW/PM, then by recency
    all_refs = list(series_map.values())
    all_refs.sort(key=lambda x: x.get("date", ""), reverse=True)

    prioritized: List[Dict[str, Any]] = []
    for s in all_refs:
        name = (s.get("name") or "").lower()
        score = 0
        if re.search(r"qcom|qualcomm|wsa\d+|wcd\d+|lpass", name):
            score += 3
        if "soundwire" in name or "sdw" in name:
            score += 2
        if "dt-bindings" in name or "yaml" in name:
            score += 1
        if "runtime pm" in name or "pm_runtime" in name:
            score += 1
        s["_priority"] = score
        prioritized.append(s)

    prioritized.sort(key=lambda x: (x.get("_priority", 0), x.get("date", "")), reverse=True)
    chosen = prioritized[:max_series]

    out: List[SeriesData] = []
    stats = {
        "candidate_series": len(series_map),
        "selected_series": len(chosen),
    }

    def fetch_one(series_ref: Dict[str, Any]) -> Optional[SeriesData]:
        sid = int(series_ref["id"])
        try:
            detail = client.fetch_series_detail(sid)
        except Exception:
            return None
        if not isinstance(detail, dict):
            return None

        patches = detail.get("patches") or []
        if not patches:
            return None
        name = detail.get("name", "")
        if not SCOPE_RE.search(name):
            return None

        submitter = normalize_name(((detail.get("submitter") or {}).get("name") or ""))
        states = Counter()
        comments: List[Dict[str, Any]] = []
        diff_lines_total = 0

        for p in patches:
            pid = p.get("id")
            purl = p.get("url")
            if pid is None or not purl:
                continue
            try:
                pj = client.fetch_patch(purl, int(pid))
            except Exception:
                continue
            if not isinstance(pj, dict):
                continue
            state = (pj.get("state") or "unknown").lower()
            states[state] += 1
            diff_text = pj.get("diff") or ""
            diff_lines_total += diff_text.count("\n")

            c_url = pj.get("comments")
            if isinstance(c_url, str):
                try:
                    crows = client.fetch_comments(c_url, int(pid))
                except Exception:
                    crows = []
                for c in crows:
                    reviewer = normalize_name(((c.get("submitter") or {}).get("name") or ""))
                    content = c.get("content") or ""
                    comments.append(
                        {
                            "series_id": sid,
                            "patch_id": pid,
                            "patch_name": pj.get("name", ""),
                            "patch_state": state,
                            "series_name": name,
                            "series_submitter": submitter,
                            "patch_submitter": normalize_name(((pj.get("submitter") or {}).get("name") or "")),
                            "reviewer": reviewer,
                            "reviewer_email": ((c.get("submitter") or {}).get("email") or ""),
                            "date": c.get("date", ""),
                            "subject": c.get("subject", ""),
                            "content": content,
                            "list_archive_url": c.get("list_archive_url", ""),
                            "addressed": bool(c.get("addressed", False)),
                            "categories": sorted(comment_categories(content)),
                            "is_objection": is_objection(content),
                            "is_acceptance": is_acceptance(content),
                        }
                    )

        total = sum(states.values())
        if total == 0:
            return None
        accept_ratio = sum(states[s] for s in STATE_ACCEPT if s in states) / total
        reject_ratio = sum(states[s] for s in STATE_REJECT if s in states) / total
        pending_ratio = sum(states[s] for s in STATE_PENDING if s in states) / total
        if accept_ratio >= 0.8:
            outcome = "accepted"
        elif reject_ratio >= 0.5 and accept_ratio == 0:
            outcome = "rejected"
        elif pending_ratio >= 0.6 and accept_ratio == 0:
            outcome = "pending"
        else:
            outcome = "mixed"

        scope_tags = classify_scope(name)
        feature_tags = classify_feature_tags(name)

        return SeriesData(
            series_id=sid,
            name=name,
            date=detail.get("date", series_ref.get("date", "")),
            version=int(detail.get("version") or 1),
            web_url=detail.get("web_url", series_ref.get("web_url", "")),
            submitter=submitter,
            patch_count=len(patches),
            patch_states=states,
            acceptance_ratio=accept_ratio,
            outcome=outcome,
            scope_tags=scope_tags,
            feature_tags=feature_tags,
            diff_lines_total=diff_lines_total,
            comments=comments,
        )

    with ThreadPoolExecutor(max_workers=client.workers) as ex:
        futs = [ex.submit(fetch_one, s) for s in chosen]
        for f in as_completed(futs):
            row = f.result()
            if row is not None:
                out.append(row)

    out.sort(key=lambda x: x.date)
    stats["fetched_series"] = len(out)
    return out, stats


def series_feature_tokens(s: SeriesData) -> Set[str]:
    tokens: Set[str] = set()
    for t in sorted(s.scope_tags):
        tokens.add(f"scope:{t}")
    for t in sorted(s.feature_tags):
        tokens.add(f"feature:{t}")
    tokens.add(f"series_len:{series_length_bin(s.patch_count)}")
    tokens.add(f"patch_size:{patch_size_bin(int(s.diff_lines_total / max(s.patch_count, 1)))}")
    tokens.add(f"version_bin:{'v1' if s.version <= 1 else 'v2plus' if s.version <= 2 else 'v3plus'}")
    return tokens


def split_train_holdout(series_rows: List[SeriesData], holdout_ratio: float = 0.2) -> Tuple[List[SeriesData], List[SeriesData]]:
    rows = sorted(series_rows, key=lambda x: x.date)
    n = len(rows)
    cut = max(1, int(n * (1 - holdout_ratio)))
    return rows[:cut], rows[cut:]


def collect_series_targets(series_rows: List[SeriesData]) -> Dict[int, Dict[str, Any]]:
    # Determine family rounds by normalized root
    families: Dict[str, List[SeriesData]] = defaultdict(list)
    for s in series_rows:
        families[normalize_subject_root(s.name)].append(s)
    family_rounds = {k: max(x.version for x in v) for k, v in families.items()}

    out = {}
    for s in series_rows:
        comments = [
            c
            for c in s.comments
            if c.get("reviewer")
            and c.get("reviewer") != s.submitter
            and c.get("reviewer") != c.get("patch_submitter")
        ]
        commenters = sorted({c["reviewer"] for c in comments if c.get("reviewer")})
        objection_categories = sorted({cat for c in comments for cat in c.get("categories", [])})
        split_req = any("patch_split" in c.get("categories", []) or "feature_cleanup_mix" in c.get("categories", []) for c in comments)
        objection_count = sum(1 for c in comments if c.get("is_objection"))
        first_patch_time = parse_date(s.date)
        first_comment_time = min((parse_date(c.get("date", "")) for c in comments), default=None)
        latency_hours = None
        if first_comment_time:
            latency_hours = max((first_comment_time - first_patch_time).total_seconds() / 3600.0, 0.0)
        out[s.series_id] = {
            "series_id": s.series_id,
            "series_name": s.name,
            "series_date": s.date,
            "series_url": s.web_url,
            "version": s.version,
            "family_rounds": family_rounds.get(normalize_subject_root(s.name), s.version),
            "scope_tags": sorted(s.scope_tags),
            "feature_tags": sorted(s.feature_tags),
            "patch_count": s.patch_count,
            "patch_size_bin": patch_size_bin(int(s.diff_lines_total / max(s.patch_count, 1))),
            "series_length_bin": series_length_bin(s.patch_count),
            "outcome": s.outcome,
            "acceptance_ratio": s.acceptance_ratio,
            "commenters": commenters,
            "objection_categories": objection_categories,
            "split_request": split_req,
            "objection_count": objection_count,
            "review_latency_hours": latency_hours,
            "comments_total": len(comments),
            "lore_links": sorted({c.get("list_archive_url", "") for c in comments if c.get("list_archive_url")}),
        }
    return out


def train_reviewer_models(train_rows: List[SeriesData], targets: Dict[int, Dict[str, Any]], reviewers: List[str]) -> Dict[str, Any]:
    train_by_series = {s.series_id: s for s in train_rows}

    feat_counts = Counter()
    reviewer_feat = {r: Counter() for r in reviewers}
    reviewer_series_count = Counter()

    for sid, s in train_by_series.items():
        t = targets[sid]
        feats = series_feature_tokens(s)
        for f in feats:
            feat_counts[f] += 1
        commenters = set(t["commenters"])
        for r in reviewers:
            if r in commenters:
                reviewer_series_count[r] += 1
                for f in feats:
                    reviewer_feat[r][f] += 1

    n = len(train_by_series)
    priors = {r: (reviewer_series_count[r] + 1) / (n + 2) for r in reviewers}

    thresholds = {}
    for r in reviewers:
        best_t, best_f1 = 0.3, -1.0
        for th in [x / 20 for x in range(2, 18)]:
            tp = fp = fn = 0
            for sid, s in train_by_series.items():
                feats = series_feature_tokens(s)
                vals = [
                    (reviewer_feat[r][f] + 1) / (feat_counts[f] + 2)
                    for f in feats
                    if feat_counts[f] > 0
                ]
                score = 0.5 * priors[r] + 0.5 * (avg(vals, priors[r]))
                pred = score >= th
                actual = r in set(targets[sid]["commenters"])
                if pred and actual:
                    tp += 1
                elif pred and not actual:
                    fp += 1
                elif (not pred) and actual:
                    fn += 1
            m = compute_prf(tp, fp, fn)
            if m["f1"] > best_f1:
                best_f1 = m["f1"]
                best_t = th
        thresholds[r] = best_t

    # Objection category model
    categories = sorted({k for k in OBJ_PATTERNS.keys()})
    cat_feat = {c: Counter() for c in categories}
    cat_counts = Counter()
    for sid, s in train_by_series.items():
        feats = series_feature_tokens(s)
        cats = set(targets[sid]["objection_categories"])
        for c in categories:
            if c in cats:
                cat_counts[c] += 1
                for f in feats:
                    cat_feat[c][f] += 1

    cat_priors = {c: (cat_counts[c] + 1) / (n + 2) for c in categories}

    # Acceptance and split probabilities by feature
    accept_feat = defaultdict(lambda: [0, 0])
    split_feat = defaultdict(lambda: [0, 0])
    rounds_feat = defaultdict(list)
    global_accept = []
    global_split = []
    global_rounds = []

    for sid, s in train_by_series.items():
        t = targets[sid]
        if t["outcome"] in {"accepted", "rejected"}:
            y = 1 if t["outcome"] == "accepted" else 0
            global_accept.append(y)
            for f in series_feature_tokens(s):
                accept_feat[f][0] += y
                accept_feat[f][1] += 1
        ysplit = 1 if t["split_request"] else 0
        global_split.append(ysplit)
        for f in series_feature_tokens(s):
            split_feat[f][0] += ysplit
            split_feat[f][1] += 1
        global_rounds.append(t["family_rounds"])
        rounds_feat[tuple(sorted(series_feature_tokens(s)))].append(t["family_rounds"])

    return {
        "reviewers": reviewers,
        "feat_counts": dict(feat_counts),
        "reviewer_feat": {k: dict(v) for k, v in reviewer_feat.items()},
        "reviewer_priors": priors,
        "reviewer_thresholds": thresholds,
        "categories": categories,
        "cat_feat": {k: dict(v) for k, v in cat_feat.items()},
        "cat_priors": cat_priors,
        "accept_feat": {k: v for k, v in accept_feat.items()},
        "split_feat": {k: v for k, v in split_feat.items()},
        "global_accept": avg(global_accept, 0.5),
        "global_split": avg(global_split, 0.2),
        "global_rounds": avg(global_rounds, 1.5),
    }


def predict_one(model: Dict[str, Any], s: SeriesData) -> Dict[str, Any]:
    feats = series_feature_tokens(s)
    feat_counts = model["feat_counts"]

    pred_reviewers = []
    reviewer_scores = {}
    for r in model["reviewers"]:
        rf = model["reviewer_feat"].get(r, {})
        vals = [
            (rf.get(f, 0) + 1) / (feat_counts.get(f, 0) + 2)
            for f in feats
            if feat_counts.get(f, 0) > 0
        ]
        prior = model["reviewer_priors"].get(r, 0.05)
        score = 0.5 * prior + 0.5 * avg(vals, prior)
        reviewer_scores[r] = score
        if score >= model["reviewer_thresholds"].get(r, 0.5):
            pred_reviewers.append(r)

    pred_cats = []
    cat_scores = {}
    for c in model["categories"]:
        cf = model["cat_feat"].get(c, {})
        vals = [
            (cf.get(f, 0) + 1) / (feat_counts.get(f, 0) + 2)
            for f in feats
            if feat_counts.get(f, 0) > 0
        ]
        prior = model["cat_priors"].get(c, 0.05)
        score = 0.5 * prior + 0.5 * avg(vals, prior)
        cat_scores[c] = score
        if score >= 0.33:
            pred_cats.append(c)

    acc_rates = []
    for f in feats:
        if f in model["accept_feat"] and model["accept_feat"][f][1] > 0:
            num, den = model["accept_feat"][f]
            acc_rates.append(num / den)
    acc_prob = avg(acc_rates, model["global_accept"])

    split_rates = []
    for f in feats:
        if f in model["split_feat"] and model["split_feat"][f][1] > 0:
            num, den = model["split_feat"][f]
            split_rates.append(num / den)
    split_prob = avg(split_rates, model["global_split"])

    pred_rounds = round(max(1.0, model["global_rounds"]))
    return {
        "pred_reviewers": sorted(pred_reviewers),
        "reviewer_scores": reviewer_scores,
        "pred_objection_categories": sorted(pred_cats),
        "category_scores": cat_scores,
        "pred_acceptance_probability": float(max(0.01, min(0.99, acc_prob))),
        "pred_split_request_probability": float(max(0.01, min(0.99, split_prob))),
        "pred_review_rounds": int(pred_rounds),
    }


def baseline_predict(s: SeriesData, global_stats: Dict[str, Any], reviewers: List[str], categories: List[str]) -> Dict[str, Any]:
    return {
        "pred_reviewers": sorted([r for r in reviewers if global_stats["reviewer_priors"].get(r, 0) >= 0.25]),
        "pred_objection_categories": sorted([c for c in categories if global_stats["cat_priors"].get(c, 0) >= 0.25]),
        "pred_acceptance_probability": global_stats["global_accept"],
        "pred_split_request_probability": global_stats["global_split"],
        "pred_review_rounds": int(round(max(1.0, global_stats["global_rounds"]))),
    }


def evaluate_predictions(
    holdout_rows: List[SeriesData],
    targets: Dict[int, Dict[str, Any]],
    model: Dict[str, Any],
    reviewers: List[str],
) -> Dict[str, Any]:
    results = []

    # global stats for baseline comparator (non-reviewer-specific)
    global_stats = {
        "reviewer_priors": model["reviewer_priors"],
        "cat_priors": model["cat_priors"],
        "global_accept": model["global_accept"],
        "global_split": model["global_split"],
        "global_rounds": model["global_rounds"],
    }

    reviewer_tp = reviewer_fp = reviewer_fn = 0
    cat_tp = cat_fp = cat_fn = 0
    split_tp = split_fp = split_fn = split_tn = 0
    accept_mae = []
    accept_brier = []
    rounds_abs = []

    baseline_reviewer_tp = baseline_reviewer_fp = baseline_reviewer_fn = 0

    for s in holdout_rows:
        t = targets[s.series_id]
        pred = predict_one(model, s)
        base = baseline_predict(s, global_stats, reviewers, model["categories"])

        actual_reviewers = set([r for r in t["commenters"] if r in reviewers])
        pred_reviewers = set(pred["pred_reviewers"])
        baseline_reviewers = set(base["pred_reviewers"])

        reviewer_tp += len(pred_reviewers & actual_reviewers)
        reviewer_fp += len(pred_reviewers - actual_reviewers)
        reviewer_fn += len(actual_reviewers - pred_reviewers)

        baseline_reviewer_tp += len(baseline_reviewers & actual_reviewers)
        baseline_reviewer_fp += len(baseline_reviewers - actual_reviewers)
        baseline_reviewer_fn += len(actual_reviewers - baseline_reviewers)

        actual_cats = set(t["objection_categories"])
        pred_cats = set(pred["pred_objection_categories"])
        cat_tp += len(pred_cats & actual_cats)
        cat_fp += len(pred_cats - actual_cats)
        cat_fn += len(actual_cats - pred_cats)

        actual_split = bool(t["split_request"])
        pred_split = pred["pred_split_request_probability"] >= 0.5
        if pred_split and actual_split:
            split_tp += 1
        elif pred_split and not actual_split:
            split_fp += 1
        elif (not pred_split) and actual_split:
            split_fn += 1
        else:
            split_tn += 1

        if t["outcome"] in {"accepted", "rejected"}:
            y = 1.0 if t["outcome"] == "accepted" else 0.0
            p = pred["pred_acceptance_probability"]
            accept_mae.append(abs(p - y))
            accept_brier.append((p - y) ** 2)

        rounds_abs.append(abs(pred["pred_review_rounds"] - t["family_rounds"]))

        results.append(
            {
                "series_id": s.series_id,
                "series_name": s.name,
                "series_url": s.web_url,
                "series_date": s.date,
                "actual_reviewers": sorted(actual_reviewers),
                "pred_reviewers": sorted(pred_reviewers),
                "actual_objection_categories": sorted(actual_cats),
                "pred_objection_categories": sorted(pred_cats),
                "actual_outcome": t["outcome"],
                "pred_acceptance_probability": pred["pred_acceptance_probability"],
                "actual_split_request": actual_split,
                "pred_split_request_probability": pred["pred_split_request_probability"],
                "actual_review_rounds": t["family_rounds"],
                "pred_review_rounds": pred["pred_review_rounds"],
                "lore_links": t["lore_links"][:8],
            }
        )

    reviewer_metrics = compute_prf(reviewer_tp, reviewer_fp, reviewer_fn)
    cat_metrics = compute_prf(cat_tp, cat_fp, cat_fn)
    split_metrics = compute_prf(split_tp, split_fp, split_fn)
    split_metrics["accuracy"] = (split_tp + split_tn) / max(1, split_tp + split_tn + split_fp + split_fn)

    baseline_reviewer_metrics = compute_prf(baseline_reviewer_tp, baseline_reviewer_fp, baseline_reviewer_fn)

    return {
        "heldout_series": len(holdout_rows),
        "reviewer_comment_prediction": reviewer_metrics,
        "objection_category_prediction": cat_metrics,
        "split_request_prediction": split_metrics,
        "acceptance_probability": {
            "mae": avg(accept_mae, 0.0),
            "brier": avg(accept_brier, 0.0),
            "samples": len(accept_mae),
        },
        "review_round_prediction": {
            "mae": avg(rounds_abs, 0.0),
            "samples": len(rounds_abs),
        },
        "baseline_vs_reviewer_model": {
            "baseline_reviewer_prediction": baseline_reviewer_metrics,
            "reviewer_model_reviewer_prediction": reviewer_metrics,
            "f1_delta": reviewer_metrics["f1"] - baseline_reviewer_metrics["f1"],
            "precision_delta": reviewer_metrics["precision"] - baseline_reviewer_metrics["precision"],
            "recall_delta": reviewer_metrics["recall"] - baseline_reviewer_metrics["recall"],
        },
        "heldout_predictions": results,
    }


def build_profiles(series_rows: List[SeriesData], targets: Dict[int, Dict[str, Any]], reviewers: List[str]) -> Dict[str, Any]:
    by_reviewer_comments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_reviewer_series: Dict[str, Set[int]] = defaultdict(set)

    series_map = {s.series_id: s for s in series_rows}

    for s in series_rows:
        for c in s.comments:
            rv = c.get("reviewer")
            if not rv:
                continue
            if rv == s.submitter or rv == c.get("patch_submitter"):
                continue
            by_reviewer_comments[rv].append(c)
            by_reviewer_series[rv].add(s.series_id)

    profiles = {}
    for r in reviewers:
        comments = by_reviewer_comments.get(r, [])
        sids = sorted(by_reviewer_series.get(r, set()))
        reviewed_series = [series_map[x] for x in sids if x in series_map]

        objection_freq = avg([1.0 if c.get("is_objection") else 0.0 for c in comments], 0.0)
        cat_counts = Counter(cat for c in comments for cat in c.get("categories", []))

        accepted_touch = 0
        rejected_touch = 0
        latencies = []
        rounds = []
        topology_patch_counts = []
        topology_patch_bins = Counter()
        topology_series_bins = Counter()
        for sid in sids:
            t = targets.get(sid)
            if not t:
                continue
            if t["outcome"] == "accepted":
                accepted_touch += 1
            elif t["outcome"] == "rejected":
                rejected_touch += 1
            if t["review_latency_hours"] is not None:
                latencies.append(t["review_latency_hours"])
            rounds.append(t["family_rounds"])
            topology_patch_counts.append(t["patch_count"])
            topology_patch_bins[t["patch_size_bin"]] += 1
            topology_series_bins[t["series_length_bin"]] += 1

        acceptance_rate = accepted_touch / max(1, accepted_touch + rejected_touch)

        phrase_ngrams = extract_ngrams([c.get("content", "") for c in comments], n=3, topk=12)

        # preference proxies
        dt_strictness = avg([1.0 if "dt_schema" in c.get("categories", []) else 0.0 for c in comments], 0.0)
        pm_focus = avg([1.0 if "runtime_pm" in c.get("categories", []) else 0.0 for c in comments], 0.0)
        sdw_focus = avg([1.0 if "soundwire" in c.get("categories", []) else 0.0 for c in comments], 0.0)
        split_focus = avg([1.0 if "patch_split" in c.get("categories", []) else 0.0 for c in comments], 0.0)
        boundary_focus = avg([1.0 if "ownership_boundary" in c.get("categories", []) else 0.0 for c in comments], 0.0)
        commit_msg_focus = avg([1.0 if "commit_message" in c.get("categories", []) else 0.0 for c in comments], 0.0)

        profiles[r] = {
            "review_interactions": len(comments),
            "reviewed_series_count": len(sids),
            "objection_frequency": objection_freq,
            "objection_categories": cat_counts,
            "acceptance_rate_on_reviewed_series": acceptance_rate,
            "review_latency_hours": {
                "median": statistics.median(latencies) if latencies else None,
                "mean": avg(latencies, 0.0) if latencies else None,
                "samples": len(latencies),
            },
            "review_round_distribution": Counter(rounds),
            "recurring_phrases": phrase_ngrams,
            "preferred_patch_topology": {
                "median_patch_count": statistics.median(topology_patch_counts) if topology_patch_counts else None,
                "patch_size_bins": topology_patch_bins,
                "series_length_bins": topology_series_bins,
                "split_request_rate": split_focus,
            },
            "behavior_axes": {
                "patch_split_preference": split_focus,
                "ownership_boundary_sensitivity": boundary_focus,
                "dt_schema_strictness": dt_strictness,
                "commit_message_expectation": commit_msg_focus,
                "refactor_tolerance_inverse": avg([1.0 if "refactor" in c.get("categories", []) and c.get("is_objection") else 0.0 for c in comments], 0.0),
                "feature_cleanup_mixing_tolerance_inverse": avg([1.0 if "feature_cleanup_mix" in c.get("categories", []) else 0.0 for c in comments], 0.0),
                "pm_sequencing_preference": pm_focus,
                "soundwire_lifecycle_preference": sdw_focus,
            },
            "common_rejection_patterns": [k for k, _ in cat_counts.most_common(5)],
            "acceptance_indicators_frequency": avg([1.0 if c.get("is_acceptance") else 0.0 for c in comments], 0.0),
            "evidence_series": [
                {
                    "series_id": sid,
                    "series_name": targets[sid]["series_name"],
                    "series_url": targets[sid]["series_url"],
                    "lore_links": targets[sid]["lore_links"][:3],
                }
                for sid in sids[:25]
                if sid in targets
            ],
        }

    return profiles


def build_interaction_graph(series_rows: List[SeriesData], targets: Dict[int, Dict[str, Any]], reviewers: List[str]) -> Dict[str, Any]:
    nodes = []
    edges = []

    for r in reviewers:
        nodes.append({"id": r, "type": "reviewer"})

    subsystem_edges = Counter()
    feature_edges = Counter()
    patchsize_edges = Counter()
    serieslen_edges = Counter()

    for s in series_rows:
        t = targets[s.series_id]
        rv_set = set(t["commenters"])
        for r in reviewers:
            if r not in rv_set:
                continue
            for sub in t["scope_tags"]:
                subsystem_edges[(r, sub)] += 1
            for feat in t["feature_tags"]:
                feature_edges[(r, feat)] += 1
            patchsize_edges[(r, t["patch_size_bin"])] += 1
            serieslen_edges[(r, t["series_length_bin"])] += 1

    for (r, sub), w in subsystem_edges.items():
        nodes.append({"id": f"subsystem:{sub}", "type": "subsystem"})
        edges.append({"source": r, "target": f"subsystem:{sub}", "relation": "reviewer_subsystem", "weight": w})
    for (r, feat), w in feature_edges.items():
        nodes.append({"id": f"feature:{feat}", "type": "feature"})
        edges.append({"source": r, "target": f"feature:{feat}", "relation": "reviewer_feature", "weight": w})
    for (r, ps), w in patchsize_edges.items():
        nodes.append({"id": f"patch_size:{ps}", "type": "patch_size"})
        edges.append({"source": r, "target": f"patch_size:{ps}", "relation": "reviewer_patch_size", "weight": w})
    for (r, sl), w in serieslen_edges.items():
        nodes.append({"id": f"series_len:{sl}", "type": "series_length"})
        edges.append({"source": r, "target": f"series_len:{sl}", "relation": "reviewer_series_length", "weight": w})

    # dedupe nodes
    uniq_nodes = {n["id"]: n for n in nodes}
    return {"nodes": list(uniq_nodes.values()), "edges": edges}


def write_report(
    out_dir: Path,
    dataset_stats: Dict[str, Any],
    profiles: Dict[str, Any],
    benchmark: Dict[str, Any],
    reviewers_modeled: List[str],
    holdout_rows: List[SeriesData],
    targets: Dict[int, Dict[str, Any]],
) -> None:
    # Q answers from held-out only
    rp = benchmark["reviewer_comment_prediction"]
    base = benchmark["baseline_vs_reviewer_model"]

    # Predictability score per reviewer on heldout from top-k correctness proxy
    # Build quick per-reviewer precision/recall from heldout predictions list
    by_r = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    for row in benchmark["heldout_predictions"]:
        act = set(row["actual_reviewers"])
        pred = set(row["pred_reviewers"])
        for r in reviewers_modeled:
            if r in pred and r in act:
                by_r[r]["tp"] += 1
            elif r in pred and r not in act:
                by_r[r]["fp"] += 1
            elif r not in pred and r in act:
                by_r[r]["fn"] += 1

    pred_scores = {}
    for r in reviewers_modeled:
        m = by_r[r]
        pr = compute_prf(m["tp"], m["fp"], m["fn"])
        pred_scores[r] = pr

    most_predictable = max(pred_scores.items(), key=lambda kv: kv[1]["f1"])[0] if pred_scores else "INSUFFICIENT_EVIDENCE"

    holdout_ids = {s.series_id for s in holdout_rows}
    heldout_rows_pred = [x for x in benchmark["heldout_predictions"] if x["series_id"] in holdout_ids]

    # Q2 strongest subsystem-specific preference (held-out only):
    # concentration = max subsystem share among series where reviewer commented.
    reviewer_scope = defaultdict(Counter)
    for row in heldout_rows_pred:
        sid = row["series_id"]
        scope_tags = targets.get(sid, {}).get("scope_tags", [])
        for r in row["actual_reviewers"]:
            for st in scope_tags:
                reviewer_scope[r][st] += 1
    scope_concentration = {}
    for r, ctr in reviewer_scope.items():
        tot = sum(ctr.values())
        scope_concentration[r] = (max(ctr.values()) / tot) if tot else 0.0
    strongest_pref = (
        max(scope_concentration.items(), key=lambda kv: kv[1])[0]
        if scope_concentration
        else "INSUFFICIENT_EVIDENCE"
    )

    # Q3 churn contribution (held-out only):
    # score = sum(review_rounds * objection_count) over series where reviewer commented.
    churn = Counter()
    for row in heldout_rows_pred:
        sid = row["series_id"]
        rr = targets.get(sid, {}).get("family_rounds", row.get("actual_review_rounds", 1))
        obj = max(1, targets.get(sid, {}).get("objection_count", 0))
        for r in row["actual_reviewers"]:
            churn[r] += rr * obj
    top_churn = max(churn.items(), key=lambda kv: kv[1])[0] if churn else "INSUFFICIENT_EVIDENCE"

    # Q5 missing reviewer-specific rules from held-out error patterns only.
    existing_global_rule_topics = {"dt_schema", "runtime_pm", "soundwire", "dapm", "controls"}
    heldout_cat_misses = Counter()
    for row in heldout_rows_pred:
        act = set(row["actual_objection_categories"])
        pred = set(row["pred_objection_categories"])
        for c in (act - pred):
            heldout_cat_misses[c] += 1
    missing_rules = []
    for c, cnt in heldout_cat_misses.most_common():
        if c not in existing_global_rule_topics and cnt >= 3:
            missing_rules.append({"rule_gap": c, "evidence_count": cnt})

    holdout_lore = [
        {
            "series_id": s.series_id,
            "series_name": s.name,
            "series_url": s.web_url,
            "lore_links": benchmark["heldout_predictions"][i].get("lore_links", []),
        }
        for i, s in enumerate(holdout_rows[:40])
    ]

    md = []
    md.append("# Reviewer Behavior Report V1")
    md.append("")
    md.append("## Dataset")
    md.append(f"- Candidate series discovered: **{dataset_stats['candidate_series']}**")
    md.append(f"- Series selected for modeling: **{dataset_stats['selected_series']}**")
    md.append(f"- Series fetched successfully: **{dataset_stats['fetched_series']}**")
    md.append(f"- Held-out series: **{benchmark['heldout_series']}**")
    md.append(f"- Reviewers modeled: **{len(reviewers_modeled)}**")
    md.append("")

    md.append("## Held-Out Prediction Metrics")
    md.append(f"- Reviewer likelihood prediction: precision={rp['precision']:.3f}, recall={rp['recall']:.3f}, f1={rp['f1']:.3f}")
    oc = benchmark["objection_category_prediction"]
    md.append(f"- Objection category prediction: precision={oc['precision']:.3f}, recall={oc['recall']:.3f}, f1={oc['f1']:.3f}")
    sp = benchmark["split_request_prediction"]
    md.append(f"- Patch-split request prediction: precision={sp['precision']:.3f}, recall={sp['recall']:.3f}, f1={sp['f1']:.3f}, acc={sp['accuracy']:.3f}")
    ap = benchmark["acceptance_probability"]
    md.append(f"- Acceptance probability: MAE={ap['mae']:.3f}, Brier={ap['brier']:.3f}, n={ap['samples']}")
    rr = benchmark["review_round_prediction"]
    md.append(f"- Review rounds prediction: MAE={rr['mae']:.3f}, n={rr['samples']}")
    md.append("")

    md.append("## Final Questions")
    md.append(f"- Q1 Most predictable reviewer (held-out F1): **{most_predictable}**")
    md.append(f"- Q2 Strongest subsystem-specific preference (behavior concentration proxy): **{strongest_pref}**")
    md.append(f"- Q3 Highest review-churn contributor (objection×rounds×volume proxy): **{top_churn}**")
    md.append(
        "- Q4 Reviewer-specific modeling vs discovered-rule-only baseline: "
        f"**F1 delta = {base['f1_delta']:+.3f}** (precision delta {base['precision_delta']:+.3f}, recall delta {base['recall_delta']:+.3f})"
    )
    if missing_rules:
        md.append("- Q5 Reviewer-specific rules not currently represented in KB (evidence-backed):")
        for x in missing_rules:
            md.append(f"  - {x['rule_gap']} (evidence count={x['evidence_count']})")
    else:
        md.append("- Q5 Reviewer-specific rules not represented in KB: **INSUFFICIENT_EVIDENCE**")

    md.append("")
    md.append("## Held-Out Lore Evidence Index")
    for row in holdout_lore:
        if row["lore_links"]:
            md.append(f"- Series {row['series_id']} `{row['series_name']}`")
            for l in row["lore_links"][:3]:
                md.append(f"  - {l}")

    (out_dir / "reviewer_behavior_report.md").write_text("\n".join(md))

    playbook = []
    playbook.append("# Maintainer Playbooks")
    playbook.append("")
    playbook.append("Evidence source: held-out Patchwork/lore benchmark and reviewer profiles in this run.")
    playbook.append("")
    for r in sorted(profiles.keys()):
        p = profiles[r]
        playbook.append(f"## {r}")
        playbook.append(f"- Interactions: {p['review_interactions']}")
        playbook.append(f"- Objection frequency: {p['objection_frequency']:.3f}")
        playbook.append(f"- Acceptance rate on reviewed accepted/rejected series: {p['acceptance_rate_on_reviewed_series']:.3f}")
        ax = p["behavior_axes"]
        playbook.append(
            "- Behavior axis scores: "
            f"split={ax['patch_split_preference']:.3f}, boundary={ax['ownership_boundary_sensitivity']:.3f}, "
            f"dt={ax['dt_schema_strictness']:.3f}, commit-msg={ax['commit_message_expectation']:.3f}, "
            f"pm={ax['pm_sequencing_preference']:.3f}, soundwire={ax['soundwire_lifecycle_preference']:.3f}"
        )
        topcats = p.get("objection_categories", {})
        topcats = sorted(topcats.items(), key=lambda kv: kv[1], reverse=True)[:5]
        playbook.append("- Top objection categories: " + ", ".join([f"{k}:{v}" for k, v in topcats]) if topcats else "- Top objection categories: INSUFFICIENT_EVIDENCE")
        phrases = p.get("recurring_phrases", [])
        if phrases:
            playbook.append("- Recurring phrase signals: " + ", ".join([f"{ph[0]} ({ph[1]})" for ph in phrases[:6]]))
        else:
            playbook.append("- Recurring phrase signals: INSUFFICIENT_EVIDENCE")
        playbook.append("- Patch topology preference: " + json.dumps(p.get("preferred_patch_topology", {}), ensure_ascii=True))
        playbook.append("")

    (out_dir / "maintainer_playbooks.md").write_text("\n".join(playbook))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-year", type=int, default=2019)
    ap.add_argument("--pages-per-query", type=int, default=10)
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--max-series", type=int, default=700)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache"

    client = PatchworkClient(cache_dir=cache_dir, workers=args.workers)

    series_rows, dataset_stats = build_dataset(
        client,
        min_year=args.min_year,
        pages_per_query=args.pages_per_query,
        per_page=args.per_page,
        max_series=args.max_series,
    )

    targets = collect_series_targets(series_rows)

    # reviewer pool: required + other reviewers with >=20 interactions
    interactions = Counter()
    for s in series_rows:
        for c in s.comments:
            rv = c.get("reviewer")
            if rv and rv != s.submitter and rv != c.get("patch_submitter"):
                interactions[rv] += 1

    other_ge20 = sorted([r for r, n in interactions.items() if n >= 20 and r not in TARGET_REVIEWERS])
    reviewer_pool = sorted(set(TARGET_REVIEWERS + other_ge20 + ["Krzysztof Kozlowski"]))

    train_rows, holdout_rows = split_train_holdout(series_rows, holdout_ratio=0.2)

    model = train_reviewer_models(train_rows, targets, reviewer_pool)
    benchmark = evaluate_predictions(holdout_rows, targets, model, reviewer_pool)

    profiles = build_profiles(series_rows, targets, reviewer_pool)
    interaction_graph = build_interaction_graph(series_rows, targets, reviewer_pool)

    # write artifacts
    serializable_profiles = {}
    for r, p in profiles.items():
        serializable_profiles[r] = {
            **p,
            "objection_categories": dict(p["objection_categories"]),
            "review_round_distribution": dict(p["review_round_distribution"]),
            "preferred_patch_topology": {
                **p["preferred_patch_topology"],
                "patch_size_bins": dict(p["preferred_patch_topology"]["patch_size_bins"]),
                "series_length_bins": dict(p["preferred_patch_topology"]["series_length_bins"]),
            },
        }

    with (out_dir / "reviewer_profiles.json").open("w") as f:
        json.dump(
            {
                "generated_at": dt.datetime.now().isoformat(),
                "dataset_stats": dataset_stats,
                "reviewers_modeled": reviewer_pool,
                "required_reviewers": TARGET_REVIEWERS,
                "other_reviewers_ge20": other_ge20,
                "interaction_counts": dict(interactions),
                "profiles": serializable_profiles,
            },
            f,
            indent=2,
        )

    with (out_dir / "reviewer_interaction_graph.json").open("w") as f:
        json.dump(interaction_graph, f, indent=2)

    with (out_dir / "reviewer_prediction_benchmark.json").open("w") as f:
        json.dump(
            {
                "generated_at": dt.datetime.now().isoformat(),
                "train_series": len(train_rows),
                "heldout_series": len(holdout_rows),
                "reviewers_modeled": reviewer_pool,
                "metrics": {
                    k: v
                    for k, v in benchmark.items()
                    if k not in {"heldout_predictions"}
                },
                "heldout_predictions": benchmark["heldout_predictions"],
            },
            f,
            indent=2,
        )

    write_report(
        out_dir=out_dir,
        dataset_stats=dataset_stats,
        profiles=serializable_profiles,
        benchmark=benchmark,
        reviewers_modeled=reviewer_pool,
        holdout_rows=holdout_rows,
        targets=targets,
    )

    print(json.dumps(
        {
            "out_dir": str(out_dir),
            "dataset_stats": dataset_stats,
            "train_series": len(train_rows),
            "heldout_series": len(holdout_rows),
            "reviewers_modeled": reviewer_pool,
            "other_reviewers_ge20": other_ge20,
            "metrics": benchmark,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
