from app.db import get_rep_data

from services.intent import detect_intents

from services.payout import get_direct_data

from services.hcp import (
    get_total_credits,
    get_hcp_credit_breakdown,
    get_hcp_names,
    count_unique_hcps,
    check_hcp_inclusion,
)

from services.eligibility import (
    build_eligibility_response,
)

from services.calculation import calculate_ic

from services.explanation import (
    generate_explanation,
    generate_why_response,
)

from services.policy import (
    generate_policy_response,
)


def get_rep_explanation(
    rep_id,
    question,
    rag,
    llm,
):

    rep_data = get_rep_data(rep_id)

    if not rep_data:
        return "No data found for this rep."

    intents = detect_intents(question)

    if "greeting" in intents:
        return "Hello. How can I assist?"

    if "thanks" in intents:
        return "You're welcome."

    sales_rows = rep_data.get("sales", [])

    rows = [
        r for r in sales_rows
        if str(r.get("assignment_emp")) == str(rep_id)
    ]

    q = question.lower()

    # DIRECT DATA 

    if (
        "direct_data" in intents
        and "explanation" not in intents
    ):
        response = get_direct_data(question, rep_data)

        if response:
            return response

    # CREDITS 

    if "credit" in intents:

        if any(
            t in q
            for t in (
                "how many",
                "total",
                "sum",
            )
        ):
            return get_total_credits(
                rows,
                question,
            )

        return get_hcp_credit_breakdown(
            rows,
            question,
        )

    # HCP 

    if "hcp" in intents:

        if any(
            t in q
            for t in (
                "how many",
                "count",
                "total",
            )
        ):
            total_hcps = count_unique_hcps(rows)

            return (
                f"Total unique HCPs: "
                f"{total_hcps}"
            )

        if "include" in q:
            return check_hcp_inclusion(
                rows,
                question,
            )

        return get_hcp_names(rows)

    # ELIGIBILITY 

    if "eligibility" in intents:

        eligibility = rep_data.get(
            "eligibility",
            {},
        )

        if eligibility:
            return build_eligibility_response(
                eligibility
            )

    # EXPLANATION 

    calc = calculate_ic(rep_data)

    if "explanation" in intents and calc:
        return generate_explanation(
            calc,
            question,
            llm,
        )

    # WHY 

    if "why" in intents and calc:
        return generate_why_response(
            calc,
            question,
            rag,
            llm,
        )

    # POLICY 

    return generate_policy_response(
        question,
        rag,
        llm,
    )