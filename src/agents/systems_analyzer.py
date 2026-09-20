"""Agent 1b: Systems Analyzer — extracts I/O specs, COPYBOOK field maps, and dependencies.

Takes legacy COBOL source (and optional COPYBOOK text) and produces a SystemsLayer
containing byte-level field maps, record format specs, external dependency classifications,
and control flow type.

This fills the gap between business-rule extraction (BRI) and specification generation (BSG)
by providing the systems-level "how" that the business-level "what" cannot express.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_EXTRACTION
from src.models.bsg import (
    DataEncoding,
    DependencyAvailability,
    DependencySpec,
    IOFieldSpec,
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


SYSTEMS_ANALYZER_PROMPT = """You are an expert COBOL systems analyst who specializes in
binary file formats, COPYBOOK layouts, and mainframe I/O. Your task is to extract the
**systems-level specification** from legacy COBOL source code.

## What to Extract

### 1. Input/Output File Specifications
From FD (File Description) and SD (Sort Description) sections, extract:
- File name (DD name or SELECT name)
- Record format: "F" (fixed), "V" (variable), "VB" (variable blocked)
- Record length (LRECL)
- Block size (BLKSIZE) if specified
- Encoding: "ebcdic" (default for mainframe) or "ascii"
- Segment hierarchy: for IMS unload files, the ordered list of segment names
  (e.g., ["CRID", "CRCOMD", "CRMDATA", "CRUSOC"])
- Header size: bytes before data records begin (e.g., IMS directory = 1440)

### 2. COPYBOOK Field Map
For EVERY field referenced in the program's business logic, provide:
- name: COBOL field name (e.g., "USOC-C", "ACCT-TYPE")
- copybook: which COPYBOOK it belongs to (e.g., "RF01A001")
- offset: 0-indexed byte offset from the start of the segment/record data
- length: field length in bytes
- pic_clause: the PIC clause (e.g., "PIC X(5)", "S9(5) COMP-3")
- encoding: "ebcdic", "comp-3", "comp", or "display"
- decimal_places: for numeric fields with implied decimal (V in PIC clause)
- requires_expand: true if the field is in a version-mapped portion that needs
  an EXPAND/migration routine before reading

### 3. External Dependencies
For EVERY CALL statement or external routine reference:
- name: the called program/routine name
- call_type: "CALL", "COPY", "CICS", or "DB2"
- availability: "available" (source code provided), "opaque" (source not available),
  or "source_needed" (source exists somewhere but not provided)
- blocked_fields: list of output fields that CANNOT be computed without this dependency
- parameters: the COBOL identifiers passed to the CALL
- impact: human-readable description of what this dependency blocks

### 4. Control Flow Type
Classify the program's main processing loop:
- "sequential" — reads records one by one, processes linearly
- "state_machine" — uses EVALUATE/WHEN to branch by record/segment type, maintaining
  state across iterations (e.g., IMS segment processing)
- "batch_update" — reads master + transaction files, applies updates
- "report_generator" — reads data, accumulates, produces formatted output

## Output Format

Return ONLY valid JSON:
```json
{{
  "input_files": [
    {{
      "file_name": "UNLOAD-FILE",
      "record_format": "V",
      "record_length": 0,
      "block_size": 0,
      "encoding": "ebcdic",
      "segment_hierarchy": ["CRID", "CRCOMD", "CRMDATA", "CRUSOC"],
      "header_size": 1440
    }}
  ],
  "output_files": [
    {{
      "file_name": "OUT-USOC-FILE",
      "record_format": "F",
      "record_length": 30,
      "encoding": "ebcdic"
    }}
  ],
  "field_map": [
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
  "dependencies": [
    {{
      "name": "R000XPND",
      "call_type": "CALL",
      "availability": "opaque",
      "blocked_fields": ["USOC-QUAN-C", "USOC-RATE-C", "BUS-UNIT-IND"],
      "parameters": ["UNLOAD-RCD-GENERAL", "EXPAND-RECORD", "RELEASE-VERSION"],
      "impact": "Version migration routine — fields in data portion are unreachable"
    }}
  ],
  "control_flow_type": "state_machine"
}}
```

## COBOL Source Code

```
{legacy_code}
```

{copybook_section}
"""

COPYBOOK_SECTION_TEMPLATE = """## COPYBOOK Sources

{copybook_text}
"""


class SystemsAnalyzerAgent(BaseAgent):
    """Extracts systems-level specification from COBOL source and COPYBOOKs."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_EXTRACTION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Systems Analyzer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Extract SystemsLayer from COBOL source and optional COPYBOOKs.

        Expects state keys:
            - legacy_code (str): COBOL source text.
            - copybook_sources (dict[str, str], optional): name → text of COPYBOOKs.

        Adds to state:
            - systems_spec (SystemsLayer): Extracted systems specification.
        """
        legacy_code = state["legacy_code"]
        scenario_id = state.get("scenario_id", "unknown")
        copybooks = state.get("copybook_sources", {})

        logger.info("[%s] Extracting systems spec for %s", self.agent_name, scenario_id)

        copybook_section = ""
        if copybooks:
            parts = []
            for name, text in copybooks.items():
                parts.append(f"### {name}\n```\n{text}\n```")
            copybook_section = COPYBOOK_SECTION_TEMPLATE.format(
                copybook_text="\n\n".join(parts)
            )

        prompt = SYSTEMS_ANALYZER_PROMPT.format(
            legacy_code=legacy_code,
            copybook_section=copybook_section,
        )
        response = self._invoke_llm(prompt)
        parsed = self._parse_json_response(response)

        systems_spec = self._build_systems_layer(parsed)

        n_fields = len(systems_spec.field_map)
        n_deps = len(systems_spec.dependencies)
        n_opaque = len(systems_spec.get_opaque_dependencies())
        n_blocked = len(systems_spec.get_blocked_fields())

        logger.info(
            "[%s] Extracted: %d fields, %d dependencies (%d opaque, %d blocked fields), "
            "control_flow=%s",
            self.agent_name, n_fields, n_deps, n_opaque, n_blocked,
            systems_spec.control_flow_type,
        )

        state["systems_spec"] = systems_spec
        return state

    def _build_systems_layer(self, parsed: dict) -> SystemsLayer:
        """Convert parsed JSON into typed SystemsLayer."""
        input_files = [
            self._build_record_format(f) for f in parsed.get("input_files", [])
        ]
        output_files = [
            self._build_record_format(f) for f in parsed.get("output_files", [])
        ]
        field_map = [
            self._build_io_field(f) for f in parsed.get("field_map", [])
        ]
        dependencies = [
            self._build_dependency(d) for d in parsed.get("dependencies", [])
        ]

        return SystemsLayer(
            input_files=input_files,
            output_files=output_files,
            field_map=field_map,
            dependencies=dependencies,
            control_flow_type=parsed.get("control_flow_type", "sequential"),
        )

    @staticmethod
    def _build_record_format(raw: dict) -> RecordFormatSpec:
        return RecordFormatSpec(
            file_name=raw["file_name"],
            record_format=raw.get("record_format", "F"),
            record_length=raw.get("record_length", 0),
            block_size=raw.get("block_size", 0),
            encoding=_safe_enum(DataEncoding, raw.get("encoding", "ebcdic")),
            segment_hierarchy=raw.get("segment_hierarchy", []),
            header_size=raw.get("header_size", 0),
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
