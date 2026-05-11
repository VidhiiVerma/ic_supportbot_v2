from app.formatter import format_number


def calculate_credit(row):
    try:
        trx = float(row.get("dermacline_trx", 0))
        flag = float(row.get("final_ic_cm_flag", 0))
        pct = float(row.get("assignment_pct", 0))

        return trx * flag * pct

    except Exception:
        return 0


def filter_by_month(rows, question):
    q = question.lower()

    if "jan 2026" in q:
        return [
            r for r in rows
            if "jan 2026" in str(r.get("month", "")).lower()
        ]

    return rows


def build_hcp_totals(rows):
    hcp_totals = {}

    for row in rows:
        credit = calculate_credit(row)
        raw_trx = float(row.get("dermacline_trx", 0))

        if credit <= 0 and raw_trx <= 0:
            continue

        hcp_name = str(row.get("hcp_name", "Unknown HCP")).strip()

        if hcp_name not in hcp_totals:
            hcp_totals[hcp_name] = {"credit": 0, "raw_trx": 0}

        hcp_totals[hcp_name]["credit"] += credit
        hcp_totals[hcp_name]["raw_trx"] += raw_trx

    return hcp_totals


def get_total_credits(rows, question):
    rows = filter_by_month(rows, question)
    totals = build_hcp_totals(rows)
    total_credit = sum(t["credit"] for t in totals.values())
    return f"Total credits: {format_number(total_credit)}"


def get_hcp_credit_breakdown(rows, question):
    rows = filter_by_month(rows, question)
    totals = build_hcp_totals(rows)

    if not totals:
        return "No credits found."

    lines = []
    for idx, (name, stats) in enumerate(
        sorted(totals.items()),
        start=1
    ):
        lines.append(
            f"{idx}. {name}: {format_number(stats['credit'])} credits (from {format_number(stats['raw_trx'])} raw TRx)"
        )

    return "\n".join(lines)


def get_hcp_names(rows):
    names = sorted({
        str(r.get("hcp_name")).strip()
        for r in rows
        if r.get("hcp_name")
    })

    if not names:
        return "data not available"

    return "\n".join(
        f"{idx}. {name}"
        for idx, name in enumerate(names, start=1)
    )


def count_unique_hcps(rows):
    unique = {
        str(r.get("npi")).strip()
        for r in rows
        if r.get("npi")
    }

    return len(unique)


def check_hcp_inclusion(rows, question):
    q = question.lower()

    matched = []

    for row in rows:
        hcp = str(row.get("hcp_name", "")).lower()

        if hcp and hcp in q:
            matched.append(row)

    if not matched:
        return "HCP not found"

    included = any(
        float(r.get("final_ic_cm_flag", 0)) == 1
        for r in matched
    )

    if included:
        total_credit = sum(
            calculate_credit(r)
            for r in matched
        )

        return (
            f"Yes, included. "
            f"Total credit = {round(total_credit, 2)}"
        )

    return "No, excluded because final_ic_cm_flag = 0"