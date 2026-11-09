"""Conservative early profit-taking for simulated positions only."""
from __future__ import annotations
import math

def early_profit_decision(*, side: str, entry: float, current: float,
                          quantity: float, minimum_net_usdt: float = .05,
                          round_trip_cost_bps: float = 20.0) -> tuple[bool,float,float]:
    """Return (close, estimated net P&L, estimated total costs).

    Cost estimate includes both sides of the trade and a slippage allowance.
    No promise of executable price or realized profit is implied.
    """
    if side not in ("BUY","SELL") or any(
        not math.isfinite(v) for v in
        (entry,current,quantity,minimum_net_usdt,round_trip_cost_bps)
    ) or min(entry,current,quantity)<=0 or minimum_net_usdt<=0 or round_trip_cost_bps<0:
        raise ValueError("Invalid paper profit inputs")
    gross=(current-entry)*quantity*(1 if side=="BUY" else -1)
    costs=(entry+current)*.5*quantity*round_trip_cost_bps/10000
    net=gross-costs
    return net>=minimum_net_usdt,net,costs
