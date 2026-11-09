"""Conservative paper-only trailing stop logic.

The initial stop is never widened. Trailing starts only after a favorable
one-risk move, and is monotonic in the profitable direction.
"""


def trailing_stop(side: str, entry: float, stop: float, favorable_extreme: float,
                  *, activation_r: float = 1.0, trail_r: float = 0.75) -> float:
    if side not in ("BUY", "SELL") or min(entry, stop, favorable_extreme) <= 0:
        raise ValueError("Invalid paper position")
    if activation_r <= 0 or trail_r <= 0:
        raise ValueError("Invalid trailing parameters")
    if side == "BUY":
        risk = entry - stop
        if risk <= 0:
            raise ValueError("Invalid BUY stop")
        if favorable_extreme < entry + activation_r * risk:
            return stop
        return max(stop, entry, favorable_extreme - trail_r * risk)
    risk = stop - entry
    if risk <= 0:
        raise ValueError("Invalid SELL stop")
    if favorable_extreme > entry - activation_r * risk:
        return stop
    return min(stop, entry, favorable_extreme + trail_r * risk)
