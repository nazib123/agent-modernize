"""Agent 1: Legacy Analyzer — extracts business rules from legacy code.

Takes legacy source code as input and produces a Business Rule Inventory (BRI)
containing all explicit and implicit business rules and data constraints.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_EXTRACTION
from src.models.bri import (
    BusinessRule,
    BusinessRuleInventory,
    Confidence,
    DataConstraint,
    RuleCategory,
    RuleType,
)

logger = logging.getLogger(__name__)


def _safe_enum(enum_cls: type, value: str) -> Any:
    """Return the enum member for *value*, falling back to the first member."""
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning("Unknown %s value %r — using default", enum_cls.__name__, value)
        return list(enum_cls)[0]


LEGACY_ANALYZER_PROMPT = """You are an expert legacy systems analyst with 20 years of experience
in COBOL, PL/SQL, and enterprise telecom systems. Your task is to analyze legacy code and extract
ALL business rules — both explicit and implicit.

## Instructions

Analyze the following legacy code and produce a structured JSON output containing:

1. **Business Rules**: Every validation, precondition, computation, transformation, and
   postcondition encoded in the code. For each rule, provide:
   - id: Unique identifier (BR-001, BR-002, etc.)
   - description: Clear natural language description
   - type: One of "precondition", "validation", "computation", "transformation", "postcondition"
   - category: "explicit" (clearly stated in code) or "implicit" (inferred from patterns, defaults,
     control flow, or cross-module interactions)
   - source_lines: Approximate line range in the source
   - inputs: List of input variables/fields involved
   - effect: What happens when this rule fires (e.g., "REJECT with E001", "set X to Y")
   - confidence: "high", "medium", or "low"
   - implicit_reason: (only for implicit rules) Why this rule is not obvious from the code

2. **Data Constraints**: Type restrictions, value ranges, referential integrity rules, and
   business invariants. For each constraint:
   - id: Unique identifier (DC-001, DC-002, etc.)
   - description: Natural language description
   - field: The field or fields involved
   - constraint: Formal constraint expression
   - formula: (optional) Mathematical formula if applicable

## CRITICAL: Implicit Rule Detection

Pay special attention to:
- Silent transformations (values modified without error, e.g., priority downgrade)
- Conditional exemptions (e.g., Platinum tier bypasses a check)
- Default behaviors (what happens when no condition matches)
- Cross-field dependencies (field A's validation depends on field B's value)
- Skipped logic paths (entire code blocks skipped for certain order types)
- Threshold values defined as constants (may not be obvious as business rules)

## Output Format

Return ONLY valid JSON in this exact structure:
```json
{{
  "rules": [
    {{
      "id": "BR-001",
      "description": "...",
      "type": "precondition",
      "category": "explicit",
      "source_lines": "10-15",
      "inputs": ["field1", "field2"],
      "effect": "...",
      "confidence": "high",
      "implicit_reason": null
    }}
  ],
  "constraints": [
    {{
      "id": "DC-001",
      "description": "...",
      "field": "field_name",
      "constraint": "...",
      "formula": null
    }}
  ]
}}
```

## Legacy Code to Analyze

```
{legacy_code}
```
"""


class LegacyAnalyzerAgent(BaseAgent):
    """Extracts business rules and constraints from legacy code."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_EXTRACTION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Legacy Analyzer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Analyze legacy code and produce a Business Rule Inventory.

        Expects state keys:
            - legacy_code (str): The legacy source code to analyze.
            - scenario_id (str): Scenario identifier.

        Adds to state:
            - business_rules (BusinessRuleInventory): Extracted rules and constraints.
        """
        legacy_code = state["legacy_code"]
        scenario_id = state["scenario_id"]

        logger.info("[%s] Analyzing scenario %s", self.agent_name, scenario_id)

        prompt = LEGACY_ANALYZER_PROMPT.format(legacy_code=legacy_code)
        response = self._invoke_llm(prompt)
        parsed = self._parse_json_response(response)

        bri = self._build_bri(scenario_id, parsed)
        logger.info(
            "[%s] Extracted %d rules (%d explicit, %d implicit) and %d constraints",
            self.agent_name,
            bri.total_rule_count,
            len(bri.explicit_rules),
            len(bri.implicit_rules),
            len(bri.constraints),
        )

        state["business_rules"] = bri
        return state

    def _build_bri(self, scenario_id: str, parsed: dict) -> BusinessRuleInventory:
        """Convert parsed JSON into typed BusinessRuleInventory."""
        rules = []
        for r in parsed.get("rules", []):
            rules.append(
                BusinessRule(
                    id=r["id"],
                    description=r["description"],
                    rule_type=_safe_enum(RuleType, r.get("type", "validation")),
                    category=_safe_enum(RuleCategory, r.get("category", "explicit")),
                    source_lines=r.get("source_lines", ""),
                    inputs=r.get("inputs", []),
                    effect=r.get("effect", ""),
                    confidence=Confidence(r.get("confidence", "high")),
                    implicit_reason=r.get("implicit_reason"),
                )
            )

        constraints = []
        for c in parsed.get("constraints", []):
            constraints.append(
                DataConstraint(
                    id=c["id"],
                    description=c["description"],
                    field_name=c.get("field", ""),
                    constraint=c.get("constraint", ""),
                    formula=c.get("formula"),
                )
            )

        return BusinessRuleInventory(
            scenario_id=scenario_id,
            rules=rules,
            constraints=constraints,
        )
