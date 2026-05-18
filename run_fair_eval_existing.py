"""Re-evaluate existing experiment results using gold-standard test suite.

Reads the already-generated modern_code from results/ directories and
evaluates ALL methods against the same gold-standard tests. No new LLM
code-generation calls needed — only test-generation calls.

Usage:
    python run_fair_eval_existing.py
    python run_fair_eval_existing.py --scenario S1 
    python run_fair_eval_existing.py --trials 3
    python run_fair_eval_existing.py --model gpt4o --trials 3
    python run_fair_eval_existing.py --model codex --trials 3
    python run_fair_eval_existing.py --model all --trials 3
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path

from src.config import BENCHMARK_DIR, RESULTS_DIR
from src.evaluation import GoldStandardEvaluator

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

# Per-model folder layouts. Each layout maps a method to a folder pattern
# parameterised by {sid} (the scenario id).
MODEL_LAYOUTS: dict[str, dict[str, str]] = {
    "mini": {
        "am": "{sid}",
        "am_no_fb": "{sid}_no_feedback",
        "sp-llm": "{sid}_sp-llm",
        "cot-llm": "{sid}_cot-llm",
    },
    "gpt4o": {
        "am": "{sid}_gpt4o",
        "am_no_fb": "{sid}_gpt4o_no_feedback",
        "sp-llm": "{sid}_sp-llm_gpt4o",
        "cot-llm": "{sid}_cot-llm_gpt4o",
    },
    "codex": {
        "am": "{sid}_codex",
        "am_no_fb": "{sid}_codex_no_feedback",
        "sp-llm": "{sid}_sp-llm_codex",
        "cot-llm": "{sid}_cot-llm_codex",
    },
}

# Output filename per model. Keep the historical name for "mini" so the README
# and existing tooling that already references fair_eval_summary.json continue
# to work.
SUMMARY_FILENAMES: dict[str, str] = {
    "mini": "fair_eval_summary.json",
    "gpt4o": "fair_eval_summary_gpt4o.json",
    "codex": "fair_eval_summary_codex.json",
}

# Backwards-compat alias; existing callers may import METHOD_DIRS.
METHOD_DIRS = MODEL_LAYOUTS["mini"]


def _find_modern_code(results_dir: Path) -> str | None:
    """Find and read the modern_service.py file in a results directory."""
    for f in results_dir.iterdir():
        if f.name.endswith("_modern_service.py") or f.name == "modern_service.py":
            return f.read_text()
    return None


def _load_gold_standard(scenario_id: str) -> dict:
    """Load gold_standard.json for a scenario."""
    dir_name = SCENARIO_MAP[scenario_id]
    gs_path = Path(BENCHMARK_DIR) / dir_name / "gold_standard.json"
    with gs_path.open() as f:
        return json.load(f)


def run_fair_eval(
    scenario_ids: list[str] | None = None,
    num_trials: int = 1,
    model: str = "mini",
) -> None:
    """Run fair evaluation on existing results for one model layout.

    Generates the test suite ONCE per scenario per trial using the AM (best)
    code as the reference, then runs that identical test suite against every
    method's code. When num_trials > 1, reports mean ± std.

    ``model`` selects which folder layout to evaluate ("mini", "gpt4o", or
    "codex"). The summary JSON is written to a model-specific filename so
    successive runs do not overwrite each other.
    """
    if scenario_ids is None:
        scenario_ids = list(SCENARIO_MAP.keys())

    if model not in MODEL_LAYOUTS:
        raise ValueError(
            f"Unknown model '{model}'. Expected one of {sorted(MODEL_LAYOUTS)}"
        )

    layout = MODEL_LAYOUTS[model]
    evaluator = GoldStandardEvaluator()
    results_base = Path(RESULTS_DIR)
    all_results: dict[str, dict[str, dict]] = {}

    if num_trials > 1:
        trial_bers: dict[str, dict[str, list[float]]] = {}
        for trial in range(num_trials):
            logger.info("=== [%s] TRIAL %d/%d ===", model, trial + 1, num_trials)
            single_results = _run_single_trial(
                scenario_ids, evaluator, results_base, layout
            )
            for sid, methods in single_results.items():
                trial_bers.setdefault(sid, {})
                for method, data in methods.items():
                    trial_bers[sid].setdefault(method, [])
                    ber = data.get("ber", 0.0)
                    trial_bers[sid][method].append(ber)

        for sid in trial_bers:
            all_results[sid] = {}
            for method, bers in trial_bers[sid].items():
                mean_ber = statistics.mean(bers)
                std_ber = statistics.stdev(bers) if len(bers) > 1 else 0.0
                all_results[sid][method] = {
                    "ber_mean": round(mean_ber, 1),
                    "ber_std": round(std_ber, 1),
                    "trials": bers,
                }
    else:
        all_results = _run_single_trial(
            scenario_ids, evaluator, results_base, layout
        )

    _print_summary(scenario_ids, all_results, num_trials, results_base, model, layout)


def run_fair_eval_all_models(
    scenario_ids: list[str] | None = None,
    num_trials: int = 1,
) -> None:
    """Run fair evaluation for every supported model layout, in sequence."""
    for model in MODEL_LAYOUTS:
        logger.info(
            "\n%s\nFair eval for model layout: %s\n%s", "=" * 60, model, "=" * 60
        )
        run_fair_eval(scenario_ids, num_trials=num_trials, model=model)


def _run_single_trial(
    scenario_ids: list[str],
    evaluator: GoldStandardEvaluator,
    results_base: Path,
    layout: dict[str, str],
) -> dict[str, dict[str, dict]]:
    """Execute one complete trial across all scenarios and methods for one layout."""
    all_results: dict[str, dict[str, dict]] = {}
    REFERENCE_ORDER = ["am", "am_no_fb", "sp-llm", "cot-llm"]

    for sid in scenario_ids:
        if sid not in SCENARIO_MAP:
            continue
        gold_standard = _load_gold_standard(sid)
        all_results[sid] = {}

        ref_code = None
        for method in REFERENCE_ORDER:
            dir_name = layout[method].format(sid=sid)
            method_dir = results_base / dir_name
            if method_dir.exists():
                code = _find_modern_code(method_dir)
                if code:
                    ref_code = code
                    logger.info("%s: using %s (%s) as reference", sid, method, dir_name)
                    break

        if ref_code is None:
            logger.warning("No modern code for %s in this layout, skipping", sid)
            continue

        test_code = evaluator.generate_test_code(sid, ref_code, gold_standard)
        if test_code is None:
            logger.error("%s: failed to generate tests, skipping", sid)
            continue

        for method, dir_pattern in layout.items():
            dir_name = dir_pattern.format(sid=sid)
            method_dir = results_base / dir_name
            if not method_dir.exists():
                continue
            modern_code = _find_modern_code(method_dir)
            if modern_code is None:
                continue

            try:
                report = evaluator.evaluate_with_tests(
                    sid, modern_code, test_code, gold_standard=gold_standard
                )
                all_results[sid][method] = {
                    "ber": report.behavioral_equivalence_rate,
                    "passed": report.passed_tests,
                    "total": report.total_tests,
                }
                logger.info(
                    "%s / %s: %.1f%% (%d/%d)",
                    sid,
                    method,
                    report.behavioral_equivalence_rate,
                    report.passed_tests,
                    report.total_tests,
                )
            except Exception as e:
                logger.error("%s / %s failed: %s", sid, method, e)
                all_results[sid][method] = {"error": str(e)}

    return all_results


def _print_summary(
    scenario_ids: list[str],
    all_results: dict,
    num_trials: int,
    results_base: Path,
    model: str,
    layout: dict[str, str],
) -> None:
    """Print and save the results summary table for one model layout."""
    print(f"\n{'=' * 75}")
    title = f"Fair Evaluation — Gold-Standard Test Suite [{model}]"
    if num_trials > 1:
        title += f" ({num_trials} trials, mean ± std)"
    print(title)
    print(f"{'=' * 75}")
    header = f"{'Scenario':<10}"
    for m in layout:
        header += f" {m:<16}"
    print(header)
    print(f"{'-' * 75}")

    for sid in scenario_ids:
        if sid not in all_results:
            continue
        row = f"{sid:<10}"
        for m in layout:
            data = all_results[sid].get(m, {})
            if "error" in data:
                row += f" {'ERROR':<15}"
            elif "ber_mean" in data:
                cell = f"{data['ber_mean']:.1f}±{data['ber_std']:.1f}%"
                row += f" {cell:<15}"
            elif "ber" in data:
                cell = f"{data['ber']:.1f}% ({data['passed']}/{data['total']})"
                row += f" {cell:<15}"
            else:
                row += f" {'—':<15}"
        print(row)
    print(f"{'=' * 75}\n")

    summary_filename = SUMMARY_FILENAMES.get(model, f"fair_eval_summary_{model}.json")
    summary_path = results_base / summary_filename
    summary_path.write_text(json.dumps(all_results, indent=2))
    logger.info("Summary saved to %s", summary_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-evaluate existing results with gold-standard tests"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Scenario ID (e.g., S1). Omit for all scenarios.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Number of trials for statistical rigor (default: 1).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mini",
        choices=["mini", "gpt4o", "codex", "all"],
        help=(
            "Which model's result folders to evaluate. 'mini' uses S{n}/, "
            "'gpt4o' uses S{n}_gpt4o/, 'codex' uses S{n}_codex/, and "
            "'all' runs every model layout in sequence (default: mini)."
        ),
    )
    args = parser.parse_args()

    scenarios = [args.scenario.upper()] if args.scenario else None
    if args.model == "all":
        run_fair_eval_all_models(scenarios, num_trials=args.trials)
    else:
        run_fair_eval(scenarios, num_trials=args.trials, model=args.model)


if __name__ == "__main__":
    main()
