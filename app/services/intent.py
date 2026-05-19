import re


GREETING_WORDS = {"hi", "hello", "hey"}

THANK_WORDS = {"thank", "thanks", "thank you"}

DIRECT_DATA_WORDS = {
    "what is",
    "show",
    "give",
    "list",
    "who",
    "which",
    "how many",
    "count",
    "total",
    "share",           # "share my current IC plan document"
}

EXPLANATION_WORDS = {
    "explain",
    "how is",
    "breakdown",
    "calculate",
    "calculated",
    "calculation",
    "current period",  # "explain my eligibility for the current period"
}

ELIGIBILITY_WORDS = {
    "eligibility",
    "eligible",
    "current period",  # "explain my eligibility for the current period"
}

PLAN_WORDS = {
    "plan document",
    "ic plan",
    "plan doc",
    "download the plan",
    "share my current ic plan",
    "current ic plan",
}

HCP_WORDS = {
    "hcp",
    "doctor",
}


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.lower().strip())


def detect_intents(question: str) -> list[str]:
    q = normalize_question(question)

    intents = []

    if q in GREETING_WORDS:
        return ["greeting"]

    if any(word in q for word in THANK_WORDS):
        return ["thanks"]

    # Plan document must be checked BEFORE generic direct_data so it gets
    # routed to policy/plan rather than a data fetch.
    if any(word in q for word in PLAN_WORDS):
        return ["policy"]

    if any(word in q for word in DIRECT_DATA_WORDS):
        intents.append("direct_data")

    if any(word in q for word in EXPLANATION_WORDS):
        intents.append("explanation")

    if any(word in q for word in ELIGIBILITY_WORDS):
        intents.append("eligibility")

    if "why" in q:
        intents.append("why")

    if any(word in q for word in HCP_WORDS):
        intents.append("hcp")

    if "credit" in q or "trx" in q:
        intents.append("credit")

    return intents if intents else ["policy"]