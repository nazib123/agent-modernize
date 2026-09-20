"""Behavioral Specification Graph (BSG) — core intermediate representation.

A directed graph that captures business operations, control flow,
pre/postconditions, global invariants, and systems-level specifications
(I/O formats, byte-level field maps, external dependencies) extracted
from legacy systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EdgeLabel(str, Enum):
    SEQUENCE = "sequence"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    ERROR = "error"
    LOOP = "loop"
    BRANCH = "branch"


class DataEncoding(str, Enum):
    EBCDIC = "ebcdic"
    ASCII = "ascii"
    COMP3 = "comp-3"
    COMP = "comp"
    DISPLAY = "display"


class DependencyAvailability(str, Enum):
    AVAILABLE = "available"
    OPAQUE = "opaque"
    SOURCE_NEEDED = "source_needed"


@dataclass
class IOFieldSpec:
    """Byte-level specification of a single COPYBOOK field."""

    name: str
    copybook: str
    offset: int
    length: int
    pic_clause: str
    encoding: DataEncoding = DataEncoding.DISPLAY
    decimal_places: int = 0
    redefines: str | None = None
    requires_expand: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "copybook": self.copybook,
            "offset": self.offset,
            "length": self.length,
            "pic_clause": self.pic_clause,
            "encoding": self.encoding.value,
            "decimal_places": self.decimal_places,
            "redefines": self.redefines,
            "requires_expand": self.requires_expand,
        }


@dataclass
class DependencySpec:
    """External dependency (CALL, COPY, subroutine) with availability status."""

    name: str
    call_type: str
    availability: DependencyAvailability = DependencyAvailability.AVAILABLE
    blocked_fields: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    impact: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "call_type": self.call_type,
            "availability": self.availability.value,
            "blocked_fields": self.blocked_fields,
            "parameters": self.parameters,
            "impact": self.impact,
        }


@dataclass
class RecordFormatSpec:
    """File-level I/O specification from COBOL FD/SD sections."""

    file_name: str
    record_format: str
    record_length: int
    block_size: int = 0
    encoding: DataEncoding = DataEncoding.EBCDIC
    segment_hierarchy: list[str] = field(default_factory=list)
    header_size: int = 0

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "record_format": self.record_format,
            "record_length": self.record_length,
            "block_size": self.block_size,
            "encoding": self.encoding.value,
            "segment_hierarchy": self.segment_hierarchy,
            "header_size": self.header_size,
        }


@dataclass
class SystemsLayer:
    """Systems-level specification — the 'how' beneath the business 'what'.

    Captures I/O formats, COPYBOOK field maps, external dependencies,
    and control flow structure that the business-rule layer cannot express.
    """

    input_files: list[RecordFormatSpec] = field(default_factory=list)
    output_files: list[RecordFormatSpec] = field(default_factory=list)
    field_map: list[IOFieldSpec] = field(default_factory=list)
    dependencies: list[DependencySpec] = field(default_factory=list)
    control_flow_type: str = "sequential"

    def to_dict(self) -> dict:
        return {
            "input_files": [f.to_dict() for f in self.input_files],
            "output_files": [f.to_dict() for f in self.output_files],
            "field_map": [f.to_dict() for f in self.field_map],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "control_flow_type": self.control_flow_type,
        }

    def get_opaque_dependencies(self) -> list[DependencySpec]:
        """Return dependencies whose source is unavailable."""
        return [
            d for d in self.dependencies
            if d.availability == DependencyAvailability.OPAQUE
        ]

    def get_blocked_fields(self) -> list[str]:
        """Return all field names blocked by opaque dependencies."""
        blocked: list[str] = []
        for dep in self.get_opaque_dependencies():
            blocked.extend(dep.blocked_fields)
        return blocked


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
    io_fields: list[IOFieldSpec] = field(default_factory=list)
    node_dependencies: list[DependencySpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
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
        if self.io_fields:
            result["io_fields"] = [f.to_dict() for f in self.io_fields]
        if self.node_dependencies:
            result["node_dependencies"] = [d.to_dict() for d in self.node_dependencies]
        return result


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
    systems_layer: SystemsLayer | None = None

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
        result = {
            "scenario_id": self.scenario_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "global_invariants": self.global_invariants,
        }
        if self.systems_layer:
            result["systems_layer"] = self.systems_layer.to_dict()
        return result
