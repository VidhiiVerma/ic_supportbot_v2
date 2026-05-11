from app.db import get_rep_data

from app.prompts import (
    ORCHESTRATION_PROMPT,
)

from app.services.calculation import (
    calculate_ic,
)

from app.services.hcp import (
    get_total_credits,
    get_hcp_credit_breakdown,
    get_hcp_names,
    count_unique_hcps,
)

from app.formatter import (
    format_calc_for_llm,
)


def get_rep_explanation(
    rep_id,
    question,
    rag,
    llm,
    memory=None,
):

    # ---------------- FETCH DATA ---------------- #

    rep_data = get_rep_data(rep_id)

    if not rep_data:
        return "No data found for this rep."

    payout = rep_data.get(
        "payout",
        {},
    )

    eligibility = rep_data.get(
        "eligibility",
        {},
    )

    sales_rows = rep_data.get(
        "sales",
        [],
    )

    rows = [
        r for r in sales_rows
        if str(r.get("assignment_emp")) == str(rep_id)
    ]

    # ---------------- DETERMINISTIC CALCULATIONS ---------------- #

    calc = calculate_ic(rep_data)

    formatted_calc = (
        format_calc_for_llm(calc)
        if calc
        else "data not available"
    )

    # ---------------- HCP / CREDIT DATA ---------------- #

    total_hcps = count_unique_hcps(rows)

    total_credits = get_total_credits(
        rows,
        question,
    )

    hcp_breakdown = get_hcp_credit_breakdown(
        rows,
        question,
    )

    hcp_names = get_hcp_names(rows)

    # ---------------- POLICY CONTEXT ---------------- #

    policy_context = (
        rag.get_context(question)
        if rag
        else ""
    )

    # ---------------- CONVERSATION HISTORY ---------------- #

    conversation_history = ""

    if memory:

        history = memory.get(
            "history",
            [],
        )

        conversation_history = "\n".join(history)

    # ---------------- BUILD FULL CONTEXT ---------------- #

    prompt = ORCHESTRATION_PROMPT.format(
        conversation_history=conversation_history,

        rep_data=f"""

PAYOUT DATA:
{payout}

ELIGIBILITY DATA:
{eligibility}

CALCULATED VALUES:
{formatted_calc}

HCP COUNT:
{total_hcps}

TOTAL CREDITS:
{total_credits}

HCP CREDIT BREAKDOWN:
{hcp_breakdown}

HCP NAMES:
{hcp_names}

""",

        policy_context=policy_context,

        question=question,
    )

    # ---------------- GENERATE RESPONSE ---------------- #

    response = llm.generate(prompt)

    # ---------------- SAVE MEMORY ---------------- #

    if memory is not None:

        if "history" not in memory:
            memory["history"] = []

        memory["history"].append(
            f"User: {question}"
        )

        memory["history"].append(
            f"Assistant: {response}"
        )

        # keep only recent history
        memory["history"] = memory["history"][-10:]

    return response