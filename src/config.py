"""Configuration constants for AgentModernize."""

from pathlib import Path

# LLM Settings
DEFAULT_MODEL = "gpt-4o-mini"
TEMPERATURE_EXTRACTION = 0.2
TEMPERATURE_GENERATION = 0.0

# Pipeline Settings
MAX_FEEDBACK_ITERATIONS = 3

# Benchmark paths (absolute so script works from any directory)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = str(_PROJECT_ROOT / "benchmark")
RESULTS_DIR = str(_PROJECT_ROOT / "results")
