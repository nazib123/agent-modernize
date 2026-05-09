"""Behavioral Specification Graph (BSG) — core intermediate representation.

A directed acyclic graph that captures business operations, control flow,
pre/postconditions, and global invariants extracted from legacy systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EdgeLabel(str, Enum):
    SEQUENCE = "sequence"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    ERROR = "error"


@dataclass
class OperationNode:
    """A discrete business operation in the BSG."""

    id: str
    name: str
    description: str
    inputs: list[dict[str, str]] = field(default_factory=list)
    outputs: list[dict[str, str]] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    business_rule_ids: list[str] = field(default_factory=list)
    error_behavior: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "business_rule_ids": self.business_rule_ids,
            "error_behavior": self.error_behavior,
        }


@dataclass
class BSGEdge:
    """A directed edge between two operation nodes."""

    source_id: str
    target_id: str
    label: EdgeLabel
    condition: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "label": self.label.value,
            "condition": self.condition,
        }


@dataclass
class BehavioralSpecificationGraph:
    """Complete BSG for a legacy system scenario."""

    scenario_id: str
    nodes: list[OperationNode] = field(default_factory=list)
    edges: list[BSGEdge] = field(default_factory=list)
    global_invariants: list[str] = field(default_factory=list)

    def get_node(self, node_id: str) -> OperationNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_entry_nodes(self) -> list[OperationNode]:
        """Nodes with no incoming edges."""
        targets = {e.target_id for e in self.edges}
        return [n for n in self.nodes if n.id not in targets]

    def get_exit_nodes(self) -> list[OperationNode]:
        """Nodes with no outgoing edges."""
        sources = {e.source_id for e in self.edges}
        return [n for n in self.nodes if n.id not in sources]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict:
        """Serialize for LLM prompt injection or JSON export."""
        return {
            "scenario_id": self.scenario_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "global_invariants": self.global_invariants,
        }
