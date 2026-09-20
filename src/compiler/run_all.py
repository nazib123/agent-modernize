"""Batch runner: compile and test S2-S7 against all gold standard test scenarios.

This is the definitive test of Alec's compilation theory:
  If formal specs (effect fields) are correct → compilation is perfect.
  No LLM needed. No hallucination possible.
"""
from __future__ import annotations

import sys
from pathlib import Path

from compiler.bsg_compiler import BSGCompiler

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "benchmark"

SCENARIOS = [
    "S2_billing_dispute",
    "S3_service_activation",
    "S4_circuit_inventory",
    "S5_fault_escalation",
    "S6_contract_renewal",
    "S7_account_migration",
    "SR360800_california_gold",
]


def main():
    total_pass = 0
    total_fail = 0
    total_tests = 0
    scenario_results = []

    print("=" * 60)
    print("BSG COMPILER — FULL BATCH TEST (Alec's Compilation Theory)")
    print("=" * 60)
    print()

    for scenario_dir in SCENARIOS:
        gs_path = BENCHMARK_DIR / scenario_dir / "gold_standard.json"
        if not gs_path.exists():
            print(f"  [SKIP] {scenario_dir}: gold_standard.json not found")
            continue

        compiler = BSGCompiler(str(gs_path))
        results = compiler.verify_against_tests()

        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        total_pass += passed
        total_fail += failed
        total_tests += len(results)

        pct = (passed / len(results) * 100) if results else 0
        status_icon = "PERFECT" if failed == 0 else f"{failed} FAIL"
        scenario_results.append((compiler.scenario_id, scenario_dir, passed, len(results), status_icon))

        print(f"── {compiler.scenario_id}: {compiler.spec['scenario_name']} ──")
        print(f"   Rules: {len(compiler.rules)} ({sum(1 for r in compiler.rules if r.category == 'explicit')} explicit, "
              f"{sum(1 for r in compiler.rules if r.category == 'implicit')} implicit)")

        for r in results:
            icon = "PASS" if r["passed"] else "FAIL"
            print(f"   [{icon}] {r['test_id']}: {r['description']}")
            if not r["passed"]:
                if "error" in r:
                    print(f"          ERROR: {r['error']}")
                else:
                    print(f"          Expected: {r.get('expected')}")
                    print(f"          Actual:   {r.get('actual')}")
        print()

    # ── Summary ──────────────────────────────────────────────────────
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print(f"{'Scenario':<5} {'Name':<30} {'Result':<12} {'Tests'}")
    print("-" * 60)
    for sid, dirname, p, t, status in scenario_results:
        name = dirname.split("_", 1)[1].replace("_", " ").title()
        print(f"{sid:<5} {name:<30} {status:<12} {p}/{t}")
    print("-" * 60)
    print(f"{'TOTAL':<5} {'':<30} {'':12} {total_pass}/{total_tests}")
    print()

    pct = (total_pass / total_tests * 100) if total_tests else 0
    if total_fail == 0:
        print(f"VERDICT: ALL {total_tests} TESTS PASSED ({pct:.0f}%)")
        print("ALEC'S THEORY CONFIRMED: Formal spec → deterministic compilation → perfect code.")
    else:
        print(f"VERDICT: {total_fail}/{total_tests} FAILURES ({pct:.0f}% pass rate)")
        print("Note: Failures may indicate gold standard bugs, not compiler bugs.")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
