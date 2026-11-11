"""Fail-closed MT5 demo auto-trade decision gate; no broker order execution.

Caller must supply independently verified, fresh broker/risk snapshots.
This module NEVER calls TickerAll or enables transport flags.
"""
from dataclasses import dataclass
from decimal import Decimal

D = Decimal

@dataclass(frozen=True)
class DemoSnapshot:
    is_demo: bool
    broker_online: bool
    session_hot: bool
    account_equity: Decimal
    daily_realized_pnl: Decimal
    open_positions: int
    positions_verified: bool
    snapshot_age_seconds: int
    kill_switch_engaged: bool
    pending_order_exists: bool

@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    side: str
    entry: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    risk_usd: Decimal
    council_approvals: int
    council_total: int
    manual_approval: bool

@dataclass(frozen=True)
class GateDecision:
    approved_for_demo_review: bool
    reasons: tuple[str, ...]

def evaluate(snapshot: DemoSnapshot, trade: TradeProposal) -> GateDecision:
    """Review only. Never authorize network order submission."""
    reasons = []
    def reject(condition: bool, reason: str) -> None:
        if condition:
            reasons.append(reason)
    reject(not snapshot.is_demo, "account not verified as demo")
    reject(not snapshot.broker_online or not snapshot.session_hot, "broker session not ready")
    reject(not snapshot.positions_verified or snapshot.snapshot_age_seconds < 0
           or snapshot.snapshot_age_seconds > 15, "broker snapshot stale or unverified")
    reject(snapshot.kill_switch_engaged, "kill switch engaged")
    reject(snapshot.pending_order_exists, "unreconciled pending order")
    reject(snapshot.open_positions != 0, "maximum one open position")
    values = (snapshot.account_equity, snapshot.daily_realized_pnl, trade.entry,
              trade.stop_loss, trade.take_profit, trade.risk_usd)
    reject(any(not isinstance(v, D) or not v.is_finite() for v in values),
           "nonfinite or invalid numeric input")
    if not reasons or all(r != "nonfinite or invalid numeric input" for r in reasons):
        reject(snapshot.account_equity <= 0, "equity unavailable")
        reject(trade.risk_usd <= 0 or trade.risk_usd > snapshot.account_equity * D("0.0025"),
               "risk exceeds 0.25 percent of equity")
        reject(snapshot.daily_realized_pnl <= -snapshot.account_equity * D("0.01"),
               "daily loss limit reached")
        reject(trade.entry <= 0 or trade.stop_loss <= 0 or trade.take_profit <= 0,
               "invalid protective prices")
        reject(trade.side not in ("BUY", "SELL"), "invalid side")
        if trade.side == "BUY":
            reject(not (trade.stop_loss < trade.entry < trade.take_profit),
                   "BUY stop/target direction invalid")
        if trade.side == "SELL":
            reject(not (trade.take_profit < trade.entry < trade.stop_loss),
                   "SELL stop/target direction invalid")
    reject(trade.symbol not in ("EURUSD", "GBPUSD", "USDJPY"), "symbol not allowlisted")
    reject(trade.council_total != 12 or trade.council_approvals < 10
           or trade.council_approvals > trade.council_total,
           "council consensus insufficient")
    reject(not trade.manual_approval, "manual approval required")
    return GateDecision(not reasons, tuple(reasons))
