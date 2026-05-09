import os
import json

base = os.path.dirname(os.path.abspath(__file__))
names = {
    "S1": "S1_order_validation", "S2": "S2_billing_dispute",
    "S3": "S3_service_activation", "S4": "S4_circuit_inventory",
    "S5": "S5_fault_escalation", "S6": "S6_contract_renewal",
    "S7": "S7_account_migration",
}

for sid, dn in names.items():
    gs = json.load(open(f"{base}/benchmark/{dn}/gold_standard.json"))
    if "rules" in gs:
        gold = {r["id"] for r in gs["rules"]}
    else:
        br = gs.get("business_rules", {})
        gold = {r["id"] for r in br.get("explicit", []) + br.get("implicit", [])}

    try:
        bri = json.load(open(f"{base}/results/{sid}/{sid}_bri.json"))
        bi = {r["id"] for r in bri.get("rules", [])}
    except Exception:
        bi = set()

    try:
        bsg = json.load(open(f"{base}/results/{sid}/{sid}_bsg.json"))
        bsi = set()
        for n in bsg.get("nodes", []):
            for rid in n.get("business_rule_ids", []):
                bsi.add(rid)
    except Exception:
        bsi = set()

    br_recall = len(bi & gold) / len(gold) * 100 if gold else 0
    br_prec = len(bi & gold) / len(bi) * 100 if bi else 0
    bs_recall = len(bsi & gold) / len(gold) * 100 if gold else 0
    bs_prec = len(bsi & gold) / len(bsi) * 100 if bsi else 0

    print(f"{sid}: gold={len(gold)} | BRI:{len(bi)} P={br_prec:.0f}% R={br_recall:.0f}% | BSG:{len(bsi)} P={bs_prec:.0f}% R={bs_recall:.0f}%")
    missed = sorted(gold - bsi)
    if missed:
        print(f"   missed from BSG: {missed}")
