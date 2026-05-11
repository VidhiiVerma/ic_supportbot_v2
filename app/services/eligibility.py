from app.formatter import format_value


def build_eligibility_response(eligibility: dict):

    nh_days = eligibility.get("new_hire_eligible_days", 0)

    nh_frac = float(
        eligibility.get("new_hire_eligibility", 0) or 0
    )

    ic_days = eligibility.get("ic_eligible_days", 0)

    tot_days = eligibility.get("total_days_in_qtr", 0)

    ic_frac = float(
        eligibility.get("ic_eligibility", 0) or 0
    )

    tot_frac = float(
        eligibility.get("total_eligibility", 0) or 0
    )

    reason = eligibility.get("eligibility_reason", "")

    response = (
        f"Your total eligibility is "
        f"{format_value('total_eligibility', tot_frac)}. "
        f"This is based on "
        f"{ic_days} IC eligible days "
        f"({format_value('ic_eligibility', ic_frac)})"
    )

    if nh_days and float(nh_days) > 0:
        response += (
            f" and {nh_days} new hire eligible days "
            f"({format_value('new_hire_eligibility', nh_frac)})"
        )

    response += (
        f" out of {tot_days} total days in the quarter."
    )

    if reason and str(reason).lower() not in (
        "nan",
        "none",
        "",
    ):
        response += f" Reason: {reason}."

    return response