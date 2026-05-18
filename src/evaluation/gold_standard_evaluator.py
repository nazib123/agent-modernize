"""Gold-Standard Evaluator — fair comparison of all methods.

Instead of letting each method generate its own tests (which creates an unfair
comparison), this evaluator generates tests from the gold_standard.json test
scenarios. Every method is tested against the SAME set of business-rule checks.

Usage:
    evaluator = GoldStandardEvaluator()
    report = evaluator.evaluate(scenario_id, modern_code, gold_standard)
"""

from __future__ import annotations

import ast
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
4. Read the modern code carefully to determine:
   - The actual endpoint path and HTTP method
   - The exact request body structure (field names, types, nesting)
   - The exact response format (status code conventions and response body fields)
5. Use VALID inputs that pass Pydantic but test the specific business rule.
6. For each test, add a comment with the rule IDs being tested (e.g., # Tests: BR-001)
7. Do NOT add extra tests beyond the listed scenarios.

## EXTRACTED PYDANTIC FIELD SCHEMA (AUTHORITATIVE — MACHINE-PARSED)

The block below was produced by **static analysis** (`ast.parse`) of the modern code.
For **HTTP request JSON bodies**, you MUST use these **exact** field names as keys.
The gold-standard "Input:" may use different spellings (e.g. `WS_ACCOUNT_BALANCE`); map
semantics onto the keys listed here only — **do not** copy gold-standard key spellings
into `json={{...}}` unless they match this list verbatim.

{pydantic_field_reference}

## FIELD NAME RULES (critical — wrong field names cause 100% test failure)

Read the modern code's Pydantic request model CAREFULLY before writing any test:

- Extract the EXACT field names from the request `class ...(BaseModel)` definition
- Use those EXACT field names in your test request bodies — do NOT rename or re-case them
- If the model uses UPPER_SNAKE_CASE (e.g. `WS_DISPUTE_ID`), use UPPER_SNAKE_CASE
- If the model uses lowercase (e.g. `dispute_id`), use lowercase
- If the model uses a `ws_` prefix (e.g. `ws_account_id`), include the `ws_` prefix
- For nested models (e.g. `account_file: Dict[str, AccountRecord]`), construct the
  full nested structure:
  `{{"account_file": {{"ACC123": {{"account_id": "ACC123", "...": "..."}}}}}}`
- For enum/Literal/regex-constrained fields, use ONLY the values defined in the
  constraint. Read the field's type annotation to find allowed values:
    Literal["NEW", "DIS", "MOD"]              -> use one of "NEW", "DIS", "MOD"
    constr(pattern="^(deposit|withdrawal)$")  -> use "deposit" or "withdrawal"
  Do NOT invent values like "test_value" — they will fail Pydantic validation.

The gold-standard test scenarios use clean semantic names (e.g. `dispute_type`).
Map each one onto the model's field by matching meaning, not spelling:
`dispute_type` <-> `ws_dispute_type` <-> `WS_DISPUTE_TYPE` are all the same field.
If a model field has no counterpart in the gold scenario input, leave it unset
(rely on the Pydantic default) rather than inventing a value.

## RESPONSE ASSERTION RULES (critical — different methods use different conventions)

NEVER assert only on HTTP status code for business-rule rejections. Some
modernized services raise `HTTPException(status_code=400)` for business failures;
others return `200` with a validation flag in the body. Read the response model
BEFORE writing assertions:

- If the response model has a boolean validation flag (e.g. `ws_validation_flag`,
  `validation_passed`, `success`, `is_valid`), assert on THAT flag's value.
- If the response model has an error-code field (e.g. `ws_error_code`, `error_code`,
  `result_code`, `WS_RESULT_CODE`), assert on the SPECIFIC code value.
- Only assert `status_code == 422` for Pydantic validation errors (wrong types,
  missing required fields).
- Only assert `status_code == 400` (or 4xx) when the code explicitly raises
  `HTTPException(status_code=...)` for business failures AND does NOT also wrap
  it in a try/except that converts back to a 200 response.

Recommended pattern: accept EITHER convention as a valid rejection signal:
    assert response.status_code in (200, 400, 422)
    body = response.json()
    rejected = (
        response.status_code != 200
        or body.get("ws_validation_flag") is False
        or body.get("validation_passed") is False
        or body.get("success") is False
        or "rejected" in str(body).lower()
        or "error" in str(body).lower()
    )
    assert rejected, f"Expected REJECTED but got: {{body}}"

For successful cases, the inverse:
    assert response.status_code == 200
    body = response.json()
    assert body.get("ws_validation_flag", True) is not False
    # plus any expected output field checks from the gold standard

## PYTHON SYNTAX RULES (must hold or the file will fail to import / serialize)

- All request body values must be JSON-serializable. Use STRINGS for dates and
  datetimes, never Python objects:
    Wrong: `"requested_due": date(2026, 5, 15)`
    Right: `"requested_due": "2026-05-15"`
    Wrong: `"order_time": datetime.now()`
    Right: `"order_time": "2026-05-15T10:00:00"`
- Never call `.isoformat()` on a string literal — the literal is already a string:
    Wrong: `"2026-05-15".isoformat()`
    Right: `"2026-05-15"`
- Never write leading zeros on decimal integer literals. Python 3 rejects `01`,
  `02`, `09` etc. as SyntaxError. For zero-padded fields use strings: `"00123"`.
- For monetary amounts in the body, prefer string form `"12.50"` so JSON
  serializes cleanly; the modern code's Pydantic `Decimal` field will accept it.
- Do not use Python 2 syntax: no `print` statement, no `<>`, no `u"..."`.
- Imports: keep them minimal. Recommended set:
    `import pytest`
    `from fastapi.testclient import TestClient`
    `from main import app`
  Do NOT import `date`, `datetime`, or `Decimal` — you do not need them; all
  body values should be plain strings/ints/floats/bools/dicts/lists.
- All test functions must be syntactically valid Python 3 — the file is run
  through `compile()` before pytest sees it.

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


def _extract_gold_standard_sections(
    gold_standard: dict[str, Any],
) -> tuple[list, list, list]:
    """Pull rules, constraints, and test scenarios out of a gold-standard dict.

    The benchmark uses two schemas:

    - S1 stores a flat list under ``rules`` and constraints under ``constraints``.
    - S2-S8 store ``business_rules`` as a dict ``{"explicit": [...],
      "implicit": [...]}`` and constraints under ``data_constraints``.

    This helper flattens both into a single ``(rules, constraints,
    test_scenarios)`` tuple so callers can treat all 8 scenarios uniformly.
    """
    rules_raw = gold_standard.get("rules") or gold_standard.get("business_rules") or []
    if isinstance(rules_raw, dict):
        # S2-S8 layout: {"explicit": [...], "implicit": [...]}
        flat: list = []
        for v in rules_raw.values():
            if isinstance(v, list):
                flat.extend(v)
        rules = flat
    else:
        rules = list(rules_raw)

    constraints = (
        gold_standard.get("constraints")
        or gold_standard.get("data_constraints")
        or []
    )
    test_scenarios = gold_standard.get("test_scenarios", [])
    return rules, constraints, test_scenarios


def _strip_python_markdown_fences(code: str) -> str:
    """Remove leading ```python fences if the model wrapped the file."""
    patched = code.strip()
    if patched.startswith("```python"):
        patched = patched[len("```python") :].strip()
    elif patched.startswith("```"):
        patched = patched[3:].strip()
    if patched.endswith("```"):
        patched = patched[:-3].strip()
    return patched


def _is_basemodel_base(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "BaseModel"
    if isinstance(base, ast.Attribute):
        return base.attr == "BaseModel"
    return False


def _class_inherits_basemodel(node: ast.ClassDef) -> bool:
    return any(_is_basemodel_base(b) for b in node.bases)


def _annotation_to_type_str(ann: ast.expr | None) -> str:
    if ann is None:
        return "Any"
    try:
        return ast.unparse(ann)
    except AttributeError:  # pragma: no cover — Python < 3.9
        return "?"


def _unwrap_common_wrappers(ann: ast.expr | None) -> ast.expr | None:
    """Strip Annotated[..., *], Optional[...], Union[..., None], and T | None."""
    if ann is None:
        return None
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        for branch in (ann.left, ann.right):
            if isinstance(branch, ast.Constant) and branch.value is None:
                continue
            inner = _unwrap_common_wrappers(branch)
            if inner is not None:
                return inner
        return ann
    if isinstance(ann, ast.Subscript):
        val = ann.value
        sl = ann.slice
        if isinstance(val, ast.Name) and val.id == "Annotated":
            inner = sl.elts[0] if isinstance(sl, ast.Tuple) else sl
            return _unwrap_common_wrappers(inner)
        if isinstance(val, ast.Name) and val.id == "Optional":
            inner = sl.elts[0] if isinstance(sl, ast.Tuple) else sl
            return _unwrap_common_wrappers(inner)
        if isinstance(val, ast.Name) and val.id == "Union":
            if isinstance(sl, ast.Tuple):
                for elt in sl.elts:
                    if isinstance(elt, ast.Constant) and elt.value is None:
                        continue
                    return _unwrap_common_wrappers(elt)
            return _unwrap_common_wrappers(sl)
    return ann


def _model_name_from_annotation(ann: ast.expr | None) -> str | None:
    inner = _unwrap_common_wrappers(ann)
    if isinstance(inner, ast.Name):
        return inner.id
    if isinstance(inner, ast.Subscript) and isinstance(inner.value, ast.Name):
        return inner.value.id
    return None


def _has_fastapi_route_decorator(fn: ast.FunctionDef) -> bool:
    http_names = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    for dec in fn.decorator_list:
        call: ast.Call | None = None
        if isinstance(dec, ast.Call):
            call = dec
        if call is None:
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr.lower() in http_names:
            return True
    return False


def _fastapi_request_body_model_names(tree: ast.AST) -> list[str]:
    """First typed parameter on each @app.post(...) / @router.post(...) etc."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not _has_fastapi_route_decorator(node):
            continue
        for arg in node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            model = _model_name_from_annotation(arg.annotation)
            if model:
                found.append(model)
                break
    out: list[str] = []
    for m in found:
        if m not in out:
            out.append(m)
    return out


def _collect_basemodel_fields(tree: ast.AST) -> dict[str, list[tuple[str, str]]]:
    """Map class name -> [(field_name, type_as_string), ...]."""
    models: dict[str, list[tuple[str, str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _class_inherits_basemodel(node):
            continue
        fields: list[tuple[str, str]] = []
        for item in node.body:
            if not isinstance(item, ast.AnnAssign):
                continue
            if not isinstance(item.target, ast.Name):
                continue
            fname = item.target.id
            # Pydantic config / metadata, not a payload field
            if fname == "model_config":
                continue
            fields.append((fname, _annotation_to_type_str(item.annotation)))
        models[node.name] = fields
    return models


def _format_pydantic_field_reference(modern_code: str) -> str:
    """Produce human-readable schema text for the harness LLM prompt."""
    source = _strip_python_markdown_fences(modern_code)
    if not source.strip():
        return "(No modern code supplied — cannot extract Pydantic models.)"
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"(Modern code is not valid Python — parse error: {exc})"

    models = _collect_basemodel_fields(tree)
    if not models:
        return (
            "(No `class ...` inheriting from `BaseModel` was found. "
            "Fall back to reading the modern code manually.)"
        )

    primary = _fastapi_request_body_model_names(tree)
    lines: list[str] = []

    if primary:
        lines.append("### Primary HTTP request body model(s) (from FastAPI route signatures)")
        lines.append("")
        for name in primary:
            if name in models:
                lines.append(f"- **`{name}`** - use these keys in `json={{...}}`:")
                for fname, ftype in models[name]:
                    lines.append(f"  - `{fname}`: `{ftype}`")
                lines.append("")
            else:
                lines.append(
                    f"- **`{name}`** - referenced by a route but fields were not found "
                    "as a BaseModel subclass (check the code)."
                )
                lines.append("")

    other = [n for n in models if n not in primary]
    if other:
        lines.append("### Other `BaseModel` classes in this file (reference / nested types)")
        lines.append("")
        for name in sorted(other):
            lines.append(f"- **`{name}`**:")
            if not models[name]:
                lines.append("  - (no annotated fields detected)")
            else:
                for fname, ftype in models[name]:
                    lines.append(f"  - `{fname}`: `{ftype}`")
            lines.append("")

    return "\n".join(lines).strip()


def _modern_code_is_valid_python(modern_code: str) -> tuple[bool, str | None]:
    """Return (ok, error_message). Prose / invalid syntax => not ok."""
    source = _strip_python_markdown_fences(modern_code)
    if not source.strip():
        return False, "empty modern code after stripping fences"
    try:
        compile(source, "<modern_code>", "exec", ast.PyCF_ONLY_AST)
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"
    return True, None


def _invalid_modern_code_report(
    scenario_id: str,
    gold_standard: dict[str, Any],
    message: str,
) -> BehavioralEquivalenceReport:
    """All gold-standard tests counted as failed (0% BER) — invalid service code."""
    rules, _constraints, scenarios = _extract_gold_standard_sections(gold_standard)
    _ = rules
    results: list[TestResult] = []
    for ts in scenarios:
        tid = ts.get("id", "unknown")
        results.append(
            TestResult(
                test_id=f"test_{tid}",
                description=f"Skipped — invalid modern_code: {message[:200]}",
                status=TestStatus.ERROR,
                bsg_node_id="",
                business_rule_ids=[str(tid)],
                error_message=message,
            )
        )
    if not results:
        results.append(
            TestResult(
                test_id="overall",
                description="Invalid modern code (no test scenarios)",
                status=TestStatus.ERROR,
                bsg_node_id="",
                error_message=message,
            )
        )
    return BehavioralEquivalenceReport(scenario_id=scenario_id, results=results)


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
        rules, constraints, test_scenarios = _extract_gold_standard_sections(
            gold_standard
        )

        if not test_scenarios:
            logger.warning(
                "[%s] No test scenarios in gold standard for %s",
                self.agent_name,
                scenario_id,
            )
            return BehavioralEquivalenceReport(scenario_id=scenario_id)

        ok_code, code_err = _modern_code_is_valid_python(modern_code)
        if not ok_code:
            logger.warning(
                "[%s] Modern code for %s is not valid Python (%s) — "
                "skipping harness generation, scoring 0%%",
                self.agent_name,
                scenario_id,
                code_err,
            )
            return _invalid_modern_code_report(
                scenario_id, gold_standard, code_err or "invalid Python"
            )

        logger.info(
            "[%s] Evaluating %s with %d gold-standard tests",
            self.agent_name,
            scenario_id,
            len(test_scenarios),
        )

        test_scenarios_text = self._format_test_scenarios(test_scenarios)
        rules_json = json.dumps(rules, indent=2)
        constraints_json = json.dumps(constraints, indent=2)
        pydantic_field_reference = _format_pydantic_field_reference(modern_code)

        prompt = GOLD_STANDARD_TEST_PROMPT.format(
            modern_code=modern_code,
            pydantic_field_reference=pydantic_field_reference,
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
        rules, constraints, test_scenarios = _extract_gold_standard_sections(
            gold_standard
        )

        if not test_scenarios:
            logger.warning("[%s] No test scenarios for %s", self.agent_name, scenario_id)
            return None

        ok_ref, ref_err = _modern_code_is_valid_python(reference_code)
        if not ok_ref:
            logger.warning(
                "[%s] Reference code for %s is not valid Python (%s) — "
                "cannot generate harness",
                self.agent_name,
                scenario_id,
                ref_err,
            )
            return None

        test_scenarios_text = self._format_test_scenarios(test_scenarios)
        rules_json = json.dumps(rules, indent=2)
        constraints_json = json.dumps(constraints, indent=2)
        pydantic_field_reference = _format_pydantic_field_reference(reference_code)

        prompt = GOLD_STANDARD_TEST_PROMPT.format(
            modern_code=reference_code,
            pydantic_field_reference=pydantic_field_reference,
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
        gold_standard: dict[str, Any] | None = None,
    ) -> BehavioralEquivalenceReport:
        """Evaluate modern code using pre-generated test code (no LLM call).

        Args:
            scenario_id: Scenario identifier.
            modern_code: The generated code to evaluate.
            test_code: Pre-generated pytest test code.
            gold_standard: If provided, invalid ``modern_code`` yields one ERROR
                result per gold-standard scenario (0% BER with correct N).

        Returns:
            BehavioralEquivalenceReport.
        """
        ok_code, code_err = _modern_code_is_valid_python(modern_code)
        if not ok_code:
            logger.warning(
                "[%s] Modern code for %s is not valid Python (%s) — "
                "skipping pytest, scoring 0%%",
                self.agent_name,
                scenario_id,
                code_err,
            )
            if gold_standard is not None:
                return _invalid_modern_code_report(
                    scenario_id, gold_standard, code_err or "invalid Python"
                )
            return BehavioralEquivalenceReport(
                scenario_id=scenario_id,
                results=[
                    TestResult(
                        test_id="overall",
                        description="Invalid modern code — skipped pytest",
                        status=TestStatus.ERROR,
                        bsg_node_id="",
                        error_message=code_err,
                    )
                ],
            )

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

    def _generate_tests_with_retry(self, prompt: str) -> str:
        """Generate test code, retrying if the LLM output is malformed or has syntax errors."""
        test_code = ""
        for attempt in range(MAX_TEST_GEN_RETRIES):
            response = self._invoke_llm(prompt)
            test_code = self._clean_code(response)

            if "def test_" not in test_code or "import" not in test_code:
                logger.warning(
                    "[%s] Attempt %d: generated code missing test functions, retrying",
                    self.agent_name,
                    attempt + 1,
                )
                continue

            # Validate syntax before accepting
            try:
                compile(test_code, "<test>", "exec")
                return test_code
            except SyntaxError as exc:
                logger.warning(
                    "[%s] Attempt %d: syntax error in generated tests: %s, retrying",
                    self.agent_name,
                    attempt + 1,
                    exc,
                )

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
            path_fix = f"import sys\nsys.path.insert(0, {tmpdir!r})\n"
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

        # Step 1: Replace condecimal(...) with float (strips Pydantic Decimal validation).
        patched = re.sub(r"condecimal\([^)]*\)", "float", patched)

        # Step 2: Process imports and non-imports differently to avoid mangling
        # function parameter annotations like `def fn(x: condecimal, y: condecimal)`.
        new_lines: list[str] = []
        import_re = re.compile(r"^\s*from\s+pydantic\s+import\s+(.+)$")
        for line in patched.splitlines():
            m = import_re.match(line)
            if m:
                # Parse and rebuild the from-pydantic import without `condecimal`.
                items = [tok.strip() for tok in m.group(1).split(",")]
                items = [tok for tok in items if tok and tok != "condecimal"]
                new_lines.append("from pydantic import " + ", ".join(items))
            else:
                # In non-import lines, bare `condecimal` is an invalid annotation
                # (Pydantic only exposes it as a callable); replace with builtin `float`.
                new_lines.append(re.sub(r"\bcondecimal\b", "float", line))
        return "\n".join(new_lines)

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
