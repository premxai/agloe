"""Lineage Event IR. Ordering is not causality: edges come only from LineageEdge."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    MESSAGE = "message"
    EDIT = "edit"
    ACTION = "action"
    MEMORY = "memory"
    READ = "read"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    timestamp: datetime
    agent_id: str
    event_type: EventType
    content: str
    target_agent_id: str | None = None
    room_or_channel: str | None = None
    session_id: str | None = None
    source_dataset: str
    raw_source_ref: str
    screenshot_ref: str | None = None


class Relation(str, Enum):
    COPY = "copy"
    PARAPHRASE = "paraphrase"
    EXTEND = "extend"
    COMBINE = "combine"
    REJECT = "reject"
    WARN = "warn"
    INDEPENDENT = "independent"


class EvidenceTier(str, Enum):
    DIRECT = "A"
    SUPPORTED = "B"
    POSSIBLE = "C"
    INDEPENDENT = "D"


class LineageEdge(BaseModel):
    """Derived analysis, kept separate from raw events."""

    model_config = ConfigDict(extra="forbid")

    child_event_id: str
    parent_event_ids: list[str] = Field(min_length=1)
    primary_parent_id: str
    relation: Relation
    evidence_tier: EvidenceTier
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    preserved_atoms: list[str] = []
    added_atoms: list[str] = []
    removed_atoms: list[str] = []
    rationale: str = ""
