"""Read-only paper trading performance metrics. No exchange order placement."""
from __future__ import annotations
import math

def paper_performance(exit_events: list[dict], starting_balance: float = 100.0) -> dict:
    """Realized-only equity curve, using recorded P&L (historical gross may remain).

    Drawdown excludes unrealized mark-to-market fluctuations. Profit factor is
    undefined when there are no losses, rather than an invented infinite value.
    """
    ordered=sorted((e for e in exit_events if e.get("event_type")=="PAPER_EXIT"),
                   key=lambda e:(str(e.get("created") or ""),str(e.get("id") or "")))
    equity=peak=float(starting_balance)
    max_drawdown=0.0
    wins=losses=breakeven=0
    gross_wins=gross_losses=0.0
    curve=[{"time":None,"equity":round(equity,6),"drawdown_percent":0.0}]
    for event in ordered:
        pnl=float(event.get("pnl") or 0)
        if not math.isfinite(pnl):
            raise ValueError("Invalid paper P&L")
        if pnl>0:
            wins+=1; gross_wins+=pnl
        elif pnl<0:
            losses+=1; gross_losses+=abs(pnl)
        else:
            breakeven+=1
        equity+=pnl
        peak=max(peak,equity)
        drawdown=100*(peak-equity)/peak if peak>0 else 0.0
        max_drawdown=max(max_drawdown,drawdown)
        curve.append({"time":event.get("created"),"equity":round(equity,6),
                      "drawdown_percent":round(drawdown,4)})
    count=len(ordered)
    return {"closed_trades":count,"wins":wins,"losses":losses,"breakeven":breakeven,
            "win_rate_percent":round(100*wins/count,2) if count else None,
            "realized_pnl":round(equity-starting_balance,6),
            "average_win":round(gross_wins/wins,6) if wins else None,
            "average_loss":round(-gross_losses/losses,6) if losses else None,
            "profit_factor":round(gross_wins/gross_losses,4) if gross_losses else None,
            "max_realized_drawdown_percent":round(max_drawdown,4),
            "equity_curve":curve,
            "notice":"Realized-only drawdown. New exits use estimated net costs; historical exits may record gross P&L. No live exchange orders."}
