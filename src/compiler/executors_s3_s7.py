"""Deterministic executors for S3-S7, compiled directly from COBOL sources.

Each executor reads the COBOL logic line-by-line and translates guards + actions
into exact Python with Decimal arithmetic. Zero LLM involvement.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from compiler.models import CompiledRule, CompilationResult


def _d(val: Any) -> Decimal:
    """Convert to Decimal safely."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    return Decimal("0")


# ── S3: Service Activation & Provisioning ────────────────────────────────────

def execute_s3(rules: list[CompiledRule], state: dict, result: CompilationResult) -> CompilationResult:
    """Compiled from S3 COBOL lines 64-274."""
    service_type = state.get("service_type", "")
    port_type = state.get("port_type", "")
    bandwidth = int(state.get("bandwidth_mbps", 0))
    customer_tier = state.get("customer_tier", "")
    available_ports = int(state.get("available_ports", 0))
    total_capacity = int(state.get("total_capacity", 0))
    used_capacity = int(state.get("used_capacity", 0))
    maintenance = state.get("maintenance", False)

    # ── BR-001: Validate fields ──────────────────────────────────────
    valid_types = ("VOICE", "DATA", "VIDEO", "BNDL")
    if service_type not in valid_types:
        result.status = "REJECTED"
        result.error_code = "S003"
        result.rules_fired.append("BR-001")
        return result
    result.rules_fired.append("BR-001")

    # ── BR-002: Bandwidth vs port limits ─────────────────────────────
    bw_limits = {"CU": 100, "FBR": 10000, "WLS": 1000}
    max_bw = bw_limits.get(port_type, 0)
    if bandwidth > max_bw:
        result.status = "REJECTED"
        result.error_code = "S004"
        result.rules_fired.append("BR-002")
        return result
    result.rules_fired.append("BR-002")

    # ── BR-012: Video min 25 Mbps ────────────────────────────────────
    if service_type == "VIDEO" and bandwidth < 25:
        result.status = "REJECTED"
        result.error_code = "S005"
        result.rules_fired.append("BR-012")
        return result

    # ── BR-013: Bundle requires fiber or wireless ────────────────────
    if service_type == "BNDL" and port_type == "CU":
        result.status = "REJECTED"
        result.error_code = "S006"
        result.rules_fired.append("BR-013")
        return result

    # ── BR-005: Maintenance block ────────────────────────────────────
    if maintenance:
        result.status = "REJECTED"
        result.error_code = "S007"
        result.rules_fired.append("BR-005")
        return result

    # ── BR-003: Port availability ────────────────────────────────────
    if available_ports <= 0:
        result.status = "REJECTED"
        result.error_code = "S008"
        result.rules_fired.append("BR-003")
        return result

    # ── BR-004: Capacity threshold (Enterprise exempt) ───────────────
    if total_capacity > 0:
        utilization = ((used_capacity + bandwidth) * 100) / total_capacity
        if utilization > 85:
            if customer_tier != "ENTERPRISE":
                result.status = "REJECTED"
                result.error_code = "S009"
                result.rules_fired.append("BR-004")
                return result
            result.rules_fired.append("BR-004")

    # ── BR-006: Provisioning plan ────────────────────────────────────
    prov_map = {
        "FBR": ("FIBER-INST", 8, True),
        "CU": ("COPPER-ACT", 4, True),
        "WLS": ("WLS-PROV", 2, False),
    }
    prov_type, est_hours, tech_req = prov_map.get(port_type, ("UNKNOWN", 0, False))
    result.rules_fired.append("BR-006")

    # ── BR-014: SLA tier ─────────────────────────────────────────────
    sla_map = {"ENTERPRISE": "PREMIUM", "BUSINESS": "STANDARD", "RESIDENTIAL": "BASIC"}
    sla_tier = sla_map.get(customer_tier, "BASIC")
    result.rules_fired.append("BR-014")

    # ── BR-007: Features ─────────────────────────────────────────────
    feat_map = {"BNDL": "VOICE+DATA+VIDEO", "VOICE": "VOICE-ONLY", "DATA": "DATA-ONLY", "VIDEO": "VIDEO+DATA"}
    features = feat_map.get(service_type, "")
    result.rules_fired.append("BR-007")

    # ── BR-008: Pricing ──────────────────────────────────────────────
    rate_map = {"FBR": Decimal("0.50"), "CU": Decimal("1.20"), "WLS": Decimal("0.80")}
    monthly_rate = _d(bandwidth) * rate_map.get(port_type, Decimal("0"))

    if service_type == "BNDL":
        monthly_rate = monthly_rate * Decimal("0.80")  # 20% bundle discount
    result.rules_fired.append("BR-008")

    # ── BR-009: Enterprise activation fee discount ───────────────────
    activation_fee = Decimal("99.99") if tech_req else Decimal("0")
    if customer_tier == "ENTERPRISE":
        activation_fee = activation_fee * Decimal("0.50")
        result.rules_fired.append("BR-009")

    # ── BR-011: Enterprise wireless next-day ─────────────────────────
    if customer_tier == "ENTERPRISE" and port_type == "WLS":
        est_hours = 1
        result.rules_fired.append("BR-011")

    result.outputs = {
        "provision_type": prov_type,
        "estimated_hours": est_hours,
        "tech_required": tech_req,
        "sla_tier": sla_tier,
        "features": features,
        "monthly_rate": float(monthly_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "activation_fee": float(activation_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
    }
    return result


# ── S4: Circuit Inventory Management ─────────────────────────────────────────

def execute_s4(rules: list[CompiledRule], state: dict, result: CompilationResult) -> CompilationResult:
    """Compiled from S4 COBOL lines 79-311."""
    action = state.get("action", "")
    circuit_type = state.get("circuit_type", "")
    bandwidth = int(state.get("bandwidth", 0))
    service_class = state.get("service_class", "STD")
    site_status = state.get("site_status", "")
    site_type = state.get("site_type", "OWNED")
    site_capacity = int(state.get("site_capacity", 0))
    site_used = int(state.get("site_used", 0))
    cross_connects = int(state.get("cross_connects", 0))
    current_status = state.get("current_status", "")
    max_bw = int(state.get("max_bw", 0))
    current_bw = int(state.get("current_bw", 0))
    child_count = int(state.get("child_count", 0))

    bw_limits = {"DS1": 1544, "DS3": 44736, "OC3": 155520, "OC12": 622080, "ETH": 1000000}

    # ── Validation ───────────────────────────────────────────────────
    if action == "ASGN":
        # BR-002: Bandwidth check
        limit = bw_limits.get(circuit_type, 0)
        if bandwidth > limit:
            result.status = "REJECTED"
            result.error_code = "C006"
            result.rules_fired.append("BR-002")
            return result

        # BR-003: Site must be active
        if site_status != "ACTIVE":
            result.status = "REJECTED"
            result.error_code = "C007"
            result.rules_fired.append("BR-003")
            return result

        # BR-004: Site capacity
        if site_used >= site_capacity:
            result.status = "REJECTED"
            result.error_code = "C008"
            result.rules_fired.append("BR-004")
            return result

        # BR-005 + BR-010: Cross-connect limit (premium can exceed by 50%)
        max_xc = 64
        if cross_connects >= max_xc:
            if service_class != "PREM":
                result.status = "REJECTED"
                result.error_code = "C009"
                result.rules_fired.append("BR-005")
                return result
            else:
                if cross_connects >= int(max_xc * 1.5):
                    result.status = "REJECTED"
                    result.error_code = "C009"
                    result.rules_fired.append("BR-010")
                    return result
                result.rules_fired.append("BR-010")

        # Calculate cost
        rate_map = {"DS1": Decimal("0.15"), "DS3": Decimal("0.08"), "OC3": Decimal("0.04"),
                    "OC12": Decimal("0.02"), "ETH": Decimal("0.01")}
        cost = _d(bandwidth) * rate_map.get(circuit_type, Decimal("0"))

        class_mult = {"PREM": Decimal("1.50"), "STD": Decimal("1.00"), "ECON": Decimal("0.75")}
        cost = cost * class_mult.get(service_class, Decimal("1.00"))

        # BR-012: Colo premium
        if site_type == "COLO":
            cost = cost * Decimal("1.15")
            result.rules_fired.append("BR-012")

        install_fee = cost  # BR-013
        result.rules_fired.extend(["BR-003", "BR-011", "BR-013"])
        result.outputs = {
            "status": "ASSIGNED",
            "monthly_cost": float(cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "install_fee": float(install_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }
        return result

    elif action == "MOD":
        # BR-006: Must be ASSIGNED
        if current_status != "ASSIGNED":
            result.status = "REJECTED"
            result.error_code = "C010"
            result.rules_fired.append("BR-006")
            return result

        # Bandwidth within max
        if bandwidth > max_bw:
            result.status = "REJECTED"
            result.error_code = "C011"
            result.rules_fired.append("BR-006")
            return result

        # BR-007: Premium can't downgrade below 50%
        if service_class == "PREM":
            if bandwidth < int(current_bw * 0.50):
                result.status = "REJECTED"
                result.error_code = "C012"
                result.rules_fired.append("BR-007")
                return result

        # Recalculate cost
        rate_map = {"DS1": Decimal("0.15"), "DS3": Decimal("0.08"), "OC3": Decimal("0.04"),
                    "OC12": Decimal("0.02"), "ETH": Decimal("0.01")}
        cost = _d(bandwidth) * rate_map.get(circuit_type, Decimal("0"))
        class_mult = {"PREM": Decimal("1.50"), "STD": Decimal("1.00"), "ECON": Decimal("0.75")}
        cost = cost * class_mult.get(service_class, Decimal("1.00"))

        result.rules_fired.extend(["BR-006", "BR-011"])
        result.outputs = {
            "monthly_cost": float(cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }
        return result

    elif action == "DECOM":
        # BR-008: Must be ASSIGNED or RESERVED
        if current_status not in ("ASSIGNED", "RESERVED"):
            result.status = "REJECTED"
            result.error_code = "C013"
            result.rules_fired.append("BR-008")
            return result

        # BR-009: No active children
        if child_count > 0:
            result.status = "REJECTED"
            result.error_code = "C014"
            result.rules_fired.append("BR-009")
            return result

        result.rules_fired.append("BR-008")
        result.outputs = {"status": "DECOM", "monthly_cost": 0}
        return result

    elif action == "QUERY":
        result.outputs = {"result_code": "OK"}
        return result

    result.status = "REJECTED"
    result.error_code = "C002"
    return result


# ── S5: Fault Ticket Escalation ──────────────────────────────────────────────

def execute_s5(rules: list[CompiledRule], state: dict, result: CompilationResult) -> CompilationResult:
    """Compiled from S5 COBOL lines 74-250."""
    action = state.get("action", "")
    severity = int(state.get("severity", 0))
    customer_tier = state.get("customer_tier", "")
    affected_circuits = int(state.get("affected_circuits", 0))
    fault_type = state.get("fault_type", "")
    ticket_id = state.get("ticket_id", "")
    current_status = state.get("current_status", "")
    current_level = int(state.get("current_level", 1))
    escalation_count = int(state.get("escalation_count", 0))
    elapsed_minutes = int(state.get("elapsed_minutes", 0))
    sla_minutes = int(state.get("sla_minutes", 0))
    resolution_code = state.get("resolution_code", "")

    # ── BR-001: Validation ───────────────────────────────────────────
    if action == "CREATE":
        if not fault_type:
            result.status = "REJECTED"
            result.error_code = "T002"
            result.rules_fired.append("BR-001")
            return result
        if severity < 1 or severity > 4:
            result.status = "REJECTED"
            result.error_code = "T003"
            result.rules_fired.append("BR-001")
            return result
    elif action in ("UPDATE", "ESCAL", "RESOLV"):
        if not ticket_id:
            result.status = "REJECTED"
            result.error_code = "T004"
            result.rules_fired.append("BR-001")
            return result
    result.rules_fired.append("BR-001")

    # ── CREATE ───────────────────────────────────────────────────────
    if action == "CREATE":
        status = "OPEN"
        level = 1

        # BR-002: SLA by severity
        sla_map = {1: 60, 2: 240, 3: 1440, 4: 4320}
        sla = sla_map.get(severity, 4320)
        result.rules_fired.append("BR-002")

        # BR-003: Customer tier SLA reduction
        if customer_tier == "PLAT":
            sla = int(sla * 50 / 100)
            result.rules_fired.append("BR-003")
        elif customer_tier == "GOLD":
            sla = int(sla * 75 / 100)
            result.rules_fired.append("BR-003")

        # BR-011: Outage >100 circuits auto-escalates
        if fault_type == "OUTAGE" and affected_circuits > 100:
            severity = 1
            sla = 60
            level = 2
            result.rules_fired.append("BR-011")

        result.outputs = {
            "status": status,
            "sla_minutes": sla,
            "severity": severity,
            "level": level,
        }
        return result

    # ── UPDATE ───────────────────────────────────────────────────────
    elif action == "UPDATE":
        if current_status in ("RESOLVED", "CLOSED"):
            result.status = "REJECTED"
            result.error_code = "T005"
            result.rules_fired.append("BR-004")
            return result
        result.outputs = {"status": "WORKING"}
        return result

    # ── ESCAL ────────────────────────────────────────────────────────
    elif action == "ESCAL":
        # BR-005: Can't escalate resolved/closed
        if current_status in ("RESOLVED", "CLOSED"):
            result.status = "REJECTED"
            result.error_code = "T006"
            result.rules_fired.append("BR-005")
            return result

        # BR-006: Escalation limits
        if escalation_count >= 5:
            result.status = "REJECTED"
            result.error_code = "T007"
            result.rules_fired.append("BR-006")
            return result

        if current_level >= 4:
            result.status = "REJECTED"
            result.error_code = "T008"
            result.rules_fired.append("BR-006")
            return result

        new_level = current_level + 1
        sla_breached = elapsed_minutes > sla_minutes

        # BR-012: Critical at level 3+ → VP notify
        result_code = "OK"
        if severity == 1 and new_level >= 3:
            result_code = "VP-NOTIFY"
            result.rules_fired.append("BR-012")

        if sla_breached:
            result.rules_fired.append("BR-007")

        result.rules_fired.append("BR-005")
        result.outputs = {
            "status": "ESCALATD",
            "level": new_level,
            "sla_breached": sla_breached,
            "result_code": result_code,
        }
        return result

    # ── RESOLV ───────────────────────────────────────────────────────
    elif action == "RESOLV":
        if current_status == "CLOSED":
            result.status = "REJECTED"
            result.error_code = "T009"
            result.rules_fired.append("BR-008")
            return result

        if not resolution_code:
            result.status = "REJECTED"
            result.error_code = "T010"
            result.rules_fired.append("BR-009")
            return result

        sla_breached = elapsed_minutes > sla_minutes
        if sla_breached:
            result.rules_fired.append("BR-013")

        result.rules_fired.append("BR-008")
        result.outputs = {
            "status": "RESOLVED",
            "sla_breached": sla_breached,
        }
        return result

    # ── QUERY ────────────────────────────────────────────────────────
    elif action == "QUERY":
        if not ticket_id:
            result.status = "REJECTED"
            result.error_code = "T004"
            result.rules_fired.append("BR-010")
            return result
        result.outputs = {"result_code": "OK"}
        return result

    result.status = "REJECTED"
    result.error_code = "T001"
    return result


# ── S6: Contract Renewal ─────────────────────────────────────────────────────

def execute_s6(rules: list[CompiledRule], state: dict, result: CompilationResult) -> CompilationResult:
    """Compiled from S6 COBOL lines 75-234."""
    action = state.get("action", "")
    contract_status = state.get("contract_status", "")
    new_term = int(state.get("new_term", 0))
    monthly_rate = _d(state.get("monthly_rate", 0))
    tenure_months = int(state.get("tenure_months", 0))
    bundled = state.get("bundled", False)
    services_count = int(state.get("services_count", 0))
    remaining_months = int(state.get("remaining_months", 0))
    loyalty_tier_input = state.get("loyalty_tier", "")

    if action == "RENEW":
        # BR-001: Validation
        if new_term not in (12, 24, 36):
            result.status = "REJECTED"
            result.error_code = "R004"
            result.rules_fired.append("BR-001")
            return result

        # BR-002: Eligibility
        if contract_status not in ("ACTIVE", "EXPIRING"):
            result.status = "REJECTED"
            result.error_code = "R005"
            result.rules_fired.append("BR-002")
            return result
        result.rules_fired.append("BR-002")

        # BR-003: Term discount
        term_disc = {12: Decimal("5.00"), 24: Decimal("12.00"), 36: Decimal("20.00")}
        discount = term_disc.get(new_term, Decimal("0"))
        result.rules_fired.append("BR-003")

        # BR-004: Bundle discount
        if bundled and services_count >= 3:
            discount += Decimal("5.00")
            result.rules_fired.append("BR-004")

        # BR-005: Loyalty tier from tenure
        if tenure_months >= 120:
            loyalty_tier = "PLAT"
        elif tenure_months >= 60:
            loyalty_tier = "GOLD"
        elif tenure_months >= 24:
            loyalty_tier = "SILV"
        else:
            loyalty_tier = ""
        result.rules_fired.append("BR-005")

        # BR-009: Loyalty discount
        loyalty_disc = {"PLAT": Decimal("3.00"), "GOLD": Decimal("2.00"), "SILV": Decimal("1.00")}
        if loyalty_tier in loyalty_disc:
            discount += loyalty_disc[loyalty_tier]
            result.rules_fired.append("BR-009")

        # BR-010: Cap at 30%
        if discount > Decimal("30.00"):
            discount = Decimal("30.00")
            result.rules_fired.append("BR-010")

        # Calculate new rate
        new_rate = monthly_rate * (Decimal("1") - discount / Decimal("100"))

        # BR-011: Loyalty credit = 2% of annual spend
        loyalty_credit = new_rate * Decimal("12") * Decimal("0.02")

        result.outputs = {
            "discount_pct": float(discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "new_rate": float(new_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "loyalty_tier": loyalty_tier,
            "loyalty_credit": float(loyalty_credit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }
        return result

    elif action == "TERM":
        # BR-008: Only ACTIVE can be terminated
        if contract_status != "ACTIVE":
            result.status = "REJECTED"
            result.error_code = "R006"
            result.rules_fired.append("BR-008")
            return result

        # BR-006: ETF calculation
        etf = _d(remaining_months) * Decimal("25.00")
        result.rules_fired.append("BR-006")

        # BR-007: Cap at 500
        if etf > Decimal("500.00"):
            etf = Decimal("500.00")
            result.rules_fired.append("BR-007")

        # BR-012: Platinum 50% ETF reduction (use loyalty_tier from input for TERM)
        # For TERM, loyalty tier comes from input since we don't compute it
        if loyalty_tier_input == "PLAT":
            etf = etf * Decimal("0.50")
            result.rules_fired.append("BR-012")

        result.outputs = {
            "etf_amount": float(etf.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "status": "TERMINAT",
        }
        return result

    elif action == "MOD":
        if contract_status != "ACTIVE":
            result.status = "REJECTED"
            result.error_code = "R007"
            result.rules_fired.append("BR-008")
            return result
        result.outputs = {"result_code": "OK"}
        return result

    elif action == "QUERY":
        result.outputs = {"result_code": "OK"}
        return result

    result.status = "REJECTED"
    result.error_code = "R002"
    return result


# ── S7: Account Migration ────────────────────────────────────────────────────

def execute_s7(rules: list[CompiledRule], state: dict, result: CompilationResult) -> CompilationResult:
    """Compiled from S7 COBOL lines 83-319."""
    action = state.get("action", "")
    source_platform = state.get("source_platform", "")
    target_platform = state.get("target_platform", "")
    customer_type = state.get("customer_type", "CONS")
    service_count = int(state.get("service_count", 0))
    data_size_gb = int(state.get("data_size_gb", 0))
    active_orders = int(state.get("active_orders", 0))
    open_tickets = int(state.get("open_tickets", 0))
    migration_status = state.get("migration_status", "")
    complexity = state.get("complexity", "")
    cutover_window_hr = int(state.get("cutover_window_hr", 0))
    services_failed = int(state.get("services_failed", 0))
    rollback_available = state.get("rollback_available", True)

    if action == "CHECK":
        # BR-001: Platforms required and must differ
        if not source_platform or not target_platform:
            result.status = "REJECTED"
            result.error_code = "M003"
            result.rules_fired.append("BR-001")
            return result
        if source_platform == target_platform:
            result.status = "REJECTED"
            result.error_code = "M004"
            result.rules_fired.append("BR-002")
            return result

        # BR-003: Active orders block
        if active_orders > 0:
            result.status = "REJECTED"
            result.error_code = "M005"
            result.rules_fired.append("BR-003")
            return result

        # BR-004: Open tickets limit
        if open_tickets > 5:
            result.status = "REJECTED"
            result.error_code = "M006"
            result.rules_fired.append("BR-004")
            return result

        # BR-005: Complexity
        if service_count <= 10 and data_size_gb <= 100:
            cmplx = "LOW"
        elif service_count <= 50 and data_size_gb <= 1000:
            cmplx = "MEDIUM"
        else:
            cmplx = "HIGH"
        result.rules_fired.append("BR-005")

        # BR-006: Risk score
        risk = (service_count * 2) + (data_size_gb // 100) + (open_tickets * 10)
        if customer_type == "ENTE":
            risk = int(risk * 1.5)
        if risk > 100:
            risk = 100
        result.rules_fired.append("BR-006")

        result.outputs = {
            "status": "ELIGIBLE",
            "complexity": cmplx,
            "risk_score": risk,
        }
        return result

    elif action == "PLAN":
        # BR-007: Must be ELIGIBLE
        if migration_status != "ELIGIBLE":
            result.status = "REJECTED"
            result.error_code = "M007"
            result.rules_fired.append("BR-007")
            return result

        # Duration by complexity
        dur_map = {"LOW": 2, "MEDIUM": 4, "HIGH": 8}
        est_duration = dur_map.get(complexity, 2)

        # BR-014: Cutover window check
        if cutover_window_hr < est_duration:
            result.status = "REJECTED"
            result.error_code = "M008"
            result.rules_fired.append("BR-014")
            return result

        # BR-008: Cost
        cost = _d(service_count) * Decimal("150.00") + _d(data_size_gb) * Decimal("2.50")

        # BR-013: Customer type multiplier
        mult_map = {"ENTE": Decimal("2.00"), "SMB": Decimal("1.50"), "CONS": Decimal("1.00")}
        cost = cost * mult_map.get(customer_type, Decimal("1.00"))
        result.rules_fired.extend(["BR-007", "BR-008", "BR-013"])

        result.outputs = {
            "status": "PLANNED",
            "estimated_cost": float(cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "est_duration_hr": est_duration,
        }
        return result

    elif action == "EXEC":
        if migration_status != "PLANNED":
            result.status = "REJECTED"
            result.error_code = "M009"
            result.rules_fired.append("BR-009")
            return result
        result.outputs = {"status": "EXECUTING"}
        return result

    elif action == "VERIFY":
        if migration_status not in ("EXECUTING", "COMPLETE"):
            result.status = "REJECTED"
            result.error_code = "M010"
            result.rules_fired.append("BR-010")
            return result

        if services_failed > 0:
            if customer_type == "ENTE":
                # Auto-rollback for enterprise
                result.rules_fired.extend(["BR-010", "BR-011"])
                result.outputs = {"status": "ROLLEDBACK"}
                return result
            else:
                result.rules_fired.extend(["BR-010", "BR-011"])
                result.outputs = {"status": "COMPLETE", "result_code": "PARTIAL"}
                return result
        else:
            # BR-015: Successful verification disables rollback
            result.rules_fired.extend(["BR-010", "BR-015"])
            result.outputs = {"status": "VERIFIED", "rollback_available": False}
            return result

    elif action == "ROLLBK":
        if migration_status not in ("EXECUTING", "COMPLETE"):
            result.status = "REJECTED"
            result.error_code = "M011"
            result.rules_fired.append("BR-012")
            return result

        if not rollback_available:
            result.status = "REJECTED"
            result.error_code = "M012"
            result.rules_fired.append("BR-012")
            return result

        result.outputs = {"status": "ROLLEDBACK"}
        return result

    elif action == "QUERY":
        result.outputs = {"result_code": "OK"}
        return result

    result.status = "REJECTED"
    result.error_code = "M002"
    return result
