from app.db import get_rep_data

from app.prompts import ORCHESTRATION_PROMPT

from app.services.calculation import calculate_ic

from app.services.hcp import (
    get_total_credits,
    get_hcp_credit_breakdown,
    get_hcp_names,
    count_unique_hcps,
)

from app.formatter import format_calc_for_llm

from app.conversation_memory import (
    format_history_for_prompt,
    save_turn,
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

    payout = rep_data.get("payout", {})
    eligibility = rep_data.get("eligibility", {})
    sales_rows = rep_data.get("sales", [])

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

    total_hcps   = count_unique_hcps(rows)
    total_credits = get_total_credits(rows, question)
    hcp_breakdown = get_hcp_credit_breakdown(rows, question)
    hcp_names     = get_hcp_names(rows)

    # ---------------- POLICY CONTEXT ---------------- #

    policy_context = rag.get_context(question) if rag else ""

    # ---------------- CONVERSATION HISTORY ---------------- #

    conversation_history = (
        format_history_for_prompt(memory)
        if memory
        else "No prior conversation."
    )

    # ---------------- BUILD PROMPT ---------------- #

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

    # ---------------- SAVE TO STRUCTURED MEMORY ---------------- #

    if memory is not None:
        # Build a clean snapshot of this turn's numbers for follow-up resolution
        data_snapshot = calc if calc else {}
        if payout:
            data_snapshot.update({
                k: payout[k]
                for k in (
                    "qtd_trx", "qtd_trx_goal", "target_pay",
                    "ic_earning_rate", "ic_earnings_rate",
                )
                if k in payout
            })

        save_turn(
            memory=memory,
            question=question,
            response=response,
            data_snapshot=data_snapshot,
        )

    return response