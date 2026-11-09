"""Conservative adaptive USDT stake sizing for paper trading only.

Stake is limited by stop-distance risk, available cash, portfolio notional
limit, and a bounded confidence tier. Never uses leverage.
"""
from __future__ import annotations
import math


def adaptive_paper_quantity(*, price: float, stop: float, equity: float,
                            available_cash: float, risk_percent: float,
                            max_notional_percent: float, confidence: float,
                            min_stake: float = 1.0, max_stake: float = 10.0) -> tuple[float, dict]:
    values=(price,stop,equity,available_cash,risk_percent,max_notional_percent,confidence,min_stake,max_stake)
    if any(not math.isfinite(v) for v in values) or price<=0 or stop<=0 or equity<=0 or available_cash<0:
        raise ValueError("Invalid paper sizing inputs")
    if not (0<risk_percent<=5 and 0<max_notional_percent<=100 and 0<=confidence<=100 and 0<min_stake<=max_stake):
        raise ValueError("Invalid paper sizing limits")
    stop_distance=abs(price-stop)
    if stop_distance<1e-12:
        return 0.0,{"reason":"Stop distance too small"}
    # More confidence can allocate more, but confidence is not a probability.
    tier=0 if confidence<75 else 1 if confidence<85 else 2 if confidence<92 else 3
    preferred=(1.0,3.0,5.0,10.0)[tier]
    stake=min(preferred,max_stake,equity*max_notional_percent/100,
              available_cash,equity*risk_percent/100*price/stop_distance)
    if stake<min_stake:
        return 0.0,{"reason":"Insufficient cash or risk budget for minimum paper stake",
                    "maximum_affordable_stake":round(stake,6)}
    return stake/price,{"stake_usdt":round(stake,6),"preferred_stake_usdt":preferred,
                        "confidence_tier":tier,"leverage":1,"mode":"paper_only"}
