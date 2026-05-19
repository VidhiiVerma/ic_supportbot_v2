def calculate_ic(rep_data):
    """
    Extracts pre-calculated values directly from the database record (Excel data).
    No Python math — all values come straight from your uploaded Excel sheet.
    """
    payout = rep_data.get("payout", {})
    if not payout:
        return None

    try:
        return {
            "qtd_trx": float(payout.get("qtd_trx", 0)),
            "goal": float(payout.get("qtd_trx_goal", 0)),
            "incremental": float(payout.get("total_projected_incremental_trx", 0)),
            "rate": float(payout.get("commission_rate", 0)),
            "commission": float(payout.get("commission_earnings_value", 0)),
            "ic_earnings": float(payout.get("ic_earnings_value", 0)),
            "total_ic": float(payout.get("total_ic_payout", payout.get("total__ic_earnings", 0))),
            "target_pay": float(payout.get("target_pay", 0)),
        }
    except Exception:
        return None