def calculate_ic(rep_data):

    payout = rep_data.get("payout", {})

    if not payout:
        return None

    try:
        qtd_trx = float(payout.get("qtd_trx", 0))

        goal = float(payout.get("qtd_trx_goal", 0))

        target_pay = float(payout.get("target_pay", 0))

        ic_rate = float(
            payout.get(
                "ic_earning_rate",
                payout.get("ic_earnings_rate", 0),
            )
        )

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

    except Exception:
        return None