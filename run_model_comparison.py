"""Run full model comparison: GPT-4o-mini vs GPT-4o on all scenarios.

This script:
1. Runs all scenarios (S1-S8) with GPT-4o (GPT-4o-mini results already exist)
2. Runs baselines (SP-LLM, CoT-LLM) for S8
3. Runs fair evaluation for S8 and the GPT-4o results

Usage (from agent-modernize venv):
    python run_model_comparison.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from src.baselines.chain_of_thought import ChainOfThoughtBaseline
from src.baselines.single_prompt import SinglePromptBaseline
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

MODEL_4O = "gpt-4o"
MODEL_MINI = "gpt-4o-mini"
RESULTS_BASE = Path(RESULTS_DIR)


def run_s8_baselines() -> None:
    """Run baselines for S8 (new scenario)."""
    dir_name = SCENARIO_MAP["S8"]
    scenario_dir = Path(BENCHMARK_DIR) / dir_name
    gs_path = scenario_dir / "gold_standard.json"
    legacy_code = (scenario_dir / "legacy_code.cbl").read_text()
    with gs_path.open() as f:
        gold_standard = json.load(f)

    initial_state = {
        "scenario_id": "S8",
        "legacy_code": legacy_code,
        "gold_standard": gold_standard,
        "iteration": 0,
    }

    for baseline_name, baseline_cls in [
        ("sp-llm", SinglePromptBaseline),
        ("cot-llm", ChainOfThoughtBaseline),
    ]:
        logger.info("S8 / %s: starting...", baseline_name)
        agent = baseline_cls()
        state = agent.run(dict(initial_state))
        out_dir = RESULTS_BASE / f"S8_{baseline_name}"
        save_results(state, out_dir)
        logger.info("S8 / %s: saved to %s", baseline_name, out_dir)


def run_s8_am_pipeline() -> None:
    """Run AgentModernize pipeline on S8 with default model (gpt-4o-mini)."""
    scenario_dir = Path(BENCHMARK_DIR) / SCENARIO_MAP["S8"]
    logger.info("S8 / AM (gpt-4o-mini): starting...")
    state = run_scenario(scenario_dir, model_name=MODEL_MINI)
    save_results(state, RESULTS_BASE / "S8")
    logger.info("S8 / AM: done")

    # No-feedback ablation
    import src.config as cfg
    original = cfg.MAX_FEEDBACK_ITERATIONS
    cfg.MAX_FEEDBACK_ITERATIONS = 1
    logger.info("S8 / AM-no-fb: starting...")
    state_nf = run_scenario(scenario_dir, model_name=MODEL_MINI)
    save_results(state_nf, RESULTS_BASE / "S8_no_feedback")
    cfg.MAX_FEEDBACK_ITERATIONS = original
    logger.info("S8 / AM-no-fb: done")


def run_gpt4o_all() -> None:
    """Run full AM pipeline on all S1-S8 with GPT-4o."""
    import src.config as cfg

    for sid, dir_name in SCENARIO_MAP.items():
        scenario_dir = Path(BENCHMARK_DIR) / dir_name
        if not scenario_dir.exists():
            logger.warning("Skipping %s — not found", sid)
            continue

        out_dir = RESULTS_BASE / f"{sid}_gpt4o"
        if out_dir.exists():
            logger.info("%s / GPT-4o: already exists, skipping", sid)
            continue

        logger.info("%s / GPT-4o: starting...", sid)
        state = run_scenario(scenario_dir, model_name=MODEL_4O)
        save_results(state, out_dir)
        logger.info("%s / GPT-4o: done", sid)

        # Also run no-feedback ablation
        nf_dir = RESULTS_BASE / f"{sid}_gpt4o_no_feedback"
        if not nf_dir.exists():
            original = cfg.MAX_FEEDBACK_ITERATIONS
            cfg.MAX_FEEDBACK_ITERATIONS = 1
            logger.info("%s / GPT-4o (no-fb): starting...", sid)
            state_nf = run_scenario(scenario_dir, model_name=MODEL_4O)
            save_results(state_nf, nf_dir)
            cfg.MAX_FEEDBACK_ITERATIONS = original


def run_fair_eval_both_models() -> None:
    """Run fair evaluation comparing both models."""
    evaluator = GoldStandardEvaluator()
    results: dict[str, dict[str, float]] = {}

    for sid, dir_name in SCENARIO_MAP.items():
        gs_path = Path(BENCHMARK_DIR) / dir_name / "gold_standard.json"
        if not gs_path.exists():
            continue
        with gs_path.open() as f:
            gold_standard = json.load(f)

        results[sid] = {}

        # For each model, find the AM code and evaluate
        for label, dir_suffix in [("mini", sid), ("4o", f"{sid}_gpt4o")]:
            code_dir = RESULTS_BASE / dir_suffix
            if not code_dir.exists():
                continue
            modern_code = None
            for p in code_dir.iterdir():
                if p.name.endswith("_modern_service.py"):
                    modern_code = p.read_text()
                    break
            if modern_code is None:
                continue

            # Generate tests using this model's code as reference
            test_code = evaluator.generate_test_code(sid, modern_code, gold_standard)
            if test_code is None:
                logger.error("%s/%s: test gen failed", sid, label)
                continue

            report = evaluator.evaluate_with_tests(sid, modern_code, test_code)
            results[sid][label] = report.behavioral_equivalence_rate
            logger.info(
                "%s / %s: %.1f%% (%d/%d)",
                sid, label,
                report.behavioral_equivalence_rate,
                report.passed_tests, report.total_tests,
            )

    # Print comparison table
    print(f"\n{'='*50}")
    print("Model Comparison — BER (%)")
    print(f"{'='*50}")
    print(f"{'Scenario':<10} {'GPT-4o-mini':<15} {'GPT-4o':<15}")
    print(f"{'-'*40}")
    for sid in SCENARIO_MAP:
        mini = results.get(sid, {}).get("mini", 0.0)
        full = results.get(sid, {}).get("4o", 0.0)
        print(f"{sid:<10} {mini:<15.1f} {full:<15.1f}")

    mini_avg = sum(results.get(s, {}).get("mini", 0.0) for s in SCENARIO_MAP) / len(SCENARIO_MAP)
    full_avg = sum(results.get(s, {}).get("4o", 0.0) for s in SCENARIO_MAP) / len(SCENARIO_MAP)
    print(f"{'-'*40}")
    print(f"{'Avg':<10} {mini_avg:<15.1f} {full_avg:<15.1f}")
    print(f"{'='*50}\n")

    summary_path = RESULTS_BASE / "model_comparison.json"
    summary_path.write_text(json.dumps(results, indent=2))
    logger.info("Saved to %s", summary_path)


def main() -> None:
    print("=" * 60)
    print("PHASE 1: S8 baselines (SP-LLM, CoT-LLM)")
    print("=" * 60)
    run_s8_baselines()

    print("\n" + "=" * 60)
    print("PHASE 2: S8 AgentModernize pipeline")
    print("=" * 60)
    run_s8_am_pipeline()

    print("\n" + "=" * 60)
    print("PHASE 3: GPT-4o on all scenarios (S1-S8)")
    print("=" * 60)
    run_gpt4o_all()

    print("\n" + "=" * 60)
    print("PHASE 4: Fair evaluation — model comparison")
    print("=" * 60)
    run_fair_eval_both_models()


if __name__ == "__main__":
    main()
