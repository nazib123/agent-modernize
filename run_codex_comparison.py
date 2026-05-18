"""Run GPT-5.3-codex on all scenarios and produce three-model comparison.

This script:
1. Runs all scenarios (S1-S8) with GPT-5.3-codex
2. Runs fair evaluation comparing all three models (mini, 4o, codex)

Usage:
    export OPENAI_API_KEY="sk-..."
    python run_codex_comparison.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from src.config import BENCHMARK_DIR, RESULTS_DIR
from src.evaluation import GoldStandardEvaluator
from src.pipeline import run_scenario, save_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SCENARIO_MAP = {
    "S1": "S1_order_validation",
    "S2": "S2_billing_dispute",
    "S3": "S3_service_activation",
    "S4": "S4_circuit_inventory",
    "S5": "S5_fault_escalation",
    "S6": "S6_contract_renewal",
    "S7": "S7_account_migration",
    "S8": "S8_bank_transaction",
}

MODEL_CODEX = "gpt-5.3-codex"
MODEL_4O = "gpt-4o"
MODEL_MINI = "gpt-4o-mini"
RESULTS_BASE = Path(RESULTS_DIR)


def run_codex_all() -> None:
    """Run full AM pipeline on all S1-S8 with GPT-5.3-codex."""
    import src.config as cfg

    for sid, dir_name in SCENARIO_MAP.items():
        scenario_dir = Path(BENCHMARK_DIR) / dir_name
        if not scenario_dir.exists():
            logger.warning("Skipping %s — not found", sid)
            continue

        out_dir = RESULTS_BASE / f"{sid}_codex"
        if out_dir.exists():
            logger.info("%s / codex: already exists, skipping", sid)
            continue

        logger.info("%s / GPT-5.3-codex: starting...", sid)
        state = run_scenario(scenario_dir, model_name=MODEL_CODEX)
        save_results(state, out_dir)
        logger.info("%s / GPT-5.3-codex: done", sid)

        # Also run no-feedback ablation
        nf_dir = RESULTS_BASE / f"{sid}_codex_no_feedback"
        if not nf_dir.exists():
            original = cfg.MAX_FEEDBACK_ITERATIONS
            cfg.MAX_FEEDBACK_ITERATIONS = 1
            logger.info("%s / codex (no-fb): starting...", sid)
            state_nf = run_scenario(scenario_dir, model_name=MODEL_CODEX)
            save_results(state_nf, nf_dir)
            cfg.MAX_FEEDBACK_ITERATIONS = original


def run_fair_eval_three_models() -> None:
    """Run fair evaluation comparing all three models."""
    evaluator = GoldStandardEvaluator()
    results: dict[str, dict[str, float]] = {}

    model_configs = [
        ("mini", lambda sid: sid),
        ("4o", lambda sid: f"{sid}_gpt4o"),
        ("codex", lambda sid: f"{sid}_codex"),
    ]

    for sid, dir_name in SCENARIO_MAP.items():
        gs_path = Path(BENCHMARK_DIR) / dir_name / "gold_standard.json"
        if not gs_path.exists():
            continue
        with gs_path.open() as f:
            gold_standard = json.load(f)

        results[sid] = {}

        for label, dir_fn in model_configs:
            code_dir = RESULTS_BASE / dir_fn(sid)
            if not code_dir.exists():
                results[sid][label] = 0.0
                continue
            modern_code = None
            for p in code_dir.iterdir():
                if p.name.endswith("_modern_service.py"):
                    modern_code = p.read_text()
                    break
            if modern_code is None:
                results[sid][label] = 0.0
                continue

            test_code = evaluator.generate_test_code(sid, modern_code, gold_standard)
            if test_code is None:
                logger.error("%s/%s: test gen failed", sid, label)
                results[sid][label] = 0.0
                continue

            report = evaluator.evaluate_with_tests(
                sid, modern_code, test_code, gold_standard=gold_standard
            )
            results[sid][label] = report.behavioral_equivalence_rate
            logger.info(
                "%s / %s: %.1f%% (%d/%d)",
                sid, label,
                report.behavioral_equivalence_rate,
                report.passed_tests, report.total_tests,
            )

    # Print three-model comparison table
    print(f"\n{'='*65}")
    print("Three-Model Comparison — BER (%)")
    print(f"{'='*65}")
    print(f"{'Scenario':<10} {'GPT-4o-mini':<15} {'GPT-4o':<15} {'GPT-5.3-codex':<15}")
    print(f"{'-'*55}")
    for sid in SCENARIO_MAP:
        mini = results.get(sid, {}).get("mini", 0.0)
        full = results.get(sid, {}).get("4o", 0.0)
        codex = results.get(sid, {}).get("codex", 0.0)
        print(f"{sid:<10} {mini:<15.1f} {full:<15.1f} {codex:<15.1f}")

    mini_avg = sum(results.get(s, {}).get("mini", 0.0) for s in SCENARIO_MAP) / len(SCENARIO_MAP)
    full_avg = sum(results.get(s, {}).get("4o", 0.0) for s in SCENARIO_MAP) / len(SCENARIO_MAP)
    codex_avg = sum(results.get(s, {}).get("codex", 0.0) for s in SCENARIO_MAP) / len(SCENARIO_MAP)
    mini_nz = sum(1 for s in SCENARIO_MAP if results.get(s, {}).get("mini", 0.0) > 0)
    full_nz = sum(1 for s in SCENARIO_MAP if results.get(s, {}).get("4o", 0.0) > 0)
    codex_nz = sum(1 for s in SCENARIO_MAP if results.get(s, {}).get("codex", 0.0) > 0)
    print(f"{'-'*55}")
    print(f"{'Avg':<10} {mini_avg:<15.1f} {full_avg:<15.1f} {codex_avg:<15.1f}")
    print(f"{'Non-zero':<10} {f'{mini_nz}/8':<15} {f'{full_nz}/8':<15} {f'{codex_nz}/8':<15}")
    print(f"{'='*65}\n")

    summary_path = RESULTS_BASE / "three_model_comparison.json"
    summary_path.write_text(json.dumps(results, indent=2))
    logger.info("Saved to %s", summary_path)


def main() -> None:
    print("=" * 60)
    print("PHASE 1: GPT-5.3-codex on all scenarios (S1-S8)")
    print("=" * 60)
    run_codex_all()

    print("\n" + "=" * 60)
    print("PHASE 2: Fair evaluation — three-model comparison")
    print("=" * 60)
    run_fair_eval_three_models()


if __name__ == "__main__":
    main()
