"""Deterministic HTML parser for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import hashlib
from pathlib import Path
import re
from typing import Any

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticHtmlParseResult:
    parsed_document: dict[str, Any]
    deterministic_fingerprint: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)]


class _KnowledgeHubHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_script = 0
        self._in_style = 0

        self._capture_heading = False
        self._capture_block = False
        self._heading_level = 0
        self._heading_buffer: list[str] = []
        self._block_buffer: list[str] = []

        self.title = ""
        self._capture_title = False

        self.section_counter = 0
        self.current_section_id = "sec_0000"
        self.sections: list[dict[str, Any]] = [
            {
                "section_id": self.current_section_id,
                "heading": "DOCUMENT_ROOT",
                "level": 0,
                "order": 0,
                "text_chunks": [],
            }
        ]

    def _ensure_section(self) -> dict[str, Any]:
        if not self.sections:
            self.sections.append(
                {
                    "section_id": "sec_0000",
                    "heading": "DOCUMENT_ROOT",
                    "level": 0,
                    "order": 0,
                    "text_chunks": [],
                }
            )
        return self.sections[-1]

    def _append_chunk(self, text: str) -> None:
        chunk = _clean_text(text)
        if not chunk:
            return
        section = self._ensure_section()
        section["text_chunks"].append(chunk)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "script":
            self._in_script += 1
            return
        if lowered == "style":
            self._in_style += 1
            return
        if self._in_script or self._in_style:
            return

        if lowered == "title":
            self._capture_title = True
            return

        if re.fullmatch(r"h[1-6]", lowered):
            self._capture_heading = True
            self._heading_level = int(lowered[1])
            self._heading_buffer = []
            return

        if lowered in {"p", "li", "code", "pre", "td", "th", "span", "a", "label"}:
            self._capture_block = True
            self._block_buffer = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "script":
            self._in_script = max(0, self._in_script - 1)
            return
        if lowered == "style":
            self._in_style = max(0, self._in_style - 1)
            return
        if self._in_script or self._in_style:
            return

        if lowered == "title":
            self._capture_title = False
            self.title = _clean_text(" ".join(self._heading_buffer + self._block_buffer + [self.title]))
            return

        if re.fullmatch(r"h[1-6]", lowered) and self._capture_heading:
            heading = _clean_text(" ".join(self._heading_buffer))
            self._capture_heading = False
            self._heading_buffer = []
            if heading:
                self.section_counter += 1
                self.current_section_id = f"sec_{self.section_counter:04d}"
                self.sections.append(
                    {
                        "section_id": self.current_section_id,
                        "heading": heading,
                        "level": self._heading_level,
                        "order": self.section_counter,
                        "text_chunks": [],
                    }
                )
            return

        if lowered in {"p", "li", "code", "pre", "td", "th", "span", "a", "label"} and self._capture_block:
            block_text = _clean_text(" ".join(self._block_buffer))
            self._capture_block = False
            self._block_buffer = []
            if block_text:
                self._append_chunk(block_text)

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return
        text = _clean_text(data)
        if not text:
            return

        if self._capture_title:
            self.title = _clean_text(f"{self.title} {text}")
            return

        if self._capture_heading:
            self._heading_buffer.append(text)
            return

        if self._capture_block:
            self._block_buffer.append(text)


def parse_semantic_html(
    *,
    source_path: str | Path,
    source_id: str,
    source_version: str,
) -> SemanticHtmlParseResult:
    html_path = Path(source_path)

    if not html_path.exists() or not html_path.is_file():
        payload = {
            "schema_version": "1.0",
            "document_name": "kernel_semantic_html",
            "source_id": str(source_id),
            "source_version": str(source_version),
            "source_path": str(html_path),
            "classification": "FAIL_CLOSED_NO_SOURCE",
            "sections": [],
            "source_sha256": "",
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return SemanticHtmlParseResult(
            parsed_document=payload,
            deterministic_fingerprint=str(payload["deterministic_fingerprint"]),
        )

    text = html_path.read_text(encoding="utf-8", errors="ignore")
    parser = _KnowledgeHubHTMLParser()
    parser.feed(text)
    parser.close()

    sections: list[dict[str, Any]] = []
    for section in parser.sections:
        chunks = [_clean_text(chunk) for chunk in section.get("text_chunks", []) if _clean_text(chunk)]
        heading = _clean_text(section.get("heading", ""))
        if heading or chunks:
            section_payload = {
                "section_id": str(section.get("section_id", "")),
                "heading": heading or "UNTITLED",
                "level": int(section.get("level", 0)),
                "order": int(section.get("order", 0)),
                "text_chunks": chunks,
                "text_sha256": stable_fingerprint({"heading": heading, "text_chunks": chunks}),
            }
            sections.append(section_payload)

    all_text = "\n".join(
        [
            part
            for section in sections
            for part in ([section.get("heading", "")] + list(section.get("text_chunks", [])))
            if str(part).strip()
        ]
    )
    tokens = _tokenize(all_text)

    token_freq: dict[str, int] = {}
    for token in tokens:
        token_freq[token] = token_freq.get(token, 0) + 1
    vocabulary_top = [
        {"token": token, "frequency": freq}
        for token, freq in sorted(token_freq.items(), key=lambda item: (-item[1], item[0]))[:200]
    ]

    payload = {
        "schema_version": "1.0",
        "document_name": "kernel_semantic_html",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "source_path": str(html_path.resolve()),
        "source_sha256": _sha256_file(html_path),
        "title": _clean_text(parser.title) or "Qualcomm Audio Kernel Knowledge Hub",
        "section_count": len(sections),
        "sections": sections,
        "vocabulary_top": vocabulary_top,
        "classification": "PASS" if sections else "ADVISORY_ONLY_EMPTY_PARSE",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticHtmlParseResult(
        parsed_document=payload,
        deterministic_fingerprint=fingerprint,
    )
