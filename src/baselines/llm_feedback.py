"""Baseline B3: LLM + iterative test feedback, no BSG (FB-LLM).

Isolates the contribution of the BSG: same model, same feedback loop budget and
patch-style repair as AgentModernize, but no Business Rule Inventory and no BSG.
Code is generated directly from the legacy source; tests are generated from the
legacy source (not from a BSG) and failures are fed back to the generator.
"""

from __future__ import annotations

import logging
from typing import Any

import src.config as config
from src.agents.base import DEFAULT_MODEL, DEFAULT_TEMPERATURE_GENERATION
from src.baselines.single_prompt import SP_PROMPT, SinglePromptBaseline

logger = logging.getLogger(__name__)

FB_TEST_PROMPT = """Generate pytest test cases that verify a Python/FastAPI implementation
preserves the business rules of the legacy COBOL program below.

Use `from main import app` and `from fastapi.testclient import TestClient`.
Pydantic validates BEFORE the endpoint runs: constraint violations return 422, business
rule rejections return the status code the code uses, success returns 200.
Use inputs that pass Pydantic validation but trigger the specific business rule.
Name tests test_<description>. Maximum 15 tests, under 300 lines, syntactically complete.

## Legacy Code

```cobol
{legacy_code}
```

## Implementation

```python
{modern_code}
```

## Output

Return ONLY the Python test code. No explanations, no markdown fences.
"""

FB_PATCH_PROMPT = """You are an expert software engineer. The Python/FastAPI implementation below
partially preserves the behavior of a legacy COBOL program but has failing tests.
Fix ONLY the failing parts and keep everything that passes unchanged. Use Pydantic v2 only.

## Legacy Code

```cobol
{legacy_code}
```

## Current Implementation

```python
{current_code}
```

## Test Failures

{failures}

## Output

Return the COMPLETE fixed Python file. No explanations, no markdown fences.
"""


class LLMFeedbackBaseline(SinglePromptBaseline):
    """Baseline B3: single-prompt generation plus validator feedback, without a BSG."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_GENERATION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "FB-LLM Baseline"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        legacy_code = state["legacy_code"]
        scenario_id = state["scenario_id"]
        logger.info("[%s] Modernizing scenario %s", self.agent_name, scenario_id)

        code = self._clean_code(self._invoke_llm(SP_PROMPT.format(legacy_code=legacy_code)))
        best: tuple[float, str, str, Any] | None = None

        for iteration in range(1, config.MAX_FEEDBACK_ITERATIONS + 1):
            tests = self._clean_code(
                self._invoke_llm(FB_TEST_PROMPT.format(legacy_code=legacy_code, modern_code=code))
            )
            report = self._execute_tests(scenario_id, code, tests)
            rate = report.behavioral_equivalence_rate
            logger.info("[%s] Iteration %d: %.1f%%", self.agent_name, iteration, rate)
            if best is None or rate > best[0]:
                best = (rate, code, tests, report)
            state.update(modern_code=code, modern_tests=tests, equiv_report=report, iteration=iteration)
            if report.all_passed or iteration >= config.MAX_FEEDBACK_ITERATIONS:
                break
            failures = "\n".join(
                f"- {r.test_id}: FAILED — {r.error_message or 'No details'}"
                for r in report.results if not r.passed
            ) + f"\n\n## Raw pytest output:\n```\n{getattr(report, '_raw_output', '')[:2000]}\n```"
            code = self._clean_code(
                self._invoke_llm(
                    FB_PATCH_PROMPT.format(
                        legacy_code=legacy_code, current_code=code, failures=failures
                    )
                )
            )

        if config.REGRESSION_AWARE_FEEDBACK and best is not None and best[0] > state["equiv_report"].behavioral_equivalence_rate:
            _, state["modern_code"], state["modern_tests"], state["equiv_report"] = best
        return state
