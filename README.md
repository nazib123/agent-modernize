# AgentModernize

**Preserving Business Logic in Legacy System Modernization: A Multi-Agent LLM Framework with Behavioral Specification Graphs**

Legacy modernization is not a translation problem --- it is a behavioral preservation problem. Most tools convert syntax; they lose the business logic buried in decades-old code. AgentModernize decomposes modernization into four agent-handled phases connected through Behavioral Specification Graphs (BSGs), making extracted logic explicit, inspectable, and verifiable before any code is generated.

## Key Results

Reported in the paper from the full fair-evaluation workflow (three models, three trials). A fresh clone does not reproduce these numbers from the short smoke test alone.

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
eval_bsg.py       # BSG extraction quality (S1-S7)
run_experiment.py # Single-scenario generation, baselines, and no-feedback ablation
run_fair_eval_existing.py    # Fair eval for gpt-4o-mini result folders
run_model_comparison.py      # GPT-4o AM generation and mini vs 4o fair comparison
run_full_baseline_comparison.py  # 4o/codex baselines and full method x model matrix
run_codex_comparison.py      # GPT-5.3-codex AM and three-model fair comparison
results/          # Generated outputs (gitignored)
```

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=your-key-here
```

On Windows PowerShell:

```powershell
pip install -r requirements.txt
$env:OPENAI_API_KEY = "your-key-here"
```

## Results folders

Fair evaluation reads only the folder names each script expects.

| Model | AgentModernize | SP-LLM | CoT-LLM | AM (no feedback) |
|-------|----------------|--------|---------|------------------|
| gpt-4o-mini | `S1/` | `S1_sp-llm/` | `S1_cot-llm/` | `S1_no_feedback/` |
| gpt-4o | `S1_gpt4o/` | `S1_sp-llm_gpt4o/` | `S1_cot-llm_gpt4o/` | `S1_gpt4o_no_feedback/` |
| gpt-5.3-codex | `S1_codex/` | `S1_sp-llm_codex/` | `S1_cot-llm_codex/` | see comparison scripts |

`run_fair_eval_existing.py` uses only the **gpt-4o-mini** row. For **gpt-4o** and **gpt-5.3-codex**, use the comparison scripts in the steps below.

`run_experiment.py --all` does **not** apply `--model`; it always writes the default mini layout under `S1/` through `S8/`.

## Evaluation workflow

### 1. Smoke test

```bash
python run_experiment.py --scenario S1
```

This runs the full pipeline on one scenario with the default model (`gpt-4o-mini`). The printed BER is from the internal validator, not the paper's fair gold-standard evaluation.

### 2. GPT-4o-mini generation

AgentModernize on all scenarios:

```bash
python run_experiment.py --all
```

Baselines per scenario:

```bash
python run_experiment.py --scenario S1 --baseline sp-llm
python run_experiment.py --scenario S1 --baseline cot-llm
```

No-feedback ablation:

```bash
python run_experiment.py --scenario S1 --no-feedback
```

Repeat the baseline and no-feedback commands for S2 through S8, or loop in your shell.

### 3. GPT-4o-mini fair evaluation

Run after the mini folders above exist for each scenario you want to score.

```bash
python run_fair_eval_existing.py --trials 3
```

Summary: `results/fair_eval_summary.json`.

### 4. BSG extraction quality

```bash
python eval_bsg.py
```

### 5. GPT-4o

Generate AgentModernize outputs under `*_gpt4o` folders:

```bash
python -c "from run_model_comparison import run_gpt4o_all; run_gpt4o_all()"
```

Generate SP-LLM and CoT-LLM baselines with GPT-4o:

```bash
python -c "from run_full_baseline_comparison import run_baselines_for_model, MODEL_4O; run_baselines_for_model(MODEL_4O, 'gpt4o')"
```

Fair comparison of AgentModernize on mini vs GPT-4o:

```bash
python -c "from run_model_comparison import run_fair_eval_both_models; run_fair_eval_both_models()"
```

Or run the bundled driver:

```bash
python run_model_comparison.py
```

### 6. GPT-5.3-codex and full matrix

```bash
python run_codex_comparison.py
```

For the full method x model matrix (mini, 4o, codex):

```bash
python -c "from run_full_baseline_comparison import run_fair_eval_full_matrix; run_fair_eval_full_matrix()"
```

Or run:

```bash
python run_full_baseline_comparison.py
```

## Results summaries

After evaluation, aggregate BER tables are written under `results/` (gitignored). Per-scenario artifacts live in the subfolders described above (`*_modern_service.py`, `*_bsg.json`, and related files).

| File | Contents |
|------|----------|
| `fair_eval_summary.json` | **gpt-4o-mini** only: AM, no-feedback, SP-LLM, CoT; `--trials` means and standard deviations |
| `model_comparison.json` | **AM only**: gpt-4o-mini vs gpt-4o; one fair-eval pass per scenario |
| `three_model_comparison.json` | **AM only**: mini vs 4o vs gpt-5.3-codex; one pass per scenario |
| `full_matrix_comparison.json` | **SP-LLM, CoT, AM** × **mini, 4o, codex**; one pass per cell |

For **gpt-5.3-codex**, use `three_model_comparison.json` and the **codex** columns in `full_matrix_comparison.json`. `fair_eval_summary.json` and `model_comparison.json` do not include codex.

`eval_bsg.py` prints BSG precision and recall to the terminal for **S1–S7** mini AM folders (`results/S{n}/`); it does not write a summary JSON file.

## Interpreting results

The **Key Results** table is from the paper's published run. A local reproduction follows the same scripts but will not match those means exactly: generations differ across runs, and fair evaluation uses LLM-generated pytest harnesses that can vary per scenario.

- **Validator BER** from `run_experiment.py` is not the same as **fair BER** from the gold-standard evaluator.
- On **gpt-4o-mini**, the 3-trial fair eval is the right place to compare AM against SP-LLM and CoT on the same harness.
- Use `full_matrix_comparison.json` for cross-model, cross-method averages; treat **gpt-4o** cells as unreliable when pytest fails during collection or on generated Pydantic validators (for example **S8**), not only when behavioral assertions fail.
- Qualitative claims (baselines often at 0% on mini, hard scenarios such as **S5** / **S7** / **S8**, codex spikes on selected scenarios) may hold even when headline means differ.

## Citation

If you use AgentModernize in your research, please cite:

```bibtex
@article{sheikh2026agentmodernize,
  title={AgentModernize: Preserving Business Logic in Legacy Modernization with Multi-Agent LLMs and Behavioral Specification Graphs},
  author={Ahmed, Sheikh Nazib},
  year={2026}
}
```

## License

MIT
