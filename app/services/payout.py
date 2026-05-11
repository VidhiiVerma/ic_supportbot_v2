from app.formatter import format_value


FIELD_SYNONYMS = {
    "target pay": "target_pay",
    "base pay": "target_pay",
    "payout": "total_ic_payout",
    "total payout": "total_ic_payout",
    "ic payout": "total_ic_payout",
    "commission": "commission_earnings_value",
    "goal": "qtd_trx_goal",
    "trx": "qtd_trx",
    "achievement rate": "goal_achievement_rate",
}


def detect_field(question: str):
    q = question.lower()

    matched_field = None
    max_len = 0

    for synonym, field in FIELD_SYNONYMS.items():
        if synonym in q:
            if len(synonym) > max_len:
                matched_field = field
                max_len = len(synonym)

    return matched_field


def get_direct_data(question: str, rep_data: dict):
    field = detect_field(question)

    if not field:
        return None

    payout = rep_data.get("payout", {})
    eligibility = rep_data.get("eligibility", {})

    value = payout.get(field)

    if value is None:
        value = eligibility.get(field)

    if value is None:
        return "data not available"

    return format_value(field, value)