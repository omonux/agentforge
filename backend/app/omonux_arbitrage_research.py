"""Read-only cross-venue spot price discrepancy analysis.

Mid/last prices are not executable quotes. Never describe these results as
realized or guaranteed arbitrage profits; no orders are submitted.
"""
from __future__ import annotations

from math import isfinite


def analyze_discrepancy(binance_price: float, bybit_price: float, *,
                        roundtrip_fee_bps: float = 20.0,
                        roundtrip_slippage_bps: float = 10.0,
                        extra_cost_bps: float = 5.0,
                        min_net_edge_bps: float = 10.0) -> dict:
    values = (binance_price, bybit_price, roundtrip_fee_bps,
              roundtrip_slippage_bps, extra_cost_bps, min_net_edge_bps)
    if not all(isfinite(float(v)) for v in values):
        raise ValueError("Inputs must be finite")
    if min(binance_price, bybit_price) <= 0 or min(values[2:]) < 0:
        raise ValueError("Prices must be positive and cost assumptions nonnegative")
    buy_venue, sell_venue = ("binance", "bybit") if binance_price <= bybit_price else ("bybit", "binance")
    buy_price, sell_price = sorted((float(binance_price), float(bybit_price)))
    gross_edge_bps = (sell_price - buy_price) / buy_price * 10000
    total_cost_bps = roundtrip_fee_bps + roundtrip_slippage_bps + extra_cost_bps
    net_edge_bps = gross_edge_bps - total_cost_bps
    return {
        "buy_venue": buy_venue, "sell_venue": sell_venue,
        "buy_reference_price": buy_price, "sell_reference_price": sell_price,
        "gross_edge_bps": round(gross_edge_bps, 3),
        "assumed_total_cost_bps": round(total_cost_bps, 3),
        "estimated_net_edge_bps": round(net_edge_bps, 3),
        "passes_assumed_cost_threshold": net_edge_bps >= min_net_edge_bps,
        "executable": False, "execution": "research_only_no_order_placed",
        "warning": "Closed-candle prices are not simultaneous executable bid/ask quotes. A positive estimate is NOT an arbitrage opportunity: order-book depth, timing, inventory, funding and venue-specific fees are unverified.",
    }
