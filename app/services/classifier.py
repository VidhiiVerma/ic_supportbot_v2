import json


CLASSIFIER_PROMPT = """
You are an IC compensation query classifier.

Your task is ONLY to classify the user query.

Return ONLY valid JSON.

Possible intents:
- greeting
- thanks
- payout
- payout_explanation
- eligibility
- eligibility_explanation
- hcp_count
- hcp_breakdown
- credit_total
- credit_breakdown
- hcp_inclusion
- follow_up
- why
- policy
- unknown

Possible fields:
- total_ic_payout
- total_ic_earnings
- ic_earnings_value
- commission_earnings_value
- total_eligibility
- qtd_trx
- qtd_trx_goal
- target_pay
- ic_earnings_rate

Rules:
- Understand incomplete English
- Understand shorthand questions
- Understand conversational follow-ups
- Use memory context if available
- Never explain anything
- Never answer the question
- Return JSON only

Examples:

User:
what my payout

Output:
{
  "intent": "payout",
  "field": "total_ic_payout"
}

User:
how is my payout calculated

Output:
{
  "intent": "payout_explanation",
  "field": "total_ic_payout"
}

User:
how many hcps

Output:
{
  "intent": "hcp_count",
  "field": null
}

User:
what are these numbers

Memory:
{
  "last_intent": "payout_explanation"
}

Output:
{
  "intent": "follow_up",
  "field": "ic_earnings_value"
}

Conversation Memory:
{memory}

User Question:
{question}
"""


def classify_query(
    question,
    memory,
    llm,
):

    prompt = CLASSIFIER_PROMPT.format(
        memory=memory,
        question=question,
    )

    try:
        response = llm.generate(prompt)
        print("CLASSIFIER RESPONSE:")
        print(response)

        return json.loads(response)

    except Exception:

        return {
            "intent": "unknown",
            "field": None,
        }