"""Shared data models for the BSG compiler."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompiledRule:
    rule_id: str
    description: str
    rule_type: str
    category: str
    inputs: list[str]
    effect: str
    implicit_reason: str | None = None


@dataclass
class CompilationResult:
    scenario_id: str
    status: str = "OK"  # "OK" or "REJECTED"
    error_code: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    rules_fired: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
