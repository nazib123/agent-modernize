"""Business Rule Inventory (BRI) — output of Legacy Analyzer Agent.

Structured representation of all business rules and data constraints
extracted from legacy artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RuleType(str, Enum):
    PRECONDITION = "precondition"
    VALIDATION = "validation"
    COMPUTATION = "computation"
    TRANSFORMATION = "transformation"
    POSTCONDITION = "postcondition"


class RuleCategory(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class BusinessRule:
    """A single business rule extracted from legacy code."""

    id: str
    description: str
    rule_type: RuleType
    category: RuleCategory
    source_lines: str
    inputs: list[str]
    effect: str
    confidence: Confidence = Confidence.HIGH
    implicit_reason: str | None = None


@dataclass
class DataConstraint:
    """A data-level constraint extracted from legacy code."""

    id: str
    description: str
    field_name: str
    constraint: str
    formula: str | None = None


@dataclass
class BusinessRuleInventory:
    """Complete inventory of extracted business rules and constraints."""

    scenario_id: str
    rules: list[BusinessRule] = field(default_factory=list)
    constraints: list[DataConstraint] = field(default_factory=list)

    @property
    def explicit_rules(self) -> list[BusinessRule]:
        return [r for r in self.rules if r.category == RuleCategory.EXPLICIT]

    @property
    def implicit_rules(self) -> list[BusinessRule]:
        return [r for r in self.rules if r.category == RuleCategory.IMPLICIT]

    @property
    def total_rule_count(self) -> int:
        return len(self.rules)

    def to_dict(self) -> dict:
        """Serialize to dictionary for LLM prompt injection."""
        return {
            "scenario_id": self.scenario_id,
            "rules": [
                {
                    "id": r.id,
                    "description": r.description,
                    "type": r.rule_type.value,
                    "category": r.category.value,
                    "inputs": r.inputs,
                    "effect": r.effect,
                    "confidence": r.confidence.value,
                }
                for r in self.rules
            ],
            "constraints": [
                {
                    "id": c.id,
                    "description": c.description,
                    "field": c.field_name,
                    "constraint": c.constraint,
                }
                for c in self.constraints
            ],
        }
