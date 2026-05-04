from app.db import get_rep_data
from app.formatter import format_value, format_calc_for_llm, format_number
from app.prompts import POLICY_PROMPT, EXPLANATION_PROMPT, WHY_PROMPT
import logging

logger = logging.getLogger(__name__)



# ---------------- INTENT DETECTION ---------------- #

def detect_intents(q: str):
    q_lower = q.lower().strip()

    if q_lower in ("hi", "hello", "hey"):
        return ["greeting"]
    if "thank" in q_lower:
        return ["thanks"]

    intents = []

    if any(t in q_lower for t in ("what is", "show", "give", "list", "who", "which", "how many", "count", "total")):
        intents.append("direct_data")

    if any(t in q_lower for t in ("explain", "how is", "breakdown", "calculate", "calculated", "calculation")):
        intents.append("explanation")
        
    if any(t in q_lower for t in ("eligibility", "eligible", "new hire")):
        intents.append("eligibility")

    if "why" in q_lower:
        intents.append("why")

    if any(t in q_lower for t in ("hcp", "doctor", "physician")):
        intents.append("sales_data")

    return intents if intents else ["policy"]


# ---------------- CREDIT CALCULATION ---------------- #

def calculate_credit(row):
    try:
        trx = float(row.get("dermacline_trx", 0))
        flag = float(row.get("final_ic_cm_flag", 0))
        pct = float(row.get("assignment_pct", 0))
        return trx * flag * pct
    except:
        return 0


# ---------------- HCP COUNT (NPI BASED) ---------------- #

def count_unique_hcps(rows):
    return len({
        str(r.get("npi")).strip()
        for r in rows
        if r.get("npi")
    })


# ---------------- MONTH FILTER (BASIC) ---------------- #

def filter_by_month(rows, question):
    q = question.lower()

    # extend later if needed
    if "jan 2026" in q:
        return [
            r for r in rows
            if "jan 2026" in str(r.get("month", "")).lower()
        ]

    return rows


# ---------------- CREDIT QUERY ---------------- #

def handle_credit_query(rows, question):
    rows = filter_by_month(rows, question)

    # Calculate breakdown
    hcp_totals = {}
    for r in rows:
        credit = calculate_credit(r)
        if credit > 0:
            name = str(r.get("hcp_name", "Unknown HCP")).strip()
            hcp_totals[name] = hcp_totals.get(name, 0) + credit

    if not hcp_totals:
        return "No credits found for the specified criteria."

    # Formula explanation
    lines = [
        "1. Credit Calculation:",
        "For each record: credit = dermacline_trx * final_ic_cm_flag * assignment_pct",
        "",
        "HCP Credit Breakdown:"
    ]

    # HCP list
    for name in sorted(hcp_totals.keys()):
        lines.append(f"{name}: {format_number(hcp_totals[name])}")

    lines.append("-" * 25)
    total_credit = sum(hcp_totals.values())
    lines.append(f"TOTAL CREDITS: {format_number(total_credit)}")

    return "\n".join(lines)


# ---------------- HCP QUERY ---------------- #

def handle_hcp_query(rows, question):
    q_lower = question.lower()

    # COUNT QUERY
    if any(t in q_lower for t in ("how many", "count", "total")):
        return str(count_unique_hcps(rows))

    # LIST QUERY
    names = {
        str(r.get("hcp_name")).strip()
        for r in rows
        if r.get("hcp_name")
    }

    return ", ".join(sorted(names)) if names else "data not available"


# ---------------- HCP INCLUSION ---------------- #

def check_hcp_inclusion(rows, question):
    q = question.lower()
    rows = filter_by_month(rows, question)

    matched = []

    for r in rows:
        hcp = str(r.get("hcp_name", "")).lower()
        if hcp and hcp in q:
            matched.append(r)

    if not matched:
        return "HCP not found"

    # check ANY row eligible
    included = any(float(r.get("final_ic_cm_flag", 0)) == 1 for r in matched)

    if included:
        total_credit = sum(calculate_credit(r) for r in matched)
        return f"Yes, included. Total credit = {round(total_credit, 2)}"
    else:
        return "No, excluded because final_ic_cm_flag = 0"


# ---------------- DETERMINISTIC FIELD MAPPING ---------------- #

FIELD_SYNONYMS = {
    "target pay": "target_pay",
    "base pay": "target_pay",
    "ic earnings rate": "ic_earnings_rate",
    "ic earning rate": "ic_earnings_rate",
    "ic rate": "ic_earnings_rate",
    "goal achievement rate": "goal_achievement_rate",
    "achievement rate": "goal_achievement_rate",
    "gar": "goal_achievement_rate",
    "ic earnings value": "ic_earnings_value",
    "base ic": "ic_earnings_value",
    "total projected incremental trx": "total_projected_incremental_trx",
    "incremental trx": "total_projected_incremental_trx",
    "incremental": "total_projected_incremental_trx",
    "commission rate": "commission_rate",
    "commission earnings value": "commission_earnings_value",
    "commission earnings": "commission_earnings_value",
    "commission": "commission_earnings_value",
    "total ic earnings": "total_ic_earnings",
    "total ic payout": "total_ic_payout",
    "ic payout": "total_ic_payout",
    "total payout": "total_ic_payout",
    "total ic": "total_ic_payout",
    "payout": "total_ic_payout",
    "total trx goal": "total_trx_goal",
    "qtd trx goal": "qtd_trx_goal",
    "trx goal": "qtd_trx_goal",
    "goal": "qtd_trx_goal",
    "qtd trx": "qtd_trx",
    "trx": "qtd_trx",
    "qtd ic earnings rate": "qtd_ic_earnings_rate",
    "qtd earnings rate": "qtd_ic_earnings_rate",
    "new hire eligibility": "new_hire_eligibility",
    "ic eligibility": "ic_eligibility",
    "total eligibility": "total_eligibility",
    "new hire days": "new_hire_eligible_days",
    "ic days": "ic_eligible_days",
    "total days": "total_days_in_qtr",
    "hire date": "hire_date",
}

def detect_field(q_lower: str):
    matched_field = None
    max_len = 0
    for syn, field in FIELD_SYNONYMS.items():
        if syn in q_lower:
            if len(syn) > max_len:
                max_len = len(syn)
                matched_field = field
    return matched_field

def handle_direct_data(question, rep_data):
    q_lower = question.lower()
    field = detect_field(q_lower)
    
    logger.info(f"Direct data query: '{question}' -> Mapped field: '{field}'")
    
    if not field:
        return None

    payout = rep_data.get("payout", {})
    eligibility = rep_data.get("eligibility", {})

    val = payout.get(field) if field in payout else eligibility.get(field)
    
    logger.info(f"Fetched value for {field}: {val}")

    if val is not None:
        return format_value(field, val)
    return None

# ---------------- EXISTING IC CALC ---------------- #
def calculate_ic(rep_data):
    if not rep_data or not rep_data.get("payout"):
        return None

    payout = rep_data["payout"]

    try:
        qtd_trx = float(payout.get("qtd_trx", 0))
        goal = float(payout.get("qtd_trx_goal", 0))
        target_pay = float(payout.get("target_pay", 0))
        ic_rate = float(payout.get("ic_earning_rate", payout.get("ic_earnings_rate", 0)))

        incremental = max(0.0, qtd_trx - goal)

        if incremental <= 50:
            rate = 10
        elif incremental <= 100:
            rate = 20
        else:
            rate = 30

        commission = incremental * rate
        ic_earnings = target_pay * ic_rate
        total_ic = ic_earnings + commission

        return {
            "qtd_trx": qtd_trx,
            "goal": goal,
            "incremental": incremental,
            "rate": rate,
            "commission": commission,
            "ic_earnings": ic_earnings,
            "total_ic": total_ic,
            "target_pay": target_pay,
        }

    except:
        return None


# ---------------- MAIN FUNCTION ---------------- #

def get_rep_explanation(rep_id, question, rag, llm):

    rep_data = get_rep_data(rep_id)
    if not rep_data:
        return "No data found for this rep_id"

    intents = detect_intents(question)

    if "greeting" in intents:
        return "Hello. How can I assist?"
    if "thanks" in intents:
        return "You're welcome."

    sales_all = rep_data.get("sales", [])

    # filter rep rows
    rows = [
        r for r in sales_all
        if str(r.get("assignment_emp")) == str(rep_id)
    ]

    q_lower = question.lower()

    # ---------------- DIRECT DATA ---------------- #
    # If it's an explanation request, skip direct data lookup to allow explanation logic to run
    if "direct_data" in intents and "explanation" not in intents:
        val = handle_direct_data(question, rep_data)
        if val is not None:
            return val

    # ---------------- CREDIT ---------------- #
    if "credit" in q_lower or "trx" in q_lower:
        return handle_credit_query(rows, question)

    # ---------------- HCP INCLUSION ---------------- #
    if "include" in q_lower:
        return check_hcp_inclusion(rows, question)

    # ---------------- HCP ---------------- #
    if "hcp" in q_lower or "doctor" in q_lower:
        return handle_hcp_query(rows, question)

    # ---------------- ELIGIBILITY ---------------- #
    if "eligibility" in intents:
        eligibility = rep_data.get("eligibility", {})
        if eligibility:
            if "explanation" in intents:
                # Use RAG to get the policy definition and combine with personal data
                context = rag.get_context(question) if rag else ""
                prompt = WHY_PROMPT.format(
                    formatted_data=str(eligibility),
                    policy_context=context,
                    question=question
                )
                return llm.generate(prompt)
            
            # Fallback to structured personal data if just asking for info
            nh_days = eligibility.get("new_hire_eligible_days", 0)
            nh_frac = float(eligibility.get("new_hire_eligibility", 0) or 0)
            ic_days = eligibility.get("ic_eligible_days", 0)
            tot_days = eligibility.get("total_days_in_qtr", 0)
            ic_frac = float(eligibility.get("ic_eligibility", 0) or 0)
            tot_frac = float(eligibility.get("total_eligibility", 0) or 0)
            reason = eligibility.get("eligibility_reason", "")
            
            exp = f"Your total eligibility is {format_value('total_eligibility', tot_frac)}. This is based on {ic_days} IC eligible days ({format_value('ic_eligibility', ic_frac)})"
            if nh_days and float(nh_days) > 0:
                exp += f" and {nh_days} new hire eligible days ({format_value('new_hire_eligibility', nh_frac)})"
            exp += f" out of {tot_days} total days in the quarter."
            if reason and str(reason).lower() not in ("nan", "none", ""):
                exp += f" Reason: {reason}."
            return exp

    # ---------------- IC EXPLANATION ---------------- #
    if "explanation" in intents:
        if any(t in q_lower for t in ("total credit", "ic earning", "total ic", "calculate", "calculated", "calculation", "payout", "earnings")):
            payout = rep_data.get("payout", {})
            eligibility = rep_data.get("eligibility", {})
            if payout:
                ic_val = float(payout.get("ic_earnings_value", payout.get("ic_earnings", 0)) or 0)
                comm_val = float(payout.get("commission_earnings_value", payout.get("commission", 0)) or 0)
                tot_elig = float(eligibility.get("total_eligibility", payout.get("total_eligibility", 1.0)) or 1.0)
                total_ic = float(payout.get("total_ic_earnings", payout.get("total_ic_payout", 0)) or 0)
                
                return (
                    f"IC Payout Breakdown:\n"
                    f"Base IC Earnings + Commission Earnings = Total (Prorated by Eligibility)\n"
                    f"({format_value('ic_earnings_value', ic_val)} + {format_value('commission_earnings_value', comm_val)}) * {format_value('total_eligibility', tot_elig)}\n"
                    f"Total Payout: {format_value('total_ic_payout', total_ic)}"
                )

    calc = calculate_ic(rep_data)

    if "explanation" in intents and calc:
        prompt = EXPLANATION_PROMPT.format(
            formatted_data=format_calc_for_llm(calc),
            question=question
        )
        return llm.generate(prompt)

    if "why" in intents and calc:
        prompt = WHY_PROMPT.format(
            formatted_data=format_calc_for_llm(calc),
            policy_context=rag.get_context(question) if rag else "",
            question=question,
        )
        return llm.generate(prompt)

    # ---------------- POLICY ---------------- #
    context = rag.get_context(question) if rag else ""
    prompt = POLICY_PROMPT.format(context=context, question=question)

    return llm.generate(prompt)