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
}

EXPLANATION_WORDS = {
    "explain",
    "how is",
    "breakdown",
    "calculate",
    "calculated",
    "calculation",
}

ELIGIBILITY_WORDS = {
    "eligibility",
    "eligible",
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