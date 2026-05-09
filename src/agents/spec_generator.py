"""Agent 2: Specification Generator — transforms BRI into a BSG.

Takes a Business Rule Inventory and produces a Behavioral Specification Graph
that formally represents operations, control flow, pre/postconditions, and invariants.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_EXTRACTION
from src.models.bri import BusinessRuleInventory
from src.models.bsg import (
    BehavioralSpecificationGraph,
    BSGEdge,
    EdgeLabel,
    OperationNode,
)

logger = logging.getLogger(__name__)

SPEC_GENERATOR_PROMPT = """You are an expert software architect specializing in behavioral
specification and formal modeling. Your task is to convert extracted business rules into a
Behavioral Specification Graph (BSG).

## What is a BSG?

A BSG is a directed acyclic graph where:
- **Nodes** = discrete business operations (e.g., "validate_account", "calculate_pricing")
- **Edges** = control flow between operations, labeled as: sequence, conditional, parallel, error
- **Preconditions** = what must be true BEFORE an operation executes
- **Postconditions** = what must be true AFTER an operation completes
- **Global Invariants** = constraints that must hold throughout the entire workflow

## Instructions

Given the Business Rule Inventory below, produce a BSG that:

1. Decomposes the workflow into discrete operation nodes (each node = one logical step)
2. Connects nodes with labeled edges showing control flow
3. Attaches preconditions and postconditions from the business rules to each node
4. Maps each business rule ID to the node(s) it governs
5. Defines global invariants (constraints that span the entire workflow)

## Output Format

Return ONLY valid JSON:
```json
{{
  "nodes": [
    {{
      "id": "op_001",
      "name": "validate_order_type",
      "description": "Check that order type is valid (NEW, DIS, MOD)",
      "inputs": [{{"name": "order_type", "type": "string"}}],
      "outputs": [{{"name": "valid", "type": "boolean"}}],
      "preconditions": ["order_type is not null"],
      "postconditions": ["order_type in ('NEW', 'DIS', 'MOD')"],
      "business_rule_ids": ["BR-001"],
      "error_behavior": "Return error E011"
    }}
  ],
  "edges": [
    {{
      "source": "op_001",
      "target": "op_002",
      "label": "sequence",
      "condition": null
    }},
    {{
      "source": "op_002",
      "target": "op_reject",
      "label": "error",
      "condition": "account not found"
    }}
  ],
  "global_invariants": [
    "order_total = subtotal + tax_amount",
    "All monetary values are non-negative DECIMAL(9,2)"
  ]
}}
```

## Business Rule Inventory

```json
{bri_json}
```
"""


class SpecGeneratorAgent(BaseAgent):
    """Transforms Business Rule Inventory into a Behavioral Specification Graph."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_EXTRACTION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Specification Generator"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate BSG from Business Rule Inventory.

        Expects state keys:
            - business_rules (BusinessRuleInventory): Extracted rules.
            - scenario_id (str): Scenario identifier.

        Adds to state:
            - bsg (BehavioralSpecificationGraph): The generated BSG.
        """
        bri: BusinessRuleInventory = state["business_rules"]
        scenario_id = state["scenario_id"]

        logger.info("[%s] Generating BSG for scenario %s", self.agent_name, scenario_id)

        bri_json = json.dumps(bri.to_dict(), indent=2)
        prompt = SPEC_GENERATOR_PROMPT.format(bri_json=bri_json)
        response = self._invoke_llm(prompt)
        parsed = self._parse_json_response(response)

        bsg = self._build_bsg(scenario_id, parsed)
        logger.info(
            "[%s] Generated BSG with %d nodes, %d edges, %d invariants",
            self.agent_name,
            bsg.node_count,
            bsg.edge_count,
            len(bsg.global_invariants),
        )

        state["bsg"] = bsg
        return state

    def _build_bsg(self, scenario_id: str, parsed: dict) -> BehavioralSpecificationGraph:
        """Convert parsed JSON into typed BehavioralSpecificationGraph."""
        nodes = []
        for n in parsed.get("nodes", []):
            nodes.append(
                OperationNode(
                    id=n["id"],
                    name=n["name"],
                    description=n.get("description", ""),
                    inputs=n.get("inputs", []),
                    outputs=n.get("outputs", []),
                    preconditions=n.get("preconditions", []),
                    postconditions=n.get("postconditions", []),
                    business_rule_ids=n.get("business_rule_ids", []),
                    error_behavior=n.get("error_behavior"),
                )
            )

        edges = []
        for e in parsed.get("edges", []):
            edges.append(
                BSGEdge(
                    source_id=e["source"],
                    target_id=e["target"],
                    label=EdgeLabel(e["label"]),
                    condition=e.get("condition"),
                )
            )

        return BehavioralSpecificationGraph(
            scenario_id=scenario_id,
            nodes=nodes,
            edges=edges,
            global_invariants=parsed.get("global_invariants", []),
        )
