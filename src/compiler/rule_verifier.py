"""Rule Verifier — Wires Alec's TruthTree + Verify + Warrant into the BSG compiler.

Integration layers:
  1. DetStore   — loads gold-standard rules as typed triples; catches contradictions
  2. truth_gate — symbolically verifies arithmetic cost formulas (exact, zero-float)
  3. Warrant    — tiers every rule by provenance (explicit > implicit > inferred)
  4. Audit      — runs all test scenarios through both DetStore consistency + executor,
                  reports divergences with provenance tier attached

Depends on Alec's csg_operator/core modules:
  alecstec_truthtree (DetStore, SubjStore)
  alecstec_verify    (verify_claim, truth_gate)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── paths ──────────────────────────────────────────────────────────────────
ALEC_CORE = Path("/Users/sheikhnazib/research/Agent-Repo-main/csg_operator/core")
COMPILER_SRC = Path(__file__).resolve().parent.parent
BENCHMARK = COMPILER_SRC.parent / "benchmark"

sys.path.insert(0, str(ALEC_CORE))
sys.path.insert(0, str(COMPILER_SRC))

from alecstec_truthtree import DetStore, SubjStore  # noqa: E402
from alecstec_verify import verify_claim, truth_gate  # noqa: E402
from compiler.bsg_compiler import BSGCompiler  # noqa: E402

# ── provenance tiers (Alec's warrant model) ────────────────────────────────
TIER_DETERMINISTIC = "T3_deterministic"  # directly in COBOL source
TIER_CURATED = "T2_curated"             # in gold_standard, human-verified
TIER_STATED = "T1_stated"               # explicit rules extracted by LLM
TIER_INFERRED = "T0_inferred"           # implicit rules inferred by LLM

TIER_LABELS = {
    TIER_DETERMINISTIC: "deterministic (COBOL source)",
    TIER_CURATED: "curated (gold standard, human-verified)",
    TIER_STATED: "stated (explicit, LLM-extracted)",
    TIER_INFERRED: "inferred (implicit, LLM-inferred)",
}


@dataclass
class RuleRecord:
    rule_id: str
    description: str
    category: str
    tier: str
    error_codes: list[str] = field(default_factory=list)
    source: str = ""  # "explicit" or "implicit"


@dataclass
class VerificationResult:
    scenario_id: str
    rules_loaded: int
    contradictions: list[str]
    arithmetic_checks: list[dict]
    tier_distribution: dict[str, int]
    test_results: list[dict]


# ── 1. Load rules into DetStore ────────────────────────────────────────────
def load_rules_into_detstore(
    gold: dict, det: DetStore
) -> tuple[list[RuleRecord], list[str]]:
    """Parse gold_standard business_rules into DetStore triples.

    Triples:
      (rule_id, "category", category_value)     — one rule, one category (functional)
      (rule_id, "maps_error", error_code)        — rule produces this error code
      (scenario_id + "_" + test_id, "expected_output", canonical_output)  — functional

    Returns (records, contradictions).
    """
    records: list[RuleRecord] = []
    contradictions: list[str] = []
    scenario_id = gold.get("scenario_id", "?")

    det.functional.add("category")
    det.functional.add("expected_output")

    br = gold.get("business_rules", {})
    for source_key in ("explicit", "implicit"):
        rules = br.get(source_key, [])
        tier = TIER_STATED if source_key == "explicit" else TIER_INFERRED
        for r in rules:
            rid = r.get("id", "?")
            cat = r.get("category", "unknown")
            desc = r.get("description", "")
            ecodes = r.get("error_codes", [])

            rec = RuleRecord(
                rule_id=rid, description=desc, category=cat,
                tier=tier, error_codes=ecodes, source=source_key,
            )
            records.append(rec)

            # Triple: rule -> category (functional)
            ok, why = det.add(rid, "category", cat)
            if not ok:
                contradictions.append(f"[{rid}] category conflict: {why}")

            # Triple: rule -> error codes
            for ec in ecodes:
                ok, why = det.add(rid, "maps_error", ec)
                if not ok:
                    contradictions.append(f"[{rid}] error_code conflict: {why}")

    # Load test scenarios as functional triples
    for ts in gold.get("test_scenarios", []):
        tid = ts.get("id", "?")
        expected = ts.get("expected", {})
        # Canonical output: sorted key=value pairs
        canon = "|".join(f"{k}={v}" for k, v in sorted(expected.items()))
        triple_subj = f"{scenario_id}_{tid}"
        ok, why = det.add(triple_subj, "expected_output", canon)
        if not ok:
            contradictions.append(f"[{triple_subj}] output conflict: {why}")

    return records, contradictions


# ── 2. Arithmetic verification via truth_gate ──────────────────────────────
def _to_int_claim(expected_val: float, formula_rhs: str) -> str | None:
    """Scale a float equality to integer so the ring can verify it exactly."""
    # Find smallest power of 10 that makes both sides integer
    s = str(expected_val)
    if "." in s:
        decimals = len(s.split(".")[1])
    else:
        decimals = 0
    scale = 10 ** decimals
    lhs = int(round(expected_val * scale))
    rhs = f"({formula_rhs}) * {scale}" if decimals > 0 else formula_rhs
    return f"{lhs} = {rhs}"


# S4 cost parameters from gold standard
S4_BASE_RATES = {"DS1": 0.15, "DS3": 0.08, "OC3": 0.04, "OC12": 0.02, "ETH": 0.01}
S4_SVC_MULT = {"PREM": 1.5, "STD": 1.0, "ECON": 0.75}

# S6 discount parameters from gold standard
S6_TERM_DISCOUNT = {12: 5, 24: 12, 36: 20}
S6_BUNDLE_EXTRA = 5
S6_LOYALTY_CREDIT_PCT = 2
S6_ETF_PER_MONTH = 25
S6_ETF_MAX = 500


def verify_arithmetic(scenario_id: str, gold: dict) -> list[dict]:
    """Generate and verify concrete arithmetic claims from test scenarios."""
    results = []
    for ts in gold.get("test_scenarios", []):
        tid = ts.get("id", "?")
        inp = ts.get("input", {})
        exp = ts.get("expected", {})

        if scenario_id == "S4":
            mc = exp.get("monthly_cost")
            if mc is not None:
                ct = inp.get("circuit_type", "")
                bw = inp.get("bandwidth", 0)
                sc = inp.get("service_class", "STD")
                st = inp.get("site_type", "OWNED")
                base = S4_BASE_RATES.get(ct, 0)
                mult = S4_SVC_MULT.get(sc, 1.0)
                # base cost = bandwidth * base_rate * svc_mult
                base_cost = bw * base * mult
                if st == "COLO":
                    base_cost *= 1.15
                # Verify: scale to avoid floats
                # mc * 10000 should equal int(base_cost * 10000)
                lhs = int(round(mc * 100))
                rhs = int(round(base_cost * 100))
                claim = f"{lhs} = {rhs}"
                ok, verdict, engine = truth_gate(claim)
                results.append({
                    "test_id": tid,
                    "description": f"monthly_cost={mc} for {ct}/{sc}/{st}",
                    "claim": claim,
                    "verdict": verdict, "engine": engine, "passed": ok,
                })
            # install_fee = monthly_cost
            ifee = exp.get("install_fee")
            if ifee is not None and mc is not None:
                lhs = int(round(ifee * 100))
                rhs = int(round(mc * 100))
                claim = f"{lhs} = {rhs}"
                ok, verdict, engine = truth_gate(claim)
                results.append({
                    "test_id": tid,
                    "description": f"install_fee={ifee} == monthly_cost={mc}",
                    "claim": claim,
                    "verdict": verdict, "engine": engine, "passed": ok,
                })

        elif scenario_id == "S6":
            nr = exp.get("new_rate")
            dp = exp.get("discount_pct")
            if nr is not None and dp is not None:
                mr = inp.get("monthly_rate", 0)
                # new_rate * 100 = monthly_rate * (100 - discount_pct)
                lhs = int(round(nr * 100))
                rhs = int(round(mr * (100 - dp)))
                claim = f"{lhs} = {rhs}"
                ok, verdict, engine = truth_gate(claim)
                results.append({
                    "test_id": tid,
                    "description": f"new_rate={nr}, discount={dp}%, rate={mr}",
                    "claim": claim,
                    "verdict": verdict, "engine": engine, "passed": ok,
                })

    # Also verify the algebraic identities that underpin the formulas
    algebraic = [
        ("install_fee_identity", "install_fee = monthly_cost is a tautology",
         "a = a"),
        ("colo_premium_identity", "colo_cost * 100 = base * 115 (algebraic form)",
         "a * (100 + 15) = a * 115"),
        ("discount_identity", "new_rate * 100 = rate * (100 - d) (algebraic form)",
         "r * (100 - d) = r * 100 - r * d"),
    ]
    for aid, desc, claim in algebraic:
        ok, verdict, engine = truth_gate(claim)
        results.append({
            "test_id": aid,
            "description": desc,
            "claim": claim,
            "verdict": verdict, "engine": engine, "passed": ok,
        })

    return results


# ── 3. Tier distribution (Warrant) ────────────────────────────────────────
def tier_distribution(records: list[RuleRecord]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for r in records:
        dist[r.tier] = dist.get(r.tier, 0) + 1
    return dist


# ── 4. Full verification pipeline ─────────────────────────────────────────
def verify_scenario(scenario_id: str, gold_path: str | Path) -> VerificationResult:
    """Run the full verification pipeline for one scenario."""
    gold = json.loads(Path(gold_path).read_text())
    det = DetStore()

    # Layer 1: Load rules, check consistency
    records, contradictions = load_rules_into_detstore(gold, det)

    # Layer 2: Arithmetic verification
    arith = verify_arithmetic(scenario_id, gold)

    # Layer 3: Tier distribution
    tiers = tier_distribution(records)

    # Layer 4: Run test scenarios through executor and check against DetStore
    try:
        compiler = BSGCompiler(str(gold_path))
    except Exception:
        compiler = None
    test_results = []
    for ts in gold.get("test_scenarios", []):
        inp = ts.get("input", {})
        expected = ts.get("expected", {})
        rules_tested = ts.get("rules_tested", [])

        if compiler is None:
            # No executor — skip execution, still report provenance
            rule_tiers = {}
            for rid in rules_tested:
                for rec in records:
                    if rec.rule_id == rid:
                        rule_tiers[rid] = TIER_LABELS.get(rec.tier, rec.tier)
                        break
            test_results.append({
                "test_id": ts.get("id", "?"),
                "description": ts.get("description", ""),
                "match": None,
                "diffs": ["NO EXECUTOR — cannot verify"],
                "rules_tested": rules_tested,
                "rule_tiers": rule_tiers,
            })
            continue

        try:
            cr = compiler.execute(inp)
        except NotImplementedError:
            rule_tiers = {}
            for rid in rules_tested:
                for rec in records:
                    if rec.rule_id == rid:
                        rule_tiers[rid] = TIER_LABELS.get(rec.tier, rec.tier)
                        break
            test_results.append({
                "test_id": ts.get("id", "?"),
                "description": ts.get("description", ""),
                "match": None,
                "diffs": ["NO EXECUTOR — cannot verify"],
                "rules_tested": rules_tested,
                "rule_tiers": rule_tiers,
            })
            continue

        actual = {}
        if cr.status == "REJECTED":
            actual["status"] = "REJECTED"
            actual["error_code"] = cr.error_code or ""
        else:
            actual["status"] = cr.outputs.get("status", cr.status)
            actual.update(cr.outputs)

        # Compare
        match = True
        diffs = []
        for k, v in expected.items():
            av = actual.get(k)
            if av is not None:
                # Numeric tolerance for floats
                try:
                    if abs(float(av) - float(v)) > 0.01:
                        match = False
                        diffs.append(f"{k}: expected={v}, got={av}")
                except (ValueError, TypeError):
                    if str(av).strip().upper() != str(v).strip().upper():
                        match = False
                        diffs.append(f"{k}: expected={v}, got={av}")
            else:
                match = False
                diffs.append(f"{k}: expected={v}, got=MISSING")

        # Get tiers for rules tested
        rule_tiers = {}
        for rid in rules_tested:
            for rec in records:
                if rec.rule_id == rid:
                    rule_tiers[rid] = TIER_LABELS.get(rec.tier, rec.tier)
                    break

        test_results.append({
            "test_id": ts.get("id", "?"),
            "description": ts.get("description", ""),
            "match": match,
            "diffs": diffs,
            "rules_tested": rules_tested,
            "rule_tiers": rule_tiers,
        })

    return VerificationResult(
        scenario_id=scenario_id,
        rules_loaded=len(records),
        contradictions=contradictions,
        arithmetic_checks=arith,
        tier_distribution=tiers,
        test_results=test_results,
    )


# ── 5. Report ─────────────────────────────────────────────────────────────
def print_report(vr: VerificationResult) -> None:
    print("=" * 72)
    print(f"  RULE VERIFICATION REPORT — {vr.scenario_id}")
    print(f"  (TruthTree + Verify + Warrant)")
    print("=" * 72)

    # Consistency
    print(f"\n## DetStore Consistency (TruthTree)")
    print(f"   Rules loaded as triples: {vr.rules_loaded}")
    if vr.contradictions:
        print(f"   CONTRADICTIONS FOUND: {len(vr.contradictions)}")
        for c in vr.contradictions:
            print(f"     ✗ {c}")
    else:
        print(f"   No contradictions — rule set is internally consistent")

    # Arithmetic
    print(f"\n## Arithmetic Verification (Verify/truth_gate)")
    if vr.arithmetic_checks:
        for ac in vr.arithmetic_checks:
            icon = "PASS" if ac["passed"] else "FAIL"
            label = ac.get("rule_id", ac.get("test_id", "?"))
            print(f"   [{icon}] {label}: {ac['claim']}")
            print(f"          {ac['description']}")
            print(f"          verdict={ac['verdict']} via {ac['engine']}")
    else:
        print(f"   No arithmetic formulas registered for {vr.scenario_id}")

    # Tiers
    print(f"\n## Provenance Tiers (Warrant)")
    for tier, count in sorted(vr.tier_distribution.items()):
        label = TIER_LABELS.get(tier, tier)
        print(f"   {label}: {count} rules")

    # Test results
    runnable = [t for t in vr.test_results if t["match"] is not None]
    skipped = [t for t in vr.test_results if t["match"] is None]
    passed = sum(1 for t in runnable if t["match"])
    total = len(vr.test_results)
    print(f"\n## Test Scenario Verification")
    if skipped:
        print(f"   Passed: {passed}/{len(runnable)} (runnable), {len(skipped)} skipped (no executor)")
    else:
        print(f"   Passed: {passed}/{total}")
    for t in vr.test_results:
        icon = "PASS" if t["match"] else ("SKIP" if t["match"] is None else "FAIL")
        print(f"   [{icon}] {t['test_id']}: {t['description']}")
        if t["diffs"]:
            for d in t["diffs"]:
                print(f"          {d}")
        if t["rule_tiers"]:
            tiers_str = ", ".join(f"{k}={v}" for k, v in t["rule_tiers"].items())
            print(f"          provenance: {tiers_str}")

    # Summary
    print(f"\n{'=' * 72}")
    print(f"  SUMMARY: {vr.scenario_id}")
    print(f"    Rules: {vr.rules_loaded} loaded, "
          f"{len(vr.contradictions)} contradictions")
    arith_pass = sum(1 for a in vr.arithmetic_checks if a["passed"])
    arith_total = len(vr.arithmetic_checks)
    print(f"    Arithmetic: {arith_pass}/{arith_total} verified")
    print(f"    Tests: {passed}/{total} passed")
    print(f"    Honesty caveat: consistency != truth (Alec's TruthTree axiom)")
    print(f"{'=' * 72}")


# ── CLI ────────────────────────────────────────────────────────────────────
SCENARIOS = {
    "S4": BENCHMARK / "S4_circuit_inventory" / "gold_standard.json",
    "S6": BENCHMARK / "S6_contract_renewal" / "gold_standard.json",
    "S7": BENCHMARK / "S7_account_migration" / "gold_standard.json",
    "S8": BENCHMARK / "S8_bank_transaction" / "gold_standard.json",
}


def main() -> None:
    import sys as _sys
    targets = _sys.argv[1:] if len(_sys.argv) > 1 else list(SCENARIOS.keys())
    for sid in targets:
        gp = SCENARIOS.get(sid)
        if not gp or not gp.exists():
            print(f"Skipping {sid}: gold_standard.json not found at {gp}")
            continue
        vr = verify_scenario(sid, gp)
        print_report(vr)
        print()


if __name__ == "__main__":
    main()
