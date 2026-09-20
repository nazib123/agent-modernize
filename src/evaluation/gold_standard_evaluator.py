"""Gold-Standard Evaluator — fair comparison of all methods.

Instead of letting each method generate its own tests (which creates an unfair
comparison), this evaluator generates tests from the gold_standard.json test
scenarios. Every method is tested against the SAME set of business-rule checks.

Usage:
    evaluator = GoldStandardEvaluator()
    report = evaluator.evaluate(scenario_id, modern_code, gold_standard)
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent, DEFAULT_MODEL, DEFAULT_TEMPERATURE_EXTRACTION
from src.models.equivalence_report import (
    BehavioralEquivalenceReport,
    TestResult,
    TestStatus,
)

logger = logging.getLogger(__name__)

GOLD_STANDARD_TEST_PROMPT = """You are an expert QA engineer. Generate pytest test cases that verify
whether a modernized Python/FastAPI implementation correctly preserves business rules
defined in a gold-standard specification.

## CRITICAL RULES

1. Generate EXACTLY ONE test function per test scenario listed below.
2. Name each test: test_<scenario_id>_<brief_description>  (e.g., test_T001_happy_path)
3. Use `from main import app` and `from fastapi.testclient import TestClient`.
4. Pydantic validates BEFORE the endpoint runs:
   - Type/constraint violations → 422
   - Business logic errors (HTTPException) → 400 (or whatever status the code uses)
   - Successful processing → 200
5. Use VALID inputs that pass Pydantic but test the specific business rule.
6. Read the modern code carefully to determine:
   - The actual endpoint path and HTTP method
   - The exact request body structure (field names, types)
   - The response format (JSON structure, status codes, error detail format)
7. For each test, add a comment with the rule IDs being tested (e.g., # Tests: BR-001)
8. Do NOT add extra tests beyond the listed scenarios.

## STRICT IMPORT AND TYPE RULES (VIOLATION = INVALID OUTPUT)

- The test file MUST import ONLY from these modules, plus `main`:
  `pytest`, `fastapi.testclient`, `decimal.Decimal`, `datetime`, `json`.
- NEVER use pydantic constraint types in tests: no `condecimal`, `conint`, `constr`,
  `confloat`, `conlist`, `conset`, `conbytes`, `condate`.
- NEVER redefine or re-import pydantic models (`BaseModel`, request/response schemas)
  that already exist in the modernized code. Pass request bodies as plain `dict`
  literals in `client.post(url, json={{...}})`.
- If a numeric field requires precise arithmetic, use plain `float` in the JSON body
  or `Decimal("...")` for local comparisons — never a pydantic constraint type.
- Do NOT define helper Pydantic classes, fixtures with pydantic models, or extra
  utility functions. Keep the file to imports + test functions only.
- Start the file with EXACTLY these imports (add more only if strictly needed):

      import pytest
      from decimal import Decimal
      from datetime import date, datetime
      from fastapi.testclient import TestClient
      from main import app

      client = TestClient(app)

## Modern Code to Test

```python
{modern_code}
```

## Business Rules (Source of Truth)

```json
{rules_json}
```

## Data Constraints

```json
{constraints_json}
```

## Test Scenarios to Implement

{test_scenarios_text}

## Output

Return ONLY the Python test file. No explanations, no markdown fences.
Start with import statements.
"""

# Maximum number of LLM retries for test generation
MAX_TEST_GEN_RETRIES = 3

# Temperature 0.0 for deterministic, reliable test generation
TEST_GEN_TEMPERATURE = 0.0


class GoldStandardEvaluator(BaseAgent):
    """Evaluates any modernization method against gold-standard test scenarios."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = TEST_GEN_TEMPERATURE,
    ) -> None:
        super().__init__(model_name=model_name, temperature=temperature)

    @property
    def agent_name(self) -> str:
        return "Gold Standard Evaluator"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Not used directly — use evaluate() instead."""
        raise NotImplementedError("Use evaluate() for gold-standard evaluation")

    def evaluate(
        self,
        scenario_id: str,
        modern_code: str,
        gold_standard: dict[str, Any],
    ) -> BehavioralEquivalenceReport:
        """Evaluate modern code against gold-standard test scenarios.

        Args:
            scenario_id: Scenario identifier (e.g., "S1").
            modern_code: The generated Python/FastAPI code to evaluate.
            gold_standard: Parsed gold_standard.json dict.

        Returns:
            BehavioralEquivalenceReport with one result per gold-standard test.
        """
        rules = gold_standard.get("rules", [])
        constraints = gold_standard.get("constraints", [])
        test_scenarios = gold_standard.get("test_scenarios", [])

        if not test_scenarios:
            logger.warning(
                "[%s] No test scenarios in gold standard for %s",
                self.agent_name,
                scenario_id,
            )
            return BehavioralEquivalenceReport(scenario_id=scenario_id)

        logger.info(
            "[%s] Evaluating %s with %d gold-standard tests",
            self.agent_name,
            scenario_id,
            len(test_scenarios),
        )

        test_scenarios_text = self._format_test_scenarios(test_scenarios)
        rules_json = json.dumps(rules, indent=2)
        constraints_json = json.dumps(constraints, indent=2)

        prompt = GOLD_STANDARD_TEST_PROMPT.format(
            modern_code=modern_code,
            rules_json=rules_json,
            constraints_json=constraints_json,
            test_scenarios_text=test_scenarios_text,
        )

        test_code = self._generate_tests_with_retry(prompt)
        report = self._execute_tests(scenario_id, modern_code, test_code)

        logger.info(
            "[%s] %s: %.1f%% BER (%d/%d passed)",
            self.agent_name,
            scenario_id,
            report.behavioral_equivalence_rate,
            report.passed_tests,
            report.total_tests,
        )

        return report

    def generate_test_code(
        self,
        scenario_id: str,
        reference_code: str,
        gold_standard: dict[str, Any],
    ) -> str | None:
        """Generate test code once from gold standard + reference implementation.

        Args:
            scenario_id: Scenario identifier (e.g., "S1").
            reference_code: A reference modern code (typically AM) to learn the API shape.
            gold_standard: Parsed gold_standard.json dict.

        Returns:
            Generated pytest test code string, or None on failure.
        """
        rules = gold_standard.get("rules", [])
        constraints = gold_standard.get("constraints", [])
        test_scenarios = gold_standard.get("test_scenarios", [])

        if not test_scenarios:
            logger.warning("[%s] No test scenarios for %s", self.agent_name, scenario_id)
            return None

        test_scenarios_text = self._format_test_scenarios(test_scenarios)
        rules_json = json.dumps(rules, indent=2)
        constraints_json = json.dumps(constraints, indent=2)

        prompt = GOLD_STANDARD_TEST_PROMPT.format(
            modern_code=reference_code,
            rules_json=rules_json,
            constraints_json=constraints_json,
            test_scenarios_text=test_scenarios_text,
        )

        try:
            return self._generate_tests_with_retry(prompt)
        except (ValueError, RuntimeError):
            logger.exception("[%s] Failed to generate tests for %s", self.agent_name, scenario_id)
            return None

    def evaluate_with_tests(
        self,
        scenario_id: str,
        modern_code: str,
        test_code: str,
    ) -> BehavioralEquivalenceReport:
        """Evaluate modern code using pre-generated test code (no LLM call).

        Args:
            scenario_id: Scenario identifier.
            modern_code: The generated code to evaluate.
            test_code: Pre-generated pytest test code.

        Returns:
            BehavioralEquivalenceReport.
        """
        report = self._execute_tests(scenario_id, modern_code, test_code)

        logger.info(
            "[%s] %s: %.1f%% BER (%d/%d passed)",
            self.agent_name,
            scenario_id,
            report.behavioral_equivalence_rate,
            report.passed_tests,
            report.total_tests,
        )

        return report

    def _format_test_scenarios(self, test_scenarios: list[dict]) -> str:
        """Format gold-standard test scenarios into a numbered list for the prompt."""
        lines = []
        for ts in test_scenarios:
            tid = ts["id"]
            desc = ts["description"]
            # Handle both S1 format (expected_result) and S2-S7 format (expected)
            expected = ts.get("expected_result") or ts.get("expected", "")
            rules = ", ".join(
                ts.get("tests_rules", []) or ts.get("rules_tested", [])
            )
            error = ts.get("expected_error", "")
            test_input = ts.get("input", {})

            entry = f"- **{tid}**: {desc}\n"
            if test_input:
                entry += f"  Input: {json.dumps(test_input)}\n"
            entry += f"  Expected: {expected}"
            if error:
                entry += f" (error code: {error})"
            entry += f"\n  Tests rules: {rules}"
            lines.append(entry)

        return "\n".join(lines)

    def _sanitize_test_code(self, test_code: str) -> str:
        """Post-hoc fix pass for the most common LLM test-gen mistakes.

        Replaces pydantic constraint constructors with plain types, ensures the
        required imports are present, and strips duplicated pydantic model
        redefinitions that would shadow `main.py`'s originals.
        """
        code = test_code

        # 1. Replace pydantic constraint type constructors with plain equivalents.
        replacements = [
            (r"condecimal\([^)]*\)", "Decimal"),
            (r"conint\([^)]*\)", "int"),
            (r"confloat\([^)]*\)", "float"),
            (r"constr\([^)]*\)", "str"),
            (r"conlist\([^)]*\)", "list"),
            (r"conset\([^)]*\)", "set"),
            (r"conbytes\([^)]*\)", "bytes"),
        ]
        for pat, repl in replacements:
            code = re.sub(pat, repl, code)

        # 1-bis. Convert byte-string literals b"..." / b'...' to plain strings.
        # The LLM generates these when the reference code uses bytes fields.
        code = re.sub(r'\bb"([^"]*)"', r'"\1"', code)
        code = re.sub(r"\bb'([^']*)'", r"'\1'", code)
        # Also handle b"..." + b"..." concatenation → "..." + "..."
        code = re.sub(r'\bb"', '"', code)
        code = re.sub(r"\bb'", "'", code)

        # 1a. Fix a common LLM mistake: calling `.isoformat()` on a string
        # literal that is already ISO-8601. Drop the `.isoformat()` call.
        code = re.sub(
            r'"(\d{4}-\d{2}-\d{2}(?:T[\d:.+-]+)?)"\s*\.\s*isoformat\s*\(\s*\)',
            r'"\1"',
            code,
        )
        code = re.sub(
            r"'(\d{4}-\d{2}-\d{2}(?:T[\d:.+-]+)?)'\s*\.\s*isoformat\s*\(\s*\)",
            r"'\1'",
            code,
        )

        # 1b. Fix another common LLM mistake: calling `.isoformat()` on a
        # numeric literal or int (LLM confuses "amount" and "date" fields).
        code = re.sub(
            r"(\d+(?:\.\d+)?)\s*\.\s*isoformat\s*\(\s*\)",
            r"\1",
            code,
        )

        # 2. Guarantee critical imports at the top (idempotent). We only append
        # imports that are referenced but missing.
        needed_imports = []
        if "Decimal" in code and "from decimal import" not in code:
            needed_imports.append("from decimal import Decimal")
        if re.search(r"\b(date|datetime)\b", code) and "from datetime import" not in code:
            needed_imports.append("from datetime import date, datetime")
        if "TestClient" in code and "from fastapi.testclient import TestClient" not in code:
            needed_imports.append("from fastapi.testclient import TestClient")
        if "from main import" not in code and "import main" not in code:
            needed_imports.append("from main import app")
        if needed_imports:
            code = "\n".join(needed_imports) + "\n" + code

        # 3. Strip pydantic model redefinitions that shadow main.py types.
        # Any "class Foo(BaseModel):" block — pop it out. We look for the class
        # header and drop lines until the next non-indented, non-blank line.
        cleaned_lines: list[str] = []
        skip = False
        for line in code.splitlines():
            if re.match(r"^class \w+\(BaseModel\)\s*:", line):
                skip = True
                continue
            if skip:
                if line and not line.startswith((" ", "\t")):
                    skip = False
                else:
                    continue
            cleaned_lines.append(line)
        code = "\n".join(cleaned_lines)

        return code

    def _collect_only_ok(self, test_code: str) -> tuple[bool, str]:
        """Run `pytest --collect-only` in an isolated tempdir with a stub main.

        Returns (ok, stderr_or_stdout_tail). This catches import/name errors
        before we waste a real evaluation run.
        """
        with tempfile.TemporaryDirectory(prefix="collect_check_") as tmpdir:
            tmp_path = Path(tmpdir)
            # Minimal stub so `from main import app` succeeds during collection.
            stub = (
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
            )
            (tmp_path / "main.py").write_text(stub)
            test_file = tmp_path / "test_collect_check.py"
            test_file.write_text(
                f"import sys\nsys.path.insert(0, r'{tmpdir}')\n" + test_code
            )
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "--collect-only", "-q"],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=30,
            )
            if proc.returncode == 0:
                return True, ""
            return False, (proc.stdout + "\n" + proc.stderr)[-1500:]

    def _generate_tests_with_retry(self, prompt: str) -> str:
        """Generate test code, retrying if the LLM output is malformed or has syntax errors."""
        test_code = ""
        last_error = ""
        for attempt in range(MAX_TEST_GEN_RETRIES):
            effective_prompt = prompt
            if last_error and attempt > 0:
                effective_prompt = (
                    prompt
                    + "\n\n## PREVIOUS ATTEMPT FAILED\n"
                    "pytest could not collect the previous test file. Fix the errors below\n"
                    "and RE-EMIT the complete test file. Do NOT use condecimal/conint/etc.\n\n"
                    + last_error
                )
            response = self._invoke_llm(effective_prompt)
            test_code = self._clean_code(response)
            test_code = self._sanitize_test_code(test_code)

            if "def test_" not in test_code or "import" not in test_code:
                logger.warning(
                    "[%s] Attempt %d: generated code missing test functions, retrying",
                    self.agent_name,
                    attempt + 1,
                )
                last_error = "missing 'def test_' or import statements"
                continue

            try:
                compile(test_code, "<test>", "exec")
            except SyntaxError as exc:
                logger.warning(
                    "[%s] Attempt %d: syntax error: %s, retrying",
                    self.agent_name,
                    attempt + 1,
                    exc,
                )
                last_error = f"SyntaxError: {exc}"
                continue

            ok, err_tail = self._collect_only_ok(test_code)
            if ok:
                return test_code

            logger.warning(
                "[%s] Attempt %d: pytest --collect-only failed, retrying",
                self.agent_name,
                attempt + 1,
            )
            last_error = err_tail

        return test_code

    def _execute_tests(
        self,
        scenario_id: str,
        modern_code: str,
        test_code: str,
    ) -> BehavioralEquivalenceReport:
        """Write code + tests to temp files and run pytest."""
        with tempfile.TemporaryDirectory(prefix="gold_eval_") as tmpdir:
            tmp_path = Path(tmpdir)

            # Fix common Decimal/float incompatibility in LLM-generated code
            patched_code = self._patch_decimal_issues(modern_code)
            (tmp_path / "main.py").write_text(patched_code)

            fixed_test_code = test_code
            for old_import in ["from modern_service", "from app", "from service"]:
                fixed_test_code = fixed_test_code.replace(old_import, "from main")

            test_file = tmp_path / "test_gold_standard.py"
            path_fix = f"import sys\nsys.path.insert(0, r'{tmpdir}')\n"
            test_file.write_text(path_fix + fixed_test_code)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
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

            logger.info(
                "[%s] pytest stdout:\n%s", self.agent_name, result.stdout[-3000:]
            )
            if result.returncode != 0:
                logger.info(
                    "[%s] pytest stderr:\n%s", self.agent_name, result.stderr[-1500:]
                )
            # Save debug artifacts
            debug_dir = Path("results") / f"{scenario_id}_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "generated_tests.py").write_text(test_code)
            (debug_dir / "patched_main.py").write_text(
                (tmp_path / "main.py").read_text()
            )
            (debug_dir / "pytest_output.txt").write_text(
                result.stdout + "\n---STDERR---\n" + result.stderr
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
                test_name = (
                    line.split("::")[1].split(" ")[0] if "::" in line else line
                )
                if " PASSED" in line:
                    status = TestStatus.PASS
                elif " FAILED" in line:
                    status = TestStatus.FAIL
                else:
                    status = TestStatus.ERROR

                rule_ids = self._extract_rule_ids(test_name)

                results.append(
                    TestResult(
                        test_id=test_name,
                        description=test_name.replace("test_", "").replace("_", " "),
                        status=status,
                        bsg_node_id="",
                        business_rule_ids=rule_ids,
                        error_message=(
                            None if status == TestStatus.PASS else line
                        ),
                    )
                )

        if not results:
            overall_status = (
                TestStatus.PASS if result.returncode == 0 else TestStatus.FAIL
            )
            results.append(
                TestResult(
                    test_id="overall",
                    description="Overall test execution",
                    status=overall_status,
                    bsg_node_id="",
                    error_message=(
                        output[:500] if overall_status != TestStatus.PASS else None
                    ),
                )
            )

        report = BehavioralEquivalenceReport(
            scenario_id=scenario_id,
            results=results,
        )
        report._raw_output = output  # type: ignore[attr-defined]
        return report

    @staticmethod
    def _extract_rule_ids(test_name: str) -> list[str]:
        """Extract rule IDs (BR-xxx, DC-xxx) from test function name."""
        rule_ids = []
        parts = test_name.upper().split("_")
        for part in parts:
            if part.startswith("BR") and len(part) >= 4:
                rule_ids.append(f"{part[:2]}-{part[2:]}")
            elif part.startswith("DC") and len(part) >= 4:
                rule_ids.append(f"{part[:2]}-{part[2:]}")
            elif part.startswith("T") and len(part) >= 4 and part[1:].isdigit():
                rule_ids.append(part)
        return rule_ids

    @staticmethod
    def _patch_decimal_issues(code: str) -> str:
        """Patch Decimal/float incompatibility in LLM-generated FastAPI code.

        LLM-generated code often uses condecimal() in Pydantic models but
        float type hints in helper functions. When Pydantic passes Decimal
        objects to float-typed functions, Python raises TypeError.

        Fix: replace condecimal(...) with float in Pydantic models so that
        all values are plain floats throughout the code.
        """
        # Strip markdown fences that some saved code files still contain
        patched = code.strip()
        if patched.startswith("```python"):
            patched = patched[len("```python"):].strip()
        elif patched.startswith("```"):
            patched = patched[3:].strip()
        if patched.endswith("```"):
            patched = patched[:-3].strip()

        # 1. Constraint constructors with args -> plain types.
        # Use .*? with re.DOTALL to handle nested parens inside patterns
        # like constr(pattern='^(NEW|MOD|DIS)$').
        constraint_names = [
            ("condecimal", "float"),
            ("confloat", "float"),
            ("conint", "int"),
            ("constr", "str"),
            ("conlist", "list"),
            ("conset", "set"),
            ("conbytes", "bytes"),
        ]
        for cname, repl in constraint_names:
            # Match the constraint call including nested parens (one level deep)
            # e.g. constr(pattern='^(NEW|MOD|DIS)$') — must NOT eat past the
            # matching closing paren or we'll break surrounding syntax like
            # Optional[constr(...)].
            patched = re.sub(
                rf"\b{cname}\s*\((?:[^()]*\([^()]*\))*[^()]*\)",
                repl,
                patched,
            )

        bare_map = {
            "condecimal": "float",
            "confloat": "float",
            "conint": "int",
            "constr": "str",
            "conlist": "list",
            "conset": "set",
            "conbytes": "bytes",
        }

        # Names the LLM incorrectly imports from pydantic (they are
        # BaseModel class methods/attributes, not standalone exports).
        invalid_pydantic_imports = {
            "model_validate", "model_config", "model_dump",
            "model_json_schema", "model_fields",
        }

        # Combined set of names to strip from pydantic import lines.
        strip_names = set(bare_map.keys()) | invalid_pydantic_imports

        # 2. Clean up any pydantic import lines FIRST (before bare substitution
        # can turn `constr` into `str` inside an import list).
        def _strip_constraint_imports(match: re.Match) -> str:
            prefix, names, suffix = match.group(1), match.group(2), match.group(3)
            kept = [
                n.strip()
                for n in names.split(",")
                if n.strip() and n.strip() not in strip_names
            ]
            if not kept:
                return ""
            return f"{prefix}{', '.join(kept)}{suffix}"

        patched = re.sub(
            r"(from\s+pydantic\s+import\s+)([^\n]+)(\n)",
            _strip_constraint_imports,
            patched,
        )

        # 3. Fix `field: type = constr(...)` → `field: type` (remove the
        #    constraint-as-default that step 1 turned into `field: type = str`).
        for repl_type in set(r for _, r in constraint_names):
            patched = re.sub(
                rf"(:\s*\w+)\s*=\s*{repl_type}(?=\s*$|\s*#)",
                r"\1",
                patched,
                flags=re.MULTILINE,
            )

        # 3b. Simplify Annotated[T, constr/conint/...] → T (constraint was
        #     already replaced with a bare type name by step 1).
        for repl_type in set(r for _, r in constraint_names):
            patched = re.sub(
                rf"Annotated\[(\w+),\s*{repl_type}\]",
                r"\1",
                patched,
            )

        # 3c. Bare references without parens elsewhere (e.g., Optional[condecimal]).
        for name, repl in bare_map.items():
            patched = re.sub(rf"\b{name}\b", repl, patched)

        # 4. Replace `bytes` type annotations with `str` in Pydantic model fields
        # so generated tests use JSON-serializable strings instead of b"..." literals.
        patched = re.sub(r":\s*bytes\b", ": str", patched)

        # 5. Strip `.decode(...)` calls — after bytes→str the values are already
        # strings, so `.decode('ascii')` etc. would raise AttributeError.
        patched = re.sub(r"\.decode\s*\([^)]*\)", "", patched)

        # 6. Strip `.encode(...)` calls on string fields being written to bytes
        # buffers — no longer needed after bytes→str conversion.
        patched = re.sub(r"\.encode\s*\([^)]*\)", "", patched)

        # 7. Replace deprecated @validator with @field_validator (Pydantic v2).
        patched = re.sub(
            r"@validator\(([^)]+),\s*always=True\)",
            r"@field_validator(\1, mode='before')",
            patched,
        )
        patched = re.sub(
            r"@validator\(([^)]+)\)",
            r"@field_validator(\1, mode='before')",
            patched,
        )
        # Add field_validator import if we added it and it's missing
        if "@field_validator" in patched and "field_validator" not in patched.split("\n")[0:10].__repr__():
            patched = re.sub(
                r"(from\s+pydantic\s+import\s+)([^\n]+)",
                lambda m: m.group(0) if "field_validator" in m.group(2) else f"{m.group(1)}{m.group(2)}, field_validator",
                patched,
                count=1,
            )

        return patched

    @staticmethod
    def _clean_code(response: str) -> str:
        """Strip markdown fences and fix common LLM-generated test issues."""
        text = response.strip()
        if text.startswith("```python"):
            text = text[len("```python") :].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        text = text.replace("constr(regex=", "constr(pattern=")
        text = text.replace(".parse_obj(", ".model_validate(")
        text = text.replace(".dict()", ".model_dump()")

        # Fix: LLM wraps values in Decimal() which isn't JSON-serializable
        text = re.sub(r'Decimal\("([^"]+)"\)', r'\1', text)
        text = re.sub(r"Decimal\('([^']+)'\)", r'\1', text)
        text = re.sub(r'Decimal\((\d+\.?\d*)\)', r'\1', text)

        # Fix: LLM uses date/datetime objects which aren't JSON-serializable
        text = re.sub(r"datetime\.date\.today\(\)", '"2026-05-15"', text)
        text = re.sub(r"date\.today\(\)", '"2026-05-15"', text)
        text = re.sub(
            r"datetime\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)",
            lambda m: f'"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"',
            text,
        )
        # Fix: LLM uses timedelta arithmetic on date strings — simplify to a date string
        text = re.sub(
            r'"(\d{4}-\d{2}-\d{2})"\s*\+\s*datetime\.timedelta\([^)]*\)',
            '"2026-05-20"',
            text,
        )
        text = re.sub(
            r'"(\d{4}-\d{2}-\d{2})"\s*-\s*datetime\.timedelta\([^)]*\)',
            '"2026-05-10"',
            text,
        )

        # Remove unused Decimal import if we stripped all usages
        if "Decimal" not in text.split("import")[-1]:
            text = re.sub(r"from decimal import Decimal\n?", "", text)
            text = re.sub(r"import decimal\n?", "", text)

        return text
