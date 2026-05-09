"""Run AgentModernize experiments on benchmark scenarios.

Usage:
    # Run a single scenario:
    python run_experiment.py --scenario S1

    # Run all scenarios:
    python run_experiment.py --all

    # Run baselines for comparison:
    python run_experiment.py --scenario S1 --baseline sp-llm
    python run_experiment.py --scenario S1 --baseline cot-llm
"""

from __future__ import annotations

import argparse
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


VALID_BASELINES = {"sp-llm", "cot-llm"}


def _load_scenario(scenario_id: str) -> tuple[Path, str, dict]:
    """Load scenario files and return (scenario_dir, legacy_code, gold_standard)."""
    dir_name = SCENARIO_MAP.get(scenario_id)
    if dir_name is None:
        logger.error("Unknown scenario: %s. Valid: %s", scenario_id, list(SCENARIO_MAP.keys()))
        sys.exit(1)

    scenario_dir = Path(BENCHMARK_DIR) / dir_name
    if not scenario_dir.exists():
        logger.error("Scenario directory not found: %s", scenario_dir)
        sys.exit(1)

    legacy_code = (scenario_dir / "legacy_code.cbl").read_text()
    with (scenario_dir / "gold_standard.json").open() as f:
        gold_standard = json.load(f)

    return scenario_dir, legacy_code, gold_standard


def _print_summary(scenario_id: str, method: str, state: dict) -> None:
    """Print a formatted results summary."""
    equiv = state.get("equiv_report")
    if equiv:
        print(f"\n{'='*50}")
        print(f"Scenario {scenario_id} — {method} Results")
        print(f"{'='*50}")
        print(f"Behavioral Equivalence Rate: {equiv.behavioral_equivalence_rate:.1f}%")
        print(f"Tests: {equiv.passed_tests}/{equiv.total_tests} passed")
        print(f"Iterations: {state.get('iteration', 0)}")
        if equiv.failed_tests > 0:
            print(f"\nFailed rules: {equiv.failed_rule_ids()}")
        print(f"{'='*50}\n")


def run_baseline(
    scenario_id: str, baseline: str, fair_eval: bool = False
) -> None:
    """Run a baseline method on a single scenario."""
    _, legacy_code, gold_standard = _load_scenario(scenario_id)

    initial_state = {
        "scenario_id": gold_standard["scenario_id"],
        "legacy_code": legacy_code,
        "gold_standard": gold_standard,
        "iteration": 0,
    }

    if baseline == "sp-llm":
        agent = SinglePromptBaseline()
    elif baseline == "cot-llm":
        agent = ChainOfThoughtBaseline()
    else:
        logger.error("Unknown baseline: %s. Valid: %s", baseline, VALID_BASELINES)
        sys.exit(1)

    state = agent.run(initial_state)

    if fair_eval:
        evaluator = GoldStandardEvaluator()
        report = evaluator.evaluate(
            scenario_id, state["modern_code"], gold_standard
        )
        state["equiv_report"] = report
        state["eval_mode"] = "gold_standard"

    suffix = f"{scenario_id}_{baseline}"
    if fair_eval:
        suffix += "_fair"
    results_dir = Path(RESULTS_DIR) / suffix
    save_results(state, results_dir)

    _print_summary(scenario_id, baseline.upper(), state)


def run_single(
    scenario_id: str,
    no_feedback: bool = False,
    fair_eval: bool = False,
    model_name: str | None = None,
) -> None:
    """Run the full AgentModernize pipeline on a single scenario."""
    import src.config as config_module

    original_max = config_module.MAX_FEEDBACK_ITERATIONS
    if no_feedback:
        config_module.MAX_FEEDBACK_ITERATIONS = 1

    scenario_dir, _, gold_standard = _load_scenario(scenario_id)
    state = run_scenario(scenario_dir, model_name=model_name)

    if fair_eval:
        evaluator = GoldStandardEvaluator()
        report = evaluator.evaluate(
            scenario_id, state["modern_code"], gold_standard
        )
        state["equiv_report"] = report
        state["eval_mode"] = "gold_standard"

    suffix = f"{scenario_id}_no_feedback" if no_feedback else scenario_id
    if fair_eval:
        suffix += "_fair"
    method_label = "AgentModernize (No FB)" if no_feedback else "AgentModernize"

    save_results(state, Path(RESULTS_DIR) / suffix)
    _print_summary(scenario_id, method_label, state)

    config_module.MAX_FEEDBACK_ITERATIONS = original_max


def run_all() -> None:
    """Run the full pipeline on all available scenarios."""
    results_summary = {}

    for scenario_id, dir_name in SCENARIO_MAP.items():
        scenario_dir = Path(BENCHMARK_DIR) / dir_name
        if not scenario_dir.exists():
            logger.warning("Skipping %s — directory not found", scenario_id)
            continue

        try:
            state = run_scenario(scenario_dir)
            save_results(state, Path(RESULTS_DIR) / scenario_id)

            equiv = state.get("equiv_report")
            if equiv:
                results_summary[scenario_id] = {
                    "ber": equiv.behavioral_equivalence_rate,
                    "passed": equiv.passed_tests,
                    "total": equiv.total_tests,
                    "iterations": state.get("iteration", 0),
                }
        except Exception as e:
            logger.error("Scenario %s failed: %s", scenario_id, e)
            results_summary[scenario_id] = {"error": str(e)}

    # Print summary table
    print(f"\n{'='*60}")
    print("AgentModernize — Full Benchmark Results")
    print(f"{'='*60}")
    print(f"{'Scenario':<12} {'BER':<10} {'Tests':<12} {'Iterations':<10}")
    print(f"{'-'*44}")
    for sid, r in results_summary.items():
        if "error" in r:
            print(f"{sid:<12} ERROR: {r['error'][:40]}")
        else:
            print(f"{sid:<12} {r['ber']:.1f}%     {r['passed']}/{r['total']:<8} {r['iterations']}")
    print(f"{'='*60}\n")

    # Save summary
    summary_path = Path(RESULTS_DIR) / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results_summary, indent=2))
    logger.info("Summary saved to %s", summary_path)


def run_fair_eval_all() -> None:
    """Run all methods on all scenarios with fair gold-standard evaluation."""
    methods = ["am", "sp-llm", "cot-llm"]
    results_summary: dict[str, dict[str, dict]] = {}

    for scenario_id, dir_name in SCENARIO_MAP.items():
        scenario_dir = Path(BENCHMARK_DIR) / dir_name
        if not scenario_dir.exists():
            logger.warning("Skipping %s — directory not found", scenario_id)
            continue

        _, legacy_code, gold_standard = _load_scenario(scenario_id)
        evaluator = GoldStandardEvaluator()
        results_summary[scenario_id] = {}

        for method in methods:
            try:
                if method == "am":
                    state = run_scenario(scenario_dir)
                elif method == "sp-llm":
                    agent = SinglePromptBaseline()
                    state = agent.run(
                        {
                            "scenario_id": gold_standard["scenario_id"],
                            "legacy_code": legacy_code,
                            "gold_standard": gold_standard,
                            "iteration": 0,
                        }
                    )
                elif method == "cot-llm":
                    agent = ChainOfThoughtBaseline()
                    state = agent.run(
                        {
                            "scenario_id": gold_standard["scenario_id"],
                            "legacy_code": legacy_code,
                            "gold_standard": gold_standard,
                            "iteration": 0,
                        }
                    )
                else:
                    continue

                report = evaluator.evaluate(
                    scenario_id, state["modern_code"], gold_standard
                )

                results_summary[scenario_id][method] = {
                    "ber": report.behavioral_equivalence_rate,
                    "passed": report.passed_tests,
                    "total": report.total_tests,
                }

                save_dir = Path(RESULTS_DIR) / f"{scenario_id}_{method}_fair"
                state["equiv_report"] = report
                state["eval_mode"] = "gold_standard"
                save_results(state, save_dir)

                logger.info(
                    "%s / %s: %.1f%% (%d/%d)",
                    scenario_id,
                    method,
                    report.behavioral_equivalence_rate,
                    report.passed_tests,
                    report.total_tests,
                )
            except Exception as e:
                logger.error("%s / %s failed: %s", scenario_id, method, e)
                results_summary[scenario_id][method] = {"error": str(e)}

    # Print summary table
    print(f"\n{'='*70}")
    print("Fair Evaluation — Gold-Standard Test Suite")
    print(f"{'='*70}")
    print(f"{'Scenario':<10} {'SP-LLM':<15} {'CoT-LLM':<15} {'AgentMod':<15}")
    print(f"{'-'*55}")
    for sid, methods_data in results_summary.items():
        row = f"{sid:<10}"
        for m in ["sp-llm", "cot-llm", "am"]:
            data = methods_data.get(m, {})
            if "error" in data:
                row += f" {'ERROR':<14}"
            elif "ber" in data:
                row += f" {data['ber']:.1f}% ({data['passed']}/{data['total']})".ljust(15)
            else:
                row += f" {'N/A':<14}"
        print(row)
    print(f"{'='*70}\n")

    summary_path = Path(RESULTS_DIR) / "fair_eval_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results_summary, indent=2))
    logger.info("Fair eval summary saved to %s", summary_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AgentModernize experiments")
    parser.add_argument("--scenario", type=str, help="Scenario ID (e.g., S1)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--baseline", type=str, help="Baseline method (sp-llm or cot-llm)")
    parser.add_argument("--no-feedback", action="store_true", help="Disable feedback loop (ablation)")
    parser.add_argument(
        "--fair-eval",
        action="store_true",
        help="Use gold-standard test suite for fair comparison",
    )
    parser.add_argument(
        "--fair-eval-all",
        action="store_true",
        help="Run all methods on all scenarios with fair evaluation",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="LLM model override (e.g., gpt-4o). Default: gpt-4o-mini",
    )
    args = parser.parse_args()

    if args.fair_eval_all:
        run_fair_eval_all()
    elif args.all:
        run_all()
    elif args.scenario and args.baseline:
        run_baseline(
            args.scenario.upper(), args.baseline.lower(), fair_eval=args.fair_eval
        )
    elif args.scenario:
        run_single(
            args.scenario.upper(),
            no_feedback=args.no_feedback,
            fair_eval=args.fair_eval,
            model_name=args.model,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
