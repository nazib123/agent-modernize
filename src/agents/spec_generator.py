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
    DataEncoding,
    DependencyAvailability,
    DependencySpec,
    EdgeLabel,
    IOFieldSpec,
    OperationNode,
    RecordFormatSpec,
    SystemsLayer,
)

logger = logging.getLogger(__name__)


def _safe_enum(enum_cls: type, value: str) -> Any:
    """Return the enum member for *value*, falling back to the first member."""
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning("Unknown %s value %r — using default", enum_cls.__name__, value)
        return list(enum_cls)[0]


SPEC_GENERATOR_PROMPT = """You are an expert software architect specializing in behavioral
specification and formal modeling. Your task is to convert extracted business rules into a
Behavioral Specification Graph (BSG), enriched with systems-level I/O specifications.

## What is a BSG?

A BSG is a directed graph where:
- **Nodes** = discrete business operations (e.g., "validate_account", "process_segment")
- **Edges** = control flow between operations, labeled as:
  - "sequence" — one step after another
  - "conditional" — follows only when a condition is true
  - "loop" — repeats (e.g., PERFORM UNTIL, read-process loop)
  - "branch" — one of N paths selected by EVALUATE/WHEN or IF/ELSE
  - "error" — taken on failure
  - "parallel" — concurrent execution
- **io_fields** = byte-level field specifications attached to each node (from COPYBOOKs)
- **node_dependencies** = external calls needed by a node (with availability status)
- **Preconditions / Postconditions** = what must be true before/after
- **Global Invariants** = constraints that hold throughout

## Instructions

Given the Business Rule Inventory (and optional Systems Specification) below, produce a BSG:

1. Decompose the workflow into discrete operation nodes
2. Connect nodes with labeled edges — use "loop" for read-process cycles, "branch" for
   EVALUATE/WHEN dispatching by record or segment type
3. For EACH node that reads or writes data fields, attach an "io_fields" array with the
   byte-level specification of every field that node touches
4. For EACH node that depends on an external routine, attach a "node_dependencies" array
5. Map each business rule ID to the node(s) it governs
6. Define global invariants

## Output Format

Return ONLY valid JSON:
```json
{{
  "nodes": [
    {{
      "id": "op_001",
      "name": "process_crcomd",
      "description": "Extract BCS, CSN from CRCOMD segment",
      "inputs": [{{"name": "CRCOMD_segment", "type": "bytes"}}],
      "outputs": [{{"name": "bcs", "type": "string"}}, {{"name": "csn_ind", "type": "string"}}],
      "preconditions": ["segment type is CRCOMD", "account is live"],
      "postconditions": ["BCS is set", "CSN-IND is set"],
      "business_rule_ids": ["BR-003", "BR-009"],
      "error_behavior": null,
      "io_fields": [
        {{
          "name": "ACCT-TYPE",
          "copybook": "RF01A001",
          "offset": 3,
          "length": 1,
          "pic_clause": "PIC X(1)",
          "encoding": "ebcdic",
          "decimal_places": 0,
          "requires_expand": false
        }}
      ],
      "node_dependencies": []
    }}
  ],
  "edges": [
    {{"source": "op_loop", "target": "op_001", "label": "branch", "condition": "segment == CRCOMD"}},
    {{"source": "op_001", "target": "op_loop", "label": "loop", "condition": "more records"}}
  ],
  "global_invariants": [
    "Output records are always 30 bytes EBCDIC"
  ]
}}
```

## Business Rule Inventory

```json
{bri_json}
```

{systems_section}
"""

SYSTEMS_SECTION_TEMPLATE = """## Systems Specification

The following I/O specs, field maps, and external dependencies were extracted from
COBOL FD sections and COPYBOOKs. Use these to populate the `io_fields` and
`node_dependencies` arrays on each BSG node.

```json
{systems_json}
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
        """Generate BSG from Business Rule Inventory + optional SystemsSpec.

        Expects state keys:
            - business_rules (BusinessRuleInventory): Extracted rules.
            - scenario_id (str): Scenario identifier.
            - systems_spec (SystemsLayer, optional): Extracted systems specification.

        Adds to state:
            - bsg (BehavioralSpecificationGraph): The generated BSG.
        """
        bri: BusinessRuleInventory = state["business_rules"]
        scenario_id = state["scenario_id"]
        systems_spec: SystemsLayer | None = state.get("systems_spec")

        logger.info("[%s] Generating BSG for scenario %s", self.agent_name, scenario_id)

        bri_json = json.dumps(bri.to_dict(), indent=2)

        systems_section = ""
        if systems_spec is not None:
            systems_json = json.dumps(systems_spec.to_dict(), indent=2)
            systems_section = SYSTEMS_SECTION_TEMPLATE.format(systems_json=systems_json)

        prompt = SPEC_GENERATOR_PROMPT.format(
            bri_json=bri_json,
            systems_section=systems_section,
        )
        response = self._invoke_llm(prompt)
        parsed = self._parse_json_response(response)

        bsg = self._build_bsg(scenario_id, parsed)

        if systems_spec is not None and bsg.systems_layer is None:
            bsg.systems_layer = systems_spec

        logger.info(
            "[%s] Generated BSG with %d nodes, %d edges, %d invariants, systems=%s",
            self.agent_name,
            bsg.node_count,
            bsg.edge_count,
            len(bsg.global_invariants),
            bsg.systems_layer is not None,
        )

        state["bsg"] = bsg
        return state

    def _build_bsg(self, scenario_id: str, parsed: dict) -> BehavioralSpecificationGraph:
        """Convert parsed JSON into typed BehavioralSpecificationGraph."""
        nodes = []
        for n in parsed.get("nodes", []):
            io_fields = [
                self._build_io_field(f) for f in n.get("io_fields", [])
            ]
            node_deps = [
                self._build_dependency(d) for d in n.get("node_dependencies", [])
            ]
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
                    io_fields=io_fields,
                    node_dependencies=node_deps,
                )
            )

        edges = []
        for e in parsed.get("edges", []):
            edges.append(
                BSGEdge(
                    source_id=e["source"],
                    target_id=e["target"],
                    label=_safe_enum(EdgeLabel, e["label"]),
                    condition=e.get("condition"),
                )
            )

        systems_layer = None
        if "systems_layer" in parsed:
            systems_layer = self._build_systems_layer(parsed["systems_layer"])
        elif state_systems := getattr(self, "_pending_systems_layer", None):
            systems_layer = state_systems

        return BehavioralSpecificationGraph(
            scenario_id=scenario_id,
            nodes=nodes,
            edges=edges,
            global_invariants=parsed.get("global_invariants", []),
            systems_layer=systems_layer,
        )

    @staticmethod
    def _build_io_field(raw: dict) -> IOFieldSpec:
        return IOFieldSpec(
            name=raw["name"],
            copybook=raw.get("copybook", ""),
            offset=raw.get("offset", 0),
            length=raw.get("length", 0),
            pic_clause=raw.get("pic_clause", ""),
            encoding=_safe_enum(DataEncoding, raw.get("encoding", "display")),
            decimal_places=raw.get("decimal_places", 0),
            redefines=raw.get("redefines"),
            requires_expand=raw.get("requires_expand", False),
        )

    @staticmethod
    def _build_dependency(raw: dict) -> DependencySpec:
        return DependencySpec(
            name=raw["name"],
            call_type=raw.get("call_type", "CALL"),
            availability=_safe_enum(
                DependencyAvailability, raw.get("availability", "available")
            ),
            blocked_fields=raw.get("blocked_fields", []),
            parameters=raw.get("parameters", []),
            impact=raw.get("impact", ""),
        )

    def _build_systems_layer(self, raw: dict) -> SystemsLayer:
        input_files = [
            RecordFormatSpec(
                file_name=f["file_name"],
                record_format=f.get("record_format", "F"),
                record_length=f.get("record_length", 0),
                block_size=f.get("block_size", 0),
                encoding=_safe_enum(DataEncoding, f.get("encoding", "ebcdic")),
                segment_hierarchy=f.get("segment_hierarchy", []),
                header_size=f.get("header_size", 0),
            )
            for f in raw.get("input_files", [])
        ]
        output_files = [
            RecordFormatSpec(
                file_name=f["file_name"],
                record_format=f.get("record_format", "F"),
                record_length=f.get("record_length", 0),
                block_size=f.get("block_size", 0),
                encoding=_safe_enum(DataEncoding, f.get("encoding", "ebcdic")),
                segment_hierarchy=f.get("segment_hierarchy", []),
                header_size=f.get("header_size", 0),
            )
            for f in raw.get("output_files", [])
        ]
        field_map = [self._build_io_field(f) for f in raw.get("field_map", [])]
        dependencies = [self._build_dependency(d) for d in raw.get("dependencies", [])]

        return SystemsLayer(
            input_files=input_files,
            output_files=output_files,
            field_map=field_map,
            dependencies=dependencies,
            control_flow_type=raw.get("control_flow_type", "sequential"),
        )
