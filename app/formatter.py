CURRENCY_FIELDS = {
    "target_pay",
    "ic_earnings",
    "ic_earnings_value",
    "commission",
    "commission_earnings_value",
    "total_ic",
    "total_ic_earnings",
    "total_ic_payout",
}

PERCENT_FIELDS = {
    "goal_achievement_rate",
    "ic_earning_rate",
    "ic_earnings_rate",
    "qtd_ic_earnings_rate",
    "assignment_pct",
    "new_hire_eligibility",
    "ic_eligibility",
    "total_eligibility",
}

RATE_FIELDS = {
    "rate",
    "commission_rate",
}

INTEGER_FIELDS = {
    "qtd_trx",
    "qtd_trx_goal",
    "goal",
    "incremental",
    "total_projected_incremental_trx",
}


def format_currency(value) -> str:
    try:
        return f"${float(value):,.0f}"
    except Exception:
        return str(value)


def format_number(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return str(value)


def format_percentage(value) -> str:
    try:
        v = float(value)
        # Normalize: if v > 1, assume it's already a percentage (e.g. 100)
        if v > 1:
            v = v / 100
        return f"{v * 100:.0f}%"
    except Exception:
        return str(value)


def format_rate(value) -> str:
    try:
        return f"${float(value):,.0f} per TRx"
    except Exception:
        return str(value)


def format_value(field: str, value) -> str:
    """
    Format a calc/payout value based on its field name.

    Usage:
        format_value("total_ic", 10490.0)   → "$10,490"
        format_value("ic_earning_rate", 1.0) → "100%"
        format_value("rate", 10)             → "$10 per TRx"
        format_value("qtd_trx", 466.0)       → "466"
    """
    if value is None:
        return "data not available"

    f = field.lower().strip()

    if f in CURRENCY_FIELDS:
        return format_currency(value)
    if f in PERCENT_FIELDS:
        return format_percentage(value)
    if f in RATE_FIELDS:
        return format_rate(value)
    if f in INTEGER_FIELDS:
        return format_number(value)

    # default: return clean string (strip unnecessary .0)
    try:
        v = float(value)
        return str(int(v)) if v == int(v) else str(v)
    except Exception:
        return str(value)


def format_calc_for_llm(calc: dict) -> str:
    """
    Returns a human-readable, properly formatted string
    of all calc fields — used when passing data to the LLM.
    """
    lines = []
    for field, value in calc.items():
        lines.append(f"{field}: {format_value(field, value)}")
    return "\n".join(lines)