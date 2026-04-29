import re
from .db import run_query
from .formatter import format_currency


# ---------------- NORMALIZATION ---------------- #

def normalize_keys(data: dict) -> dict:
    return {
        k.strip().lower().replace(" ", "_"): v
        for k, v in data.items()
    }


def format_data_for_llm(data: dict) -> str:
    return "\n".join(
        f"{k.replace('_', ' ').title()}: {v}"
        for k, v in data.items()
    )


# ---------------- DATABASE ---------------- #

def get_payout_data(rep_id: str):
    query = f"""
    SELECT *
    FROM ic_implementation.ic_intelligence.payout_summary
    WHERE `Rep ID` = '{rep_id}'
    LIMIT 1
    """
    result = run_query(query)
    return normalize_keys(result[0]) if result else None


def get_eligibility_data(rep_name: str):
    query = f"""
    SELECT *
    FROM ic_implementation.ic_intelligence.eligibility_2
    WHERE lower(rep_name) = lower('{rep_name}')
    """
    result = run_query(query)
    return normalize_keys(result[0]) if result else None


def get_combined_data(rep_id: str):
    payout = get_payout_data(rep_id)
    if not payout:
        return None

    eligibility = get_eligibility_data(payout.get("rep_name"))
    if eligibility:
        payout.update(eligibility)

    return payout


# ---------------- INTENT ---------------- #

def detect_intent(question: str) -> str:
    q = question.lower()

    if any(word in q for word in ["hi", "hello", "hey"]):
        return "greeting"

    if any(word in q for word in ["policy", "rule", "eligibility"]):
        return "policy"

    return "rep_data"


def is_explanation_query(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in ["explain", "why", "how", "breakdown", "calculated"])


# ---------------- FIELD DETECTION ---------------- #

FIELD_MAP = {
    "payout": "total_ic_payout",
    "earnings": "total_ic_earnings",
    "commission": "commission_earnings_value",
    "trx": "qtd_trx",
    "goal": "qtd_trx_goal",
    "name": "rep_name"
}


def detect_field(question: str):
    q = question.lower()

    for keyword, field in FIELD_MAP.items():
        if keyword in q:
            return field

    return None


# ---------------- MAIN SERVICE ---------------- #

def get_rep_explanation(rep_id: str, question: str, rag, llm) -> str:
    rep_data = get_combined_data(rep_id)

    if not rep_data:
        return "No data found for the given representative."

    intent = detect_intent(question)

    # ---------- GREETING ---------- #
    if intent == "greeting":
        name = rep_data.get("rep_name", "there")
        return f"Hello {name}. How can I assist you today?"

    # ---------- POLICY ---------- #
    if intent == "policy":
        context = None

        if rag:
            try:
                result = rag.ask(question)
                if isinstance(result, dict):
                    context = result.get("context")
            except Exception:
                context = None

        response = llm.generate(f"""
You are an IC policy assistant.

Answer strictly using the policy provided below.

Policy:
{context or "No policy information available."}

Question:
{question}
""")

        return response or "Policy information is not available."

    # ---------- DIRECT FIELD RESPONSE ---------- #
    field = detect_field(question)

    if field and not is_explanation_query(question):
        value = rep_data.get(field)

        if value is None:
            return "Requested data is not available."

        if any(x in field for x in ["payout", "earnings", "commission"]):
            return f"{field.replace('_', ' ').title()}: {format_currency(value)}"

        return f"{field.replace('_', ' ').title()}: {value}"

    # ---------- EXPLANATION (LLM CONTROLLED) ---------- #
    formatted_data = format_data_for_llm(rep_data)

    prompt = f"""
You are an Incentive Compensation assistant.

Objective:
Explain the answer clearly using ONLY the data provided.

Constraints:
- Do not modify any numbers
- Do not infer missing values
- Do not assume formulas unless explicitly stated
- If required data is missing, state "data not available"

Style:
- Professional and clear
- Concise (maximum 4 sentences)
- Structured explanation

Response Structure:
1. Direct answer
2. Supporting explanation using provided values

Data:
{formatted_data}

Question:
{question}
"""

    response = llm.generate(prompt)

    if not response:
        return "Unable to generate a response at the moment."

    return response