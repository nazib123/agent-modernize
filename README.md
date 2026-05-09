# AgentModernize

**Preserving Business Logic in Legacy System Modernization: A Multi-Agent LLM Framework with Behavioral Specification Graphs**

Legacy modernization is not a translation problem --- it is a behavioral preservation problem. Most tools convert syntax; they lose the business logic buried in decades-old code. AgentModernize decomposes modernization into four agent-handled phases connected through Behavioral Specification Graphs (BSGs), making extracted logic explicit, inspectable, and verifiable before any code is generated.

## Key Results

Evaluated on **LegacyModernize-8** (8 scenarios, COBOL/PL/SQL, telecom + banking) with three models:

| Model | Mean BER | Best Scenario | Cost (input/output per 1M tokens) |
|-------|----------|---------------|-----------------------------------|
| GPT-4o-mini | 6.2% | S1: 25.0% | $0.15 / $0.60 |
| GPT-4o | 5.6% | S8: 26.7% | $2.50 / $10.00 |
| GPT-5.3-codex | 11.0% | S5: 75.0% | $1.75 / $14.00 |

- **With GPT-4o-mini**, AgentModernize is the only method to pass any gold-standard tests (all baselines score 0.0%).
- **With GPT-5.3-codex**, a single prompt (SP-LLM) hits 20.4% mean BER --- beating the full pipeline's 11.0%. The pipeline overhead hurts when the model is strong enough.
- **BSG extraction quality**: 91.2% recall, 89.7% precision --- the bottleneck is code generation, not rule extraction.

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
  Agent 4: Validator        -------| (feedback loop)
        |
  Equivalence Report
```

## Project Structure

```
src/              # Pipeline implementation (4 agents + orchestrator)
benchmark/        # LegacyModernize-8 scenarios (S1-S8, COBOL/PL/SQL + gold-standard tests)
paper/            # Research paper (LaTeX + Markdown)
eval_bsg.py       # BSG extraction quality evaluation
run_experiment.py # Single-scenario experiment runner
run_fair_eval_existing.py    # Fair evaluation across all scenarios
run_full_baseline_comparison.py  # SP-LLM / CoT-LLM / AM comparison
run_model_comparison.py      # GPT-4o-mini vs GPT-4o vs GPT-5.3-codex
run_codex_comparison.py      # Frontier model crossover study
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY=your-key-here

# Run a single scenario
python run_experiment.py --scenario S1

# Run full fair evaluation (all 8 scenarios, 3 trials)
python run_fair_eval_existing.py

# Run 3-model comparison
python run_model_comparison.py
```

## Citation

If you use AgentModernize in your research, please cite:

```bibtex
@article{sheikh2026agentmodernize,
  title={Preserving Business Logic in Legacy System Modernization: A Multi-Agent LLM Framework with Behavioral Specification Graphs},
  author={Sheikh, Nazib},
  year={2026}
}
```

## License

MIT
