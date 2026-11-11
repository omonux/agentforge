"""Read-only DEX opportunity simulation. Never signs or broadcasts transactions."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence

@dataclass(frozen=True)
class Quote:
    route: str
    amount_out: Decimal
    gas_usd: Decimal
    pool_fees_usd: Decimal
    price_impact_usd: Decimal
    quote_age_seconds: int

@dataclass(frozen=True)
class Evaluation:
    route: str
    net_profit_usd: Decimal
    net_return_percent: Decimal
    eligible: bool
    reason: str

def evaluate_routes(
    capital_usd: Decimal,
    quotes: Sequence[Quote],
    *,
    max_quote_age_seconds: int = 20,
    min_profit_usd: Decimal = Decimal("1"),
    max_price_impact_percent: Decimal = Decimal("1"),
) -> list[Evaluation]:
    """Assumes amount_out is denominated in USD; only comparable round trips qualify."""
    if not capital_usd.is_finite() or capital_usd <= 0:
        raise ValueError("capital_usd must be positive and finite")
    results = []
    for q in quotes:
        amounts = (q.amount_out, q.gas_usd, q.pool_fees_usd, q.price_impact_usd)
        if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in amounts):
            raise ValueError("quote amounts must be finite, nonnegative Decimals")
        if q.quote_age_seconds < 0:
            raise ValueError("quote age must be nonnegative")
        net = q.amount_out - capital_usd - q.gas_usd - q.pool_fees_usd - q.price_impact_usd
        impact_pct = q.price_impact_usd * Decimal("100") / capital_usd
        if q.quote_age_seconds > max_quote_age_seconds:
            reason = "stale quote"
        elif impact_pct > max_price_impact_percent:
            reason = "price impact exceeds limit"
        elif net < min_profit_usd:
            reason = "insufficient estimated net profit"
        else:
            reason = "simulation candidate; manual review required"
        results.append(Evaluation(q.route, net, net * Decimal("100") / capital_usd,
                                  reason.startswith("simulation candidate"), reason))
    return sorted(results, key=lambda r: r.net_profit_usd, reverse=True)
