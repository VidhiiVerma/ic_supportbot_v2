from app.db import get_rep_data

from app.services.classifier import (
    classify_query,
)

from app.services.payout import (
    get_direct_data,
)

from app.services.hcp import (
    get_total_credits,
    get_hcp_credit_breakdown,
    get_hcp_names,
    count_unique_hcps,
    check_hcp_inclusion,
)

from app.services.eligibility import (
    build_eligibility_response,
)

from app.services.calculation import (
    calculate_ic,
)

from app.services.explanation import (
    generate_explanation,
    generate_why_response,
)

from app.services.policy import (
    generate_policy_response,
)


def get_rep_explanation(
    rep_id,
    question,
    rag,
    llm,
    memory=None,
):

    rep_data = get_rep_data(rep_id)

    if not rep_data:
        return "No data found for this rep."

    classification = classify_query(
        question,
        memory,
        llm,
    )

    intent = classification.get("intent")
    field = classification.get("field")

    sales_rows = rep_data.get("sales", [])

    rows = [
        r for r in sales_rows
        if str(r.get("assignment_emp")) == str(rep_id)
    ]

    # SAVE MEMORY

    if memory is not None:

        memory["last_question"] = question
        memory["last_intent"] = intent
        memory["last_field"] = field

    # GREETING

    if intent == "greeting":
        return "Hello. How can I assist?"

    # THANKS

    if intent == "thanks":
        return "You're welcome."

    # PAYOUT / DIRECT DATA

    if intent == "payout":

        response = get_direct_data(
            question,
            rep_data,
        )

        if response:
            return response

    # PAYOUT EXPLANATION

    calc = calculate_ic(rep_data)

    if intent == "payout_explanation" and calc:

        return generate_explanation(
            calc,
            question,
            llm,
        )

    # WHY

    if intent == "why" and calc:

        return generate_why_response(
            calc,
            question,
            rag,
            llm,
        )

    # ELIGIBILITY

    if intent == "eligibility":

        eligibility = rep_data.get(
            "eligibility",
            {},
        )

        if eligibility:

            return build_eligibility_response(
                eligibility
            )

    # HCP COUNT

    if intent == "hcp_count":

        total_hcps = count_unique_hcps(
            rows
        )

        return str(total_hcps)

    # HCP BREAKDOWN

    if intent == "hcp_breakdown":

        return get_hcp_names(rows)

    # CREDIT TOTAL

    if intent == "credit_total":

        return get_total_credits(
            rows,
            question,
        )

    # CREDIT BREAKDOWN

    if intent == "credit_breakdown":

        return get_hcp_credit_breakdown(
            rows,
            question,
        )

    # HCP INCLUSION

    if intent == "hcp_inclusion":

        return check_hcp_inclusion(
            rows,
            question,
        )

    # FOLLOW UP

    if intent == "follow_up":

        last_intent = (
            memory.get("last_intent")
            if memory
            else None
        )

        if last_intent == "payout_explanation":

            return (
                "The first number is your target pay. "
                "The percentage is your IC earnings rate "
                "based on performance. "
                "The final amount is your calculated "
                "Base IC Earnings."
            )

    # POLICY

    return generate_policy_response(
        question,
        rag,
        llm,
    )