"""Agent 4: Equivalence Validator — verifies behavioral preservation.

Takes the BSG specification and generated modern code, generates test cases,
executes them, and produces a Behavioral Equivalence Report (BER).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_EXTRACTION
from src.models.bsg import BehavioralSpecificationGraph
from src.models.equivalence_report import (
    BehavioralEquivalenceReport,
    TestResult,
    TestStatus,
)

logger = logging.getLogger(__name__)

VALIDATOR_PROMPT = """You are an expert QA engineer specializing in behavioral equivalence
testing for modernized FastAPI/Pydantic systems. Generate pytest test cases that verify
the modern implementation preserves all business rules from the BSG specification.

## CRITICAL: FastAPI/Pydantic Testing Rules

1. **Pydantic validates BEFORE the endpoint runs.** If the Pydantic model uses `constr`,
   `conint`, etc., invalid inputs return HTTP 422 (not 400 or 200).
2. **Test for the ACTUAL status codes the code produces:**
   - Pydantic type/constraint violations → 422
   - Business logic errors (HTTPException) → 400 or the code's status_code
   - Successful processing → 200
3. **Use VALID inputs that pass Pydantic but test business logic.** For example, if
   `order_type: constr(pattern='^(NEW|DIS|MOD)$')`, don't test with "INVALID" — that
   gives 422 from Pydantic, not a business logic error.
4. **Read the code carefully** to determine what response format is returned (JSON body
   structure, error detail format, etc.).

## Test Case Structure

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_BR001_example():
    response = client.post("/orders/validate-and-submit", json={{...}})
    # Check the actual status code the code returns
    assert response.status_code == <expected>
    # Check response body matches expected behavior
```

## Naming Convention: test_<rule_id>_<description>

## The Modernized Code to Test

```python
{modern_code}
```

## BSG Specification (Source of Truth)

```json
{bsg_json}
```

## Output

Return ONLY the Python test file. No explanations, no markdown fences.
Start with import statements. Include at least one test per business rule.
Focus on testing BUSINESS LOGIC, not Pydantic schema validation.
"""


class EquivalenceValidatorAgent(BaseAgent):
    """Generates and executes equivalence tests against modern code."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_EXTRACTION,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Equivalence Validator"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate tests, execute them, and produce equivalence report.

        Expects state keys:
            - bsg (BehavioralSpecificationGraph): Specification graph.
            - modern_code (str): Generated Python implementation.
            - scenario_id (str): Scenario identifier.

        Adds to state:
            - modern_tests (str): Generated test code.
            - equiv_report (BehavioralEquivalenceReport): Test results.
        """
        bsg: BehavioralSpecificationGraph = state["bsg"]
        modern_code: str = state["modern_code"]
        scenario_id = state["scenario_id"]

        logger.info("[%s] Validating scenario %s", self.agent_name, scenario_id)

        # Step 1: Generate test cases
        tests = self._generate_tests(bsg, modern_code)
        state["modern_tests"] = tests

        # Step 2: Execute tests
        report = self._execute_tests(scenario_id, modern_code, tests)

        logger.info(
            "[%s] Equivalence rate: %.1f%% (%d/%d passed)",
            self.agent_name,
            report.behavioral_equivalence_rate,
            report.passed_tests,
            report.total_tests,
        )

        state["equiv_report"] = report
        state["validator_raw_output"] = getattr(report, "_raw_output", "")
        return state

    def _generate_tests(self, bsg: BehavioralSpecificationGraph, modern_code: str) -> str:
        """Use LLM to generate pytest test cases."""
        bsg_json = json.dumps(bsg.to_dict(), indent=2)
        prompt = VALIDATOR_PROMPT.format(
            modern_code=modern_code,
            bsg_json=bsg_json,
        )
        response = self._invoke_llm(prompt)
        return self._clean_code_response(response)

    def _execute_tests(
        self,
        scenario_id: str,
        modern_code: str,
        test_code: str,
    ) -> BehavioralEquivalenceReport:
        """Write code + tests to temp files and run pytest."""
        with tempfile.TemporaryDirectory(prefix="agentmod_") as tmpdir:
            tmp_path = Path(tmpdir)

            # Write the modernized code as main.py (LLMs typically import from main)
            code_file = tmp_path / "main.py"
            code_file.write_text(modern_code)

            # Normalize imports in test code to match our file name
            fixed_test_code = test_code
            for old_import in ["from modern_service", "from app", "from service"]:
                fixed_test_code = fixed_test_code.replace(old_import, "from main")

            # Write the test file with sys.path fix
            test_file = tmp_path / "test_equivalence.py"
            path_fix = f"import sys\nsys.path.insert(0, {tmpdir!r})\n"
            test_file.write_text(path_fix + fixed_test_code)

            # Find the python binary (prefer venv)
            python_bin = sys.executable

            # Run pytest
            result = subprocess.run(
                [
                    python_bin, "-m", "pytest",
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

            logger.info("[%s] pytest stdout:\n%s", self.agent_name, result.stdout[-2000:])
            logger.info("[%s] pytest stderr:\n%s", self.agent_name, result.stderr[-2000:])
            logger.info("[%s] pytest exit code: %d", self.agent_name, result.returncode)

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

                # Extract rule IDs from test name (convention: test_BR001_...)
                rule_ids = []
                parts = test_name.upper().split("_")
                for part in parts:
                    if part.startswith("BR") and len(part) >= 4:
                        rule_ids.append(f"{part[:2]}-{part[2:]}")
                    elif part.startswith("DC") and len(part) >= 4:
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

        # If no individual test results parsed, create a summary result
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

    def _clean_code_response(self, response: str) -> str:
        """Strip markdown fences if present."""
        text = response.strip()
        if text.startswith("```python"):
            text = text[len("```python") :].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text
