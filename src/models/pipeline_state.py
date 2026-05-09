"""Pipeline state shared across all agents in the AgentModernize pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.models.bri import BusinessRuleInventory
from src.models.bsg import BehavioralSpecificationGraph
from src.models.equivalence_report import BehavioralEquivalenceReport


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineState:
    """Shared state passed through the LangGraph pipeline.

    Each agent reads from and writes to this state, enabling
    traceability from legacy artifacts through intermediate
    representations to the final modernized output.
    """

    scenario_id: str
    legacy_code: str
    legacy_code_path: str

    business_rules: BusinessRuleInventory | None = None
    bsg: BehavioralSpecificationGraph | None = None
    modern_code: str | None = None
    modern_tests: str | None = None
    equiv_report: BehavioralEquivalenceReport | None = None

    iteration: int = 0
    max_iterations: int = 3
    status: PipelineStatus = PipelineStatus.PENDING
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def should_retry(self) -> bool:
        """Whether the feedback loop should trigger another iteration."""
        if self.equiv_report is None:
            return False
        if self.iteration >= self.max_iterations:
            return False
        return not self.equiv_report.all_passed
