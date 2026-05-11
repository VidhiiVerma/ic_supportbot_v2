from app.prompts import EXPLANATION_PROMPT, WHY_PROMPT
from app.formatter import format_calc_for_llm


def generate_explanation(calc, question, llm):

    prompt = EXPLANATION_PROMPT.format(
        formatted_data=format_calc_for_llm(calc),
        question=question,
    )

    return llm.generate(prompt)


def generate_why_response(
    calc,
    question,
    rag,
    llm,
):

    context = rag.get_context(question) if rag else ""

    prompt = WHY_PROMPT.format(
        formatted_data=format_calc_for_llm(calc),
        policy_context=context,
        question=question,
    )

    return llm.generate(prompt)