import time
import logging
from typing import Optional
from app.db import get_rep_data

from app.prompts import ORCHESTRATION_PROMPT

from app.services.calculation import calculate_ic

from app.services.hcp import (
    get_total_credits,
    get_hcp_credit_breakdown,
    get_hcp_names,
    count_unique_hcps,
)

from app.formatter import format_calc_for_llm, format_dict_for_llm

from app.conversation_memory import (
    get_formatted_history,
    save_turn,               
)


logger = logging.getLogger(__name__)

# Follow-up signals that indicate the user is asking about a previous response
_FOLLOWUP_SIGNALS = {
    "why", "how", "explain", "what is this", "what are these",
    "tell me more", "what does this mean", "reason", "because",
    "what is the reason", "why only", "why is it", "why was",
}


def _build_rag_query(question: str, user_id: str) -> str:
    """
    For follow-up questions, enrich the RAG query with the last assistant
    response so vector retrieval finds the right policy section.

    Example:
        question     = "why commission rate is 10 only"
        last_response = "Commission: 49 TRx x $10/TRx = $490"
        rag_query    = "why commission rate is 10 only\nContext: Commission: ..."
    """
    q_lower = question.lower()
    is_followup = any(signal in q_lower for signal in _FOLLOWUP_SIGNALS)

    if not is_followup:
        return question

    # Pull last assistant line from formatted history
    history_str = get_formatted_history(user_id)
    lines = history_str.splitlines()

    last_assistant = next(
        (ln[len("Assistant: "):] for ln in reversed(lines)
         if ln.startswith("Assistant: ")),
        None,
    )

    if last_assistant:
        return f"{question}\nContext: {last_assistant}"

    return question


def get_rep_explanation(
    rep_id: str,
    question: str,
    rag,
    llm,
    user_id: str,
    rep_name: Optional[str] = None,
):

    start_db = time.time()
    rep_data = get_rep_data(rep_id)
    db_time = time.time() - start_db
    logger.info(f"DB Fetch for {rep_id} took {db_time:.2f}s")

    if not rep_data:
        return "No data found for this rep."

    payout      = rep_data.get("payout", {})
    eligibility = rep_data.get("eligibility", {})
    sales_rows  = rep_data.get("sales", [])

    rows = [
        r for r in sales_rows
        if str(r.get("assignment_emp")) == str(rep_id)
    ]

    # PRIORITIZE DB name (Alex Morgan) over passed name (Vidhi Verma)
    final_rep_name = (
        payout.get("rep_name")
        or eligibility.get("rep_name")
        or rep_data.get("rep_name")
        or rep_name  # fallback to name from Teams/API
        or "Rep"                       
    )
    rep_role = (
        payout.get("role")
        or eligibility.get("role")
        or rep_data.get("role")
        or "TBM"
    )

    # DETERMINISTIC CALCULATION

    calc           = calculate_ic(rep_data)
    formatted_calc = format_calc_for_llm(calc) if calc else "data not available"

    # HCP / CREDIT DATA 

    total_hcps    = count_unique_hcps(rows)
    total_credits = get_total_credits(rows, question)
    hcp_breakdown = get_hcp_credit_breakdown(rows, question)
    hcp_names     = get_hcp_names(rows)

    # POLICY CONTEXT (context-aware RAG query) 

    rag_query      = _build_rag_query(question, user_id)   # uses user_id now
    
    start_rag = time.time()
    policy_context = rag.get_context(rag_query) if rag else ""
    rag_time = time.time() - start_rag
    logger.info(f"RAG Retrieval took {rag_time:.2f}s")

    # METADATA 

    product = payout.get("product_name") or eligibility.get("product") or "Dermacline"
    period  = payout.get("period")       or eligibility.get("period")  or "this quarter"

    #  CONVERSATION HISTORY

    conversation_history = get_formatted_history(user_id)  

    prompt = ORCHESTRATION_PROMPT.format(
        rep_name=final_rep_name,             
        rep_role=rep_role,            
        conversation_history=conversation_history,
        rep_data=f"""
PRODUCT: {product}
PERIOD:  {period}

PAYOUT DATA:
{format_dict_for_llm(payout)}

ELIGIBILITY DATA:
{format_dict_for_llm(eligibility)}

CALCULATED VALUES:
{formatted_calc}

HCP COUNT:         {total_hcps}
TOTAL CREDITS:     {total_credits}

HCP CREDIT BREAKDOWN:
{hcp_breakdown}

HCP NAMES:
{hcp_names}
""",
        policy_context=policy_context,
        question=question,
    )

    start_llm = time.time()
    response = llm.generate(prompt)
    llm_time = time.time() - start_llm
    logger.info(f"LLM Generation took {llm_time:.2f}s")

    data_snapshot = dict(calc) if calc else {}
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
        user_id=user_id,
        question=question,
        response=response,
        data_snapshot=data_snapshot,
    )

    return response