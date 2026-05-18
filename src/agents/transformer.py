"""Agent 3: Modernization Transformer — generates modern code from BSG.

Takes a Behavioral Specification Graph and produces a modern Python/FastAPI
implementation that preserves all behavioral contracts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_GENERATION
from src.models.bsg import BehavioralSpecificationGraph

logger = logging.getLogger(__name__)

TRANSFORMER_PROMPT = """You are an expert software engineer specializing in modernizing legacy
telecom systems into clean, modern Python APIs. Your task is to generate a complete, runnable
Python implementation from a Behavioral Specification Graph (BSG).

## Instructions

Generate a SINGLE Python file that implements the entire workflow described in the BSG below.

Requirements:
1. Use **Pydantic** models for all data structures (input/output/internal)
2. Use **FastAPI** for the API endpoint
3. Implement EVERY operation node as a function
4. Enforce ALL preconditions as input validations (raise HTTPException with appropriate error codes)
5. Enforce ALL postconditions as assertions or output validations
6. Preserve ALL global invariants
7. Map BSG edge labels to control flow:
   - sequence → sequential function calls
   - conditional → if/else branching
   - error → exception handling with specific error codes
8. Include error codes matching the legacy system (E001, E002, etc.)
9. Use type hints throughout
10. Add a main FastAPI endpoint: POST /orders/validate-and-submit
11. Use Pydantic v2 syntax only:
- Use constr(pattern=...) NOT constr(regex=...)
- Use conint(ge=..., le=...) NOT conint(0, 10)
- Use condecimal(ge=..., le=...) NOT condecimal(0, 100)
- Use model_validate NOT parse_obj
- Use model_dump NOT dict()
- Use @field_validator (Pydantic V2) NOT @validator (Pydantic V1)
- Do NOT use Pydantic V1 `field=` or `config=` parameters; use `model_config = ConfigDict(...)` if config is needed
- Do not assign new fields to Pydantic request objects after creation; create response dictionaries instead
12. Use standard Python types with Annotated for constraints when possible

## CRITICAL: Behavioral Preservation

- Every business rule referenced in the BSG MUST be enforced in the generated code
- Silent transformations (e.g., priority downgrade) must be preserved exactly
- Conditional exemptions (e.g., tier-based discount limits) must match the BSG spec
- Pricing calculations must produce identical results to the legacy formulas
- Error codes must match exactly

{feedback_section}

## BSG Specification

```json
{bsg_json}
```

## Output

Return ONLY the Python source code. No explanations, no markdown fences.
Start directly with the import statements.
"""

FEEDBACK_SECTION_TEMPLATE = """
## Feedback from Validator (Iteration {iteration})

The previous implementation had the following failures. Fix ALL of them:

{failures}
"""

PATCH_PROMPT = """You are an expert software engineer. You have a Python/FastAPI implementation that
partially works but has some failing tests. Your job is to FIX ONLY the failing parts while
keeping everything that already passes UNCHANGED.

## CRITICAL RULES

1. DO NOT rewrite the entire file from scratch
2. KEEP all passing logic exactly as-is
3. Only modify the specific functions/logic that cause test failures
4. Preserve all imports, class definitions, and endpoint structure
5. Use **Pydantic v2 only**:
   - Use constr(pattern=...) NOT constr(regex=...)
   - Use model_validate NOT parse_obj; use model_dump NOT dict()
   - Use @field_validator (Pydantic v2) NOT @validator (v1)
   - Do NOT use Pydantic v1 `Field(..., field=...)`, `validator=`, or `config=` class parameters;
     use `model_config = ConfigDict(...)` if configuration is needed

## Current Implementation (partially working)

```python
{current_code}
```

## Test Failures to Fix

{failures}

## BSG Specification (for reference)

```json
{bsg_json}
```

## Output

Return the COMPLETE fixed Python file. No explanations, no markdown fences.
Start directly with the import statements.
"""


class ModernizationTransformerAgent(BaseAgent):
    """Generates modern Python/FastAPI implementation from a BSG."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_GENERATION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Modernization Transformer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate modern implementation from BSG.

        Expects state keys:
            - bsg (BehavioralSpecificationGraph): The specification graph.
            - scenario_id (str): Scenario identifier.
            - equiv_report (optional): Previous validation results for feedback.
            - iteration (int): Current feedback loop iteration.

        Adds to state:
            - modern_code (str): Generated Python source code.
        """
        bsg: BehavioralSpecificationGraph = state["bsg"]
        scenario_id = state["scenario_id"]
        iteration = state.get("iteration", 0)

        logger.info(
            "[%s] Generating modern code for scenario %s (iteration %d)",
            self.agent_name,
            scenario_id,
            iteration,
        )

        bsg_json = json.dumps(bsg.to_dict(), indent=2)

        if iteration > 0 and state.get("equiv_report") is not None:
            # INCREMENTAL PATCH: send previous code + failures, ask to fix only broken parts
            equiv_report = state["equiv_report"]
            failures = self._format_failures(equiv_report)
            raw_output = state.get("validator_raw_output", "")
            if raw_output:
                failures += f"\n\n## Raw pytest output:\n```\n{raw_output[:2000]}\n```"

            current_code = state.get("modern_code", "")
            prompt = PATCH_PROMPT.format(
                current_code=current_code,
                failures=failures,
                bsg_json=bsg_json,
            )
            logger.info(
                "[%s] Using incremental patch prompt (preserving passing code)",
                self.agent_name,
            )
        else:
            # FIRST PASS: generate from scratch
            prompt = TRANSFORMER_PROMPT.format(
                bsg_json=bsg_json,
                feedback_section="",
            )

        response = self._invoke_llm(prompt)

        modern_code = self._clean_code_response(response)
        logger.info(
            "[%s] Generated %d lines of modern code",
            self.agent_name,
            modern_code.count("\n") + 1,
        )

        state["modern_code"] = modern_code
        return state

    def _format_failures(self, equiv_report: Any) -> str:
        """Format failed test results into feedback for the LLM."""
        lines = []
        for result in equiv_report.results:
            if not result.passed:
                lines.append(
                    f"- Test {result.test_id} ({result.description}): "
                    f"FAILED — {result.error_message or 'No details'}"
                )
                if result.expected:
                    lines.append(f"  Expected: {result.expected}")
                if result.actual:
                    lines.append(f"  Actual: {result.actual}")
        return "\n".join(lines)

    def _clean_code_response(self, response: str) -> str:
        """Strip markdown fences and fix common LLM code generation issues."""
        text = response.strip()
        if text.startswith("```python"):
            text = text[len("```python") :].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        # Fix Pydantic v1 → v2 incompatibilities (LLMs trained on v1 docs)
        text = text.replace("constr(regex=", "constr(pattern=")
        text = text.replace("conint(ge=", "conint(ge=")
        text = text.replace(".parse_obj(", ".model_validate(")
        text = text.replace(".dict()", ".model_dump()")

        return text
