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
    "assignment",
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

DECIMAL_FIELDS = {
    "credits",
    "credited_trx",
}


def format_decimal(value) -> str:
    try:
        v = float(value)
        return f"{v:,.1f}" if not v.is_integer() else f"{v:,.0f}"
    except Exception:
        return str(value)


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

        if v <= 1:
            v = v * 100

        return f"{v:.0f}%"

    except Exception:
        return str(value)


def format_rate(value) -> str:
    try:
        return f"${float(value):,.0f} per TRx"
    except Exception:
        return str(value)


def format_value(field: str, value) -> str:

    if value is None:
        return "data not available"

    f = field.lower().strip()

    if f in CURRENCY_FIELDS:
        return format_currency(value)

    if f in PERCENT_FIELDS:
        return format_percentage(value)

    if f in RATE_FIELDS:
        return format_rate(value)

    if f in DECIMAL_FIELDS:
        return format_decimal(value)

    if f in INTEGER_FIELDS:
        return format_number(value)

    try:
        v = float(value)
        return str(int(v)) if v == int(v) else str(v)

    except Exception:
        return str(value)


def format_calc_for_llm(calc: dict) -> str:

    if not calc:
        return "data not available"

    lines = []

    for field, value in calc.items():
        lines.append(f"{field}: {format_value(field, value)}")

    return "\n".join(lines)


def format_dict_for_llm(data: dict) -> str:

    if not data:
        return "data not available"

    lines = []

    for k, v in data.items():
        lines.append(f"{k}: {format_value(k, v)}")

    return "\n".join(lines)