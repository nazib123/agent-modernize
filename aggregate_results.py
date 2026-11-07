"""Aggregate per-scenario fair-eval summaries into paper tables.

Reads results/fair_eval_summary_S{n}.json (written by run_fair_eval_existing.py
--scenario S{n}) and prints per-scenario BER means, averages, and non-zero counts.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from src.config import RESULTS_DIR

METHODS = ["sp-llm", "cot-llm", "fb-llm", "am_no_fb", "am", "am_ra"]
LABELS = {"sp-llm": "SP-LLM", "cot-llm": "CoT-LLM", "fb-llm": "FB-LLM", "am_no_fb": "AM-NoFB", "am": "AM", "am_ra": "AM-RA"}


def load() -> dict[str, dict[str, dict]]:
    out = {}
    for sid in [f"S{i}" for i in range(1, 9)]:
        p = Path(RESULTS_DIR) / f"fair_eval_summary_{sid}.json"
        if p.exists():
            out.update(json.loads(p.read_text()))
    return out


def main() -> None:
    data = load()
    sids = sorted(data)
    print(f"{'ID':<4}" + "".join(f"{LABELS[m]:>10}" for m in METHODS))
    means: dict[str, list[float]] = {m: [] for m in METHODS}
    for sid in sids:
        row = f"{sid:<4}"
        for m in METHODS:
            d = data[sid].get(m)
            v = d["ber_mean"] if d and "ber_mean" in d else float("nan")
            if d and "ber_mean" in d:
                means[m].append(v)
            row += f"{v:>10.1f}"
        print(row)
    print(f"{'Avg':<4}" + "".join(f"{statistics.mean(means[m]):>10.1f}" if means[m] else f"{'-':>10}" for m in METHODS))
    print(f"{'NZ':<4}" + "".join(f"{sum(v > 0 for v in means[m])}/{len(means[m])}".rjust(10) for m in METHODS))
    print("\nNon-zero sigma cells:")
    for m in METHODS:
        cells = [f"{sid} ({data[sid][m]['ber_std']})" for sid in sids if m in data[sid] and data[sid][m].get("ber_std", 0) > 0]
        print(f"  {LABELS[m]}: {', '.join(cells) or 'none'}")
    print("\nPer-scenario trials (raw):")
    for sid in sids:
        for m in METHODS:
            d = data[sid].get(m)
            if d and d.get("ber_mean", 0) > 0:
                print(f"  {sid} {LABELS[m]}: {[round(t, 1) for t in d['trials']]}")


if __name__ == "__main__":
    main()
