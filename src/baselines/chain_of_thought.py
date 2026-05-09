"""Baseline B2: Chain-of-Thought LLM (CoT-LLM).

Uses a single LLM call with chain-of-thought instructions: "First analyze
the business rules, then design the API, then implement it." Still a single
model call, but with structured reasoning.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_GENERATION
from src.models.equivalence_report import (
    BehavioralEquivalenceReport,
    TestResult,
    TestStatus,
)

logger = logging.getLogger(__name__)

COT_PROMPT = """You are a software engineer modernizing legacy telecom systems.

Convert the following legacy COBOL code into a modern Python/FastAPI API.

Follow these steps IN ORDER (show your reasoning for each step):

### Step 1: Analyze Business Rules
First, identify ALL business rules in the legacy code. List each rule with:
- Rule ID (BR-001, BR-002, etc.)
- Description
- Whether it's explicit or implicit

### Step 2: Design the Modern API
Design the FastAPI endpoint structure:
- Pydantic v2 request/response models
- Validation logic for each business rule
- Error handling strategy

### Step 3: Implement
Generate the complete Python/FastAPI implementation.

Requirements:
1. Use Pydantic v2 models (constr(pattern=...) NOT constr(regex=...))
2. POST /orders/validate-and-submit endpoint
3. Preserve ALL business rules from Step 1
4. Include proper error codes (E001, E002, etc.)
5. Type hints throughout

## Legacy Code

```cobol
{legacy_code}
```

## Output Format

After your analysis, output the FINAL Python code between these markers:
===FINAL_CODE_START===
[your complete Python file here]
===FINAL_CODE_END===
"""

COT_TEST_PROMPT = """Generate pytest test cases for the following Python/FastAPI implementation.
Test ALL business rules and edge cases visible in the code.

Use `from main import app` to import the FastAPI app, and `from fastapi.testclient import TestClient`.

## CRITICAL: Pydantic validates BEFORE the endpoint runs.
- If the model uses constr/conint constraints, invalid inputs return 422, NOT 400.
- Test BUSINESS LOGIC by using inputs that pass Pydantic validation but trigger business rules.
- Read the code carefully to determine the actual response format and status codes.

## Implementation

```python
{modern_code}
```

## Output

Return ONLY the Python test code. No explanations, no markdown fences.
Start directly with the import statements.
"""


class ChainOfThoughtBaseline(BaseAgent):
    """Baseline B2: Chain-of-thought LLM modernization."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_GENERATION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "CoT-LLM Baseline"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Run chain-of-thought modernization.

        Expects state keys:
            - legacy_code (str): The legacy COBOL source code.
            - scenario_id (str): Scenario identifier.

        Adds to state:
            - modern_code (str): Generated Python source code.
            - cot_reasoning (str): The full CoT reasoning trace.
            - modern_tests (str): Generated test code.
            - equiv_report (BehavioralEquivalenceReport): Test results.
        """
        legacy_code = state["legacy_code"]
        scenario_id = state["scenario_id"]

        logger.info("[%s] Modernizing scenario %s", self.agent_name, scenario_id)

        # Step 1: Generate with chain-of-thought reasoning
        prompt = COT_PROMPT.format(legacy_code=legacy_code)
        response = self._invoke_llm(prompt)
        state["cot_reasoning"] = response

        # Extract code from between markers
        modern_code = self._extract_code(response)
        state["modern_code"] = modern_code

        logger.info(
            "[%s] Generated %d lines of modern code",
            self.agent_name,
            modern_code.count("\n") + 1,
        )

        # Step 2: Generate tests
        test_prompt = COT_TEST_PROMPT.format(modern_code=modern_code)
        test_response = self._invoke_llm(test_prompt)
        test_code = self._clean_code(test_response)
        state["modern_tests"] = test_code

        # Step 3: Execute tests
        report = self._execute_tests(scenario_id, modern_code, test_code)
        state["equiv_report"] = report
        state["iteration"] = 1

        logger.info(
            "[%s] Equivalence rate: %.1f%% (%d/%d passed)",
            self.agent_name,
            report.behavioral_equivalence_rate,
            report.passed_tests,
            report.total_tests,
        )

        return state

    def _extract_code(self, response: str) -> str:
        """Extract code from between ===FINAL_CODE_START=== and ===FINAL_CODE_END=== markers."""
        start_marker = "===FINAL_CODE_START==="
        end_marker = "===FINAL_CODE_END==="

        if start_marker in response and end_marker in response:
            code = response.split(start_marker)[1].split(end_marker)[0].strip()
        else:
            # Fallback: try to extract code from markdown fences
            code = self._clean_code(response)

        # Apply Pydantic v2 fixes
        code = code.replace("constr(regex=", "constr(pattern=")
        code = code.replace(".parse_obj(", ".model_validate(")
        code = code.replace(".dict()", ".model_dump()")

        return code

    def _execute_tests(
        self,
        scenario_id: str,
        modern_code: str,
        test_code: str,
    ) -> BehavioralEquivalenceReport:
        """Write code + tests to temp files and run pytest."""
        with tempfile.TemporaryDirectory(prefix="cot_llm_") as tmpdir:
            tmp_path = Path(tmpdir)

            (tmp_path / "main.py").write_text(modern_code)

            fixed_test_code = test_code
            for old_import in ["from modern_service", "from app", "from service"]:
                fixed_test_code = fixed_test_code.replace(old_import, "from main")

            test_file = tmp_path / "test_equivalence.py"
            path_fix = f"import sys\nsys.path.insert(0, '{tmpdir}')\n"
            test_file.write_text(path_fix + fixed_test_code)

            result = subprocess.run(
                [
                    sys.executable, "-m", "pytest",
                    str(test_file),
                    "-v",
                    "--tb=short",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=120,
            )

            return self._parse_pytest_output(scenario_id, result)

    def _parse_pytest_output(
        self,
        scenario_id: str,
        result: subprocess.CompletedProcess,
    ) -> BehavioralEquivalenceReport:
        """Parse pytest verbose output into structured test results."""
        results = []
        output = result.stdout + result.stderr

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            if " PASSED" in line or " FAILED" in line or " ERROR" in line:
                test_name = line.split("::")[1].split(" ")[0] if "::" in line else line
                if " PASSED" in line:
                    status = TestStatus.PASS
                elif " FAILED" in line:
                    status = TestStatus.FAIL
                else:
                    status = TestStatus.ERROR

                rule_ids = []
                parts = test_name.upper().split("_")
                for part in parts:
                    if part.startswith("BR") and len(part) >= 4:
                        rule_ids.append(f"{part[:2]}-{part[2:]}")

                results.append(
                    TestResult(
                        test_id=test_name,
                        description=test_name.replace("test_", "").replace("_", " "),
                        status=status,
                        bsg_node_id="",
                        business_rule_ids=rule_ids,
                        error_message=None if status == TestStatus.PASS else line,
                    )
                )

        if not results:
            overall_status = TestStatus.PASS if result.returncode == 0 else TestStatus.FAIL
            results.append(
                TestResult(
                    test_id="overall",
                    description="Overall test execution",
                    status=overall_status,
                    bsg_node_id="",
                    error_message=output[:500] if overall_status != TestStatus.PASS else None,
                )
            )

        report = BehavioralEquivalenceReport(
            scenario_id=scenario_id,
            results=results,
        )
        report._raw_output = output  # type: ignore[attr-defined]
        return report

    def _clean_code(self, response: str) -> str:
        """Strip markdown fences and fix Pydantic v1 issues."""
        text = response.strip()
        if text.startswith("```python"):
            text = text[len("```python"):].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        text = text.replace("constr(regex=", "constr(pattern=")
        text = text.replace(".parse_obj(", ".model_validate(")
        text = text.replace(".dict()", ".model_dump()")

        return text
