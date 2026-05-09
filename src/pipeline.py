"""AgentModernize Pipeline — LangGraph orchestration of all 4 agents.

Chains Legacy Analyzer → Spec Generator → Transformer → Validator
with a feedback loop that re-invokes the Transformer when the Validator
detects behavioral divergences.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.legacy_analyzer import LegacyAnalyzerAgent
from src.agents.spec_generator import SpecGeneratorAgent
from src.agents.transformer import ModernizationTransformerAgent
from src.agents.validator import EquivalenceValidatorAgent
import src.config as config

logger = logging.getLogger(__name__)


# Module-level model override — set before calling run_scenario()
_MODEL_OVERRIDE: str | None = None


def _analyze(state: dict[str, Any]) -> dict[str, Any]:
    """Node 1: Legacy Analyzer."""
    kwargs: dict[str, Any] = {}
    if _MODEL_OVERRIDE:
        kwargs["model_name"] = _MODEL_OVERRIDE
    agent = LegacyAnalyzerAgent(**kwargs)
    return agent.run(state)


def _specify(state: dict[str, Any]) -> dict[str, Any]:
    """Node 2: Specification Generator."""
    kwargs: dict[str, Any] = {}
    if _MODEL_OVERRIDE:
        kwargs["model_name"] = _MODEL_OVERRIDE
    agent = SpecGeneratorAgent(**kwargs)
    return agent.run(state)


def _transform(state: dict[str, Any]) -> dict[str, Any]:
    """Node 3: Modernization Transformer."""
    kwargs: dict[str, Any] = {}
    if _MODEL_OVERRIDE:
        kwargs["model_name"] = _MODEL_OVERRIDE
    agent = ModernizationTransformerAgent(**kwargs)
    return agent.run(state)


def _validate(state: dict[str, Any]) -> dict[str, Any]:
    """Node 4: Equivalence Validator."""
    kwargs: dict[str, Any] = {}
    if _MODEL_OVERRIDE:
        kwargs["model_name"] = _MODEL_OVERRIDE
    agent = EquivalenceValidatorAgent(**kwargs)
    state = agent.run(state)
    state["iteration"] = state.get("iteration", 0) + 1
    return state


def _should_retry(state: dict[str, Any]) -> str:
    """Decide whether to re-enter the feedback loop or finish."""
    equiv_report = state.get("equiv_report")
    iteration = state.get("iteration", 0)

    if equiv_report is None:
        return "end"

    if equiv_report.all_passed:
        logger.info("All tests passed — pipeline complete.")
        return "end"

    if iteration >= config.MAX_FEEDBACK_ITERATIONS:
        logger.warning(
            "Max iterations (%d) reached with %.1f%% equivalence. Stopping.",
            config.MAX_FEEDBACK_ITERATIONS,
            equiv_report.behavioral_equivalence_rate,
        )
        return "end"

    logger.info(
        "Iteration %d: %.1f%% equivalence — retrying transformer.",
        iteration,
        equiv_report.behavioral_equivalence_rate,
    )
    return "retry"


def build_pipeline() -> StateGraph:
    """Construct the AgentModernize LangGraph pipeline.

    Pipeline flow:
        analyze → specify → transform → validate
                                ↑            │
                                └── retry ───┘
    """
    workflow = StateGraph(dict)

    workflow.add_node("analyze", _analyze)
    workflow.add_node("specify", _specify)
    workflow.add_node("transform", _transform)
    workflow.add_node("validate", _validate)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "specify")
    workflow.add_edge("specify", "transform")
    workflow.add_edge("transform", "validate")

    workflow.add_conditional_edges(
        "validate",
        _should_retry,
        {
            "retry": "transform",
            "end": END,
        },
    )

    return workflow.compile()


def run_scenario(
    scenario_dir: str | Path,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Run the full AgentModernize pipeline on a single benchmark scenario.

    Args:
        scenario_dir: Path to a benchmark scenario folder containing
                      legacy_code.cbl and gold_standard.json.
        model_name: Optional LLM model override (e.g., 'gpt-4o').

    Returns:
        Final pipeline state with all artifacts.
    """
    global _MODEL_OVERRIDE
    _MODEL_OVERRIDE = model_name
    scenario_path = Path(scenario_dir)
    legacy_code_path = scenario_path / "legacy_code.cbl"
    gold_standard_path = scenario_path / "gold_standard.json"

    legacy_code = legacy_code_path.read_text()

    with gold_standard_path.open() as f:
        gold_standard = json.load(f)

    scenario_id = gold_standard["scenario_id"]

    logger.info("=" * 60)
    logger.info("Running AgentModernize on scenario: %s", scenario_id)
    logger.info("Scenario: %s", gold_standard["scenario_name"])
    logger.info("=" * 60)

    initial_state = {
        "scenario_id": scenario_id,
        "legacy_code": legacy_code,
        "legacy_code_path": str(legacy_code_path),
        "gold_standard": gold_standard,
        "iteration": 0,
    }

    pipeline = build_pipeline()
    final_state = pipeline.invoke(initial_state)

    return final_state


def save_results(state: dict[str, Any], output_dir: str | Path) -> None:
    """Save pipeline artifacts to the results directory."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    scenario_id = state["scenario_id"]

    # Save BRI
    if state.get("business_rules"):
        bri_path = out_path / f"{scenario_id}_bri.json"
        bri_path.write_text(json.dumps(state["business_rules"].to_dict(), indent=2))

    # Save BSG
    if state.get("bsg"):
        bsg_path = out_path / f"{scenario_id}_bsg.json"
        bsg_path.write_text(json.dumps(state["bsg"].to_dict(), indent=2))

    # Save modern code
    if state.get("modern_code"):
        code_path = out_path / f"{scenario_id}_modern_service.py"
        code_path.write_text(state["modern_code"])

    # Save tests
    if state.get("modern_tests"):
        test_path = out_path / f"{scenario_id}_tests.py"
        test_path.write_text(state["modern_tests"])

    # Save equivalence report
    if state.get("equiv_report"):
        report_path = out_path / f"{scenario_id}_equiv_report.json"
        report_path.write_text(json.dumps(state["equiv_report"].to_dict(), indent=2))

    logger.info("Results saved to %s", out_path)
