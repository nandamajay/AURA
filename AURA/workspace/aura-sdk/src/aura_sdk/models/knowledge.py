"""Knowledge system models — rules, evidence, maintainers."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RuleCategory(StrEnum):
    """Categories of migration rules."""

    API_MAPPING = "api_mapping"
    MACRO = "macro"
    PATTERN = "pattern"
    STYLE = "style"
    PHILOSOPHY = "philosophy"


class MigrationRule(BaseModel):
    """A learned rule for converting downstream to upstream code."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    subsystem_id: str = ""
    category: RuleCategory = RuleCategory.PATTERN
    downstream_pattern: str = ""
    upstream_equivalent: str = ""
    description: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_count: int = 0
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_applied_at: datetime | None = None
    success_count: int = 0
    failure_count: int = 0


class EvidenceType(StrEnum):
    """Types of evidence linking patches to rules."""

    REFERENCE = "reference"
    JUSTIFICATION = "justification"
    WARNING = "warning"
    CORRECTION = "correction"


class EvidenceLink(BaseModel):
    """Evidence linking a patch to upstream references."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    patch_id: str = ""
    rule_id: str = ""
    evidence_type: EvidenceType = EvidenceType.REFERENCE
    source_ref: str = ""  # git commit hash or URL
    source_file: str = ""  # file path in kernel tree
    source_lines: str = ""  # line range "120-145"
    source_excerpt: str = ""  # relevant code excerpt
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaintainerProfile(BaseModel):
    """Profile of a kernel subsystem maintainer."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""
    email: str = ""
    subsystem_id: str = ""
    acceptance_rate: float | None = None
    review_count: int = 0
    common_nak_reasons: list[str] = Field(default_factory=list)
    preferred_patterns: list[str] = Field(default_factory=list)
    personality_summary: str = ""
    last_analyzed_at: datetime | None = None
