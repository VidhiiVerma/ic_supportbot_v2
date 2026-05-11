from app.prompts import POLICY_PROMPT


def generate_policy_response(
    question,
    rag,
    llm,
):

    context = rag.get_context(question) if rag else ""

    prompt = POLICY_PROMPT.format(
        context=context,
        question=question,
    )

    return llm.generate(prompt)