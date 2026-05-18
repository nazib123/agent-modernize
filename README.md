# AgentModernize

**Preserving Business Logic in Legacy Modernization with Multi-Agent LLMs and Behavioral Specification Graphs**

AgentModernize is a multi-agent LLM framework that treats legacy modernization as a behavioral preservation problem. Four specialized agents handle extraction, specification, code generation, and equivalence validation, connected through **Behavioral Specification Graphs (BSGs)** that make extracted business logic explicit and inspectable before any code is generated.

For evaluation methodology, BER tables, and discussion, see **our paper (PDF)** on **arXiv**: **https://arxiv.org/abs/XXXX.XXXXXX** — substitute your real manuscript ID after submission. This repository implements the evaluation protocol described in that paper.

## Architecture

```
Legacy Artifact Bundle
        |
  Agent 1: Legacy Analyzer --> Business Rule Inventory
        |
  Agent 2: Spec Generator  --> Behavioral Specification Graph (BSG)  [trust boundary]
        |
  Agent 3: Transformer     --> Modernized Service
        |                          ^
  Agent 4: Validator        -------| (feedback loop, up to 3 iterations)
        |
  Equivalence Report
```

## Benchmark: LegacyModernize-8

Eight legacy modernization scenarios (COBOL / PL-SQL) spanning telecom and banking domains, each with:

- Legacy source code (100–310 LOC)
- Gold-standard behavioral specs (**curated; AI-assisted drafting, human-reviewed**)
- Withheld behavioral test suites for fair evaluation

## Project Structure

```
src/              # Pipeline implementation (4 agents + orchestrator)
benchmark/        # LegacyModernize-8 scenarios (S1–S8, COBOL/PL-SQL + gold-standard tests)
eval_bsg.py       # BSG extraction quality evaluation
run_experiment.py # Single-scenario experiment runner
run_fair_eval_existing.py    # Fair evaluation across scenarios (existing `results/` layouts)
run_full_baseline_comparison.py  # SP-LLM / CoT-LLM / AM comparison
run_model_comparison.py      # GPT-4o-mini vs GPT-4o vs GPT-5.3-codex
run_codex_comparison.py      # Frontier model study
```
## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY=your-key-here

# Run a single scenario
python run_experiment.py --scenario S1

# Re-run fair evaluation on existing result folders (recommended for paper-style tables:
# all 8 scenarios, 3 trials, all model layouts mini / gpt4o / codex)
python run_fair_eval_existing.py --model all --trials 3

# Or: run AM + baselines + fair eval in one driver (single pass per cell; default mini layout)
python run_experiment.py --fair-eval-all

# Run 3-model comparison
python run_model_comparison.py
```

On Windows PowerShell:

```powershell
pip install -r requirements.txt
$env:OPENAI_API_KEY = "your-key-here"
```

## Reproducibility

| Item | Details |
|------|---------|
| **Python** | 3.11 |
| **Core libraries** | LangGraph, pytest, OpenAI SDK |
| **Models tested** | GPT-4o-mini, GPT-4o, GPT-5.3-codex |
| **Temperature** | 0.2 (extraction), 0.0 (generation / evaluation) |
| **Trials** | 3 per scenario per method (when using `run_fair_eval_existing.py --trials 3`) |
| **Total API cost** | &lt; $15 for full evaluation suite (approximate; varies with snapshot and usage) |

## Citation

If you use AgentModernize or LegacyModernize-8 in your research, please cite:

```bibtex
@article{ahmed2026agentmodernize,
  title={AgentModernize: Preserving Business Logic in Legacy Modernization with Multi-Agent LLMs and Behavioral Specification Graphs},
  author={Ahmed, Sheikh Nazib and Galib, Marnim},
  year={2026}
}
```

## License

MIT
