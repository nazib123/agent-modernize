"""Run SP-LLM and CoT-LLM baselines with GPT-4o and GPT-5.3-codex.

Also runs S8 with AgentModernize + codex (missing from prior run).

This fills the missing cells in the comparison matrix:
  - SP-LLM  × GPT-4o        (S1-S8)
  - CoT-LLM × GPT-4o        (S1-S8)
  - SP-LLM  × GPT-5.3-codex (S1-S8)
  - CoT-LLM × GPT-5.3-codex (S1-S8)
  - AM       × GPT-5.3-codex (S8 only)

Usage:
    export OPENAI_API_KEY="sk-..."
    python run_full_baseline_comparison.py
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
MODEL_CODEX = "gpt-5.3-codex"
RESULTS_BASE = Path(RESULTS_DIR)


def run_baselines_for_model(model_name: str, model_label: str) -> None:
    """Run SP-LLM and CoT-LLM baselines for all scenarios with given model."""
    for sid, dir_name in SCENARIO_MAP.items():
        scenario_dir = Path(BENCHMARK_DIR) / dir_name
        if not scenario_dir.exists():
            logger.warning("Skipping %s — not found", sid)
            continue

        legacy_code = (scenario_dir / "legacy_code.cbl").read_text()
        gs_path = scenario_dir / "gold_standard.json"
        with gs_path.open() as f:
            gold_standard = json.load(f)

        initial_state = {
            "scenario_id": sid,
            "legacy_code": legacy_code,
            "gold_standard": gold_standard,
            "iteration": 0,
        }

        for baseline_name, baseline_cls in [
            ("sp-llm", SinglePromptBaseline),
            ("cot-llm", ChainOfThoughtBaseline),
        ]:
            out_dir = RESULTS_BASE / f"{sid}_{baseline_name}_{model_label}"
            if out_dir.exists():
                logger.info("%s / %s / %s: already exists, skipping", sid, baseline_name, model_label)
                continue

            logger.info("%s / %s / %s: starting...", sid, baseline_name, model_label)
            agent = baseline_cls(model_name=model_name)
            state = agent.run(dict(initial_state))
            save_results(state, out_dir)
            logger.info("%s / %s / %s: saved to %s", sid, baseline_name, model_label, out_dir)


def run_s8_codex_am() -> None:
    """Run AgentModernize on S8 with codex (was missing from prior run)."""
    import src.config as cfg

    scenario_dir = Path(BENCHMARK_DIR) / SCENARIO_MAP["S8"]

    out_dir = RESULTS_BASE / "S8_codex"
    if out_dir.exists():
        logger.info("S8 / AM / codex: already exists, skipping")
    else:
        logger.info("S8 / AM / codex: starting...")
        state = run_scenario(scenario_dir, model_name=MODEL_CODEX)
        save_results(state, out_dir)
        logger.info("S8 / AM / codex: done")

    nf_dir = RESULTS_BASE / "S8_codex_no_feedback"
    if nf_dir.exists():
        logger.info("S8 / AM-no-fb / codex: already exists, skipping")
    else:
        original = cfg.MAX_FEEDBACK_ITERATIONS
        cfg.MAX_FEEDBACK_ITERATIONS = 1
        logger.info("S8 / AM-no-fb / codex: starting...")
        state_nf = run_scenario(scenario_dir, model_name=MODEL_CODEX)
        save_results(state_nf, nf_dir)
        cfg.MAX_FEEDBACK_ITERATIONS = original


def run_fair_eval_full_matrix() -> None:
    """Run fair evaluation for the complete 3×3 model-method matrix."""
    evaluator = GoldStandardEvaluator()
    results: dict[str, dict[str, float]] = {}

    # (label, dir_pattern) for each method × model combination
    configs = [
        ("SP-LLM / mini", lambda sid: f"{sid}_sp-llm"),
        ("SP-LLM / 4o", lambda sid: f"{sid}_sp-llm_gpt4o"),
        ("SP-LLM / codex", lambda sid: f"{sid}_sp-llm_codex"),
        ("CoT / mini", lambda sid: f"{sid}_cot-llm"),
        ("CoT / 4o", lambda sid: f"{sid}_cot-llm_gpt4o"),
        ("CoT / codex", lambda sid: f"{sid}_cot-llm_codex"),
        ("AM / mini", lambda sid: sid),
        ("AM / 4o", lambda sid: f"{sid}_gpt4o"),
        ("AM / codex", lambda sid: f"{sid}_codex"),
    ]

    for sid, dir_name in SCENARIO_MAP.items():
        gs_path = Path(BENCHMARK_DIR) / dir_name / "gold_standard.json"
        if not gs_path.exists():
            continue
        with gs_path.open() as f:
            gold_standard = json.load(f)

        results[sid] = {}

        for label, dir_fn in configs:
            code_dir = RESULTS_BASE / dir_fn(sid)
            if not code_dir.exists():
                results[sid][label] = -1  # not available
                continue

            modern_code = None
            for p in code_dir.iterdir():
                if p.name.endswith("_modern_service.py"):
                    modern_code = p.read_text()
                    break
            if modern_code is None:
                results[sid][label] = -1
                continue

            test_code = evaluator.generate_test_code(sid, modern_code, gold_standard)
            if test_code is None:
                logger.error("%s / %s: test gen failed", sid, label)
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

    # Print full matrix
    methods = ["SP-LLM", "CoT", "AM"]
    models = ["mini", "4o", "codex"]

    print(f"\n{'='*80}")
    print("FULL COMPARISON MATRIX — BER (%)")
    print(f"{'='*80}")

    for method in methods:
        print(f"\n--- {method} ---")
        print(f"{'Scenario':<8}", end="")
        for model in models:
            print(f"  {model:<12}", end="")
        print()
        print("-" * 44)

        for sid in SCENARIO_MAP:
            print(f"{sid:<8}", end="")
            for model in models:
                key = f"{method} / {model}"
                val = results.get(sid, {}).get(key, -1)
                if val < 0:
                    print(f"  {'N/A':<12}", end="")
                else:
                    print(f"  {val:<12.1f}", end="")
            print()

        # Averages
        print("-" * 44)
        print(f"{'Avg':<8}", end="")
        for model in models:
            key = f"{method} / {model}"
            vals = [results.get(s, {}).get(key, -1) for s in SCENARIO_MAP]
            valid = [v for v in vals if v >= 0]
            avg = sum(valid) / len(valid) if valid else 0
            print(f"  {avg:<12.1f}", end="")
        print()

    # Save
    summary_path = RESULTS_BASE / "full_matrix_comparison.json"
    summary_path.write_text(json.dumps(results, indent=2))
    logger.info("Saved to %s", summary_path)


def main() -> None:
    print("=" * 60)
    print("PHASE 1: SP-LLM & CoT-LLM baselines with GPT-4o")
    print("=" * 60)
    run_baselines_for_model(MODEL_4O, "gpt4o")

    print("\n" + "=" * 60)
    print("PHASE 2: SP-LLM & CoT-LLM baselines with GPT-5.3-codex")
    print("=" * 60)
    run_baselines_for_model(MODEL_CODEX, "codex")

    print("\n" + "=" * 60)
    print("PHASE 3: S8 AgentModernize with codex")
    print("=" * 60)
    run_s8_codex_am()

    print("\n" + "=" * 60)
    print("PHASE 4: Fair evaluation — full 3×3 matrix")
    print("=" * 60)
    run_fair_eval_full_matrix()


if __name__ == "__main__":
    main()
