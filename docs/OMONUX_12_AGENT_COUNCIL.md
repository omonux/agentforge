# OMONUX Twelve-Agent Trading Council

## Purpose

The council adds twelve independent specialist reviews to OMONUX market research and the automatic paper-trading candidate gate. It is a research filter, not a source of guaranteed profitable trades.

## The twelve specialists

1. Market Regime Analyst — trend/range/transition conditions.
2. Trend Analyst — EMA structure and directional alignment.
3. Momentum Analyst — RSI and price momentum.
4. Volume Analyst — volume confirmation and participation.
5. Volatility Analyst — ATR, candle ranges and stop-distance risk.
6. Support & Resistance Analyst — nearby observed swing levels.
7. Multi-Timeframe Analyst — explicitly reports when only one timeframe is available.
8. Breakout Analyst — completed-candle range breaks, not intrabar guesses.
9. Mean-Reversion Analyst — stretched price and chase risk.
10. Liquidity & Execution Analyst — candle-based proxies only; no false claims about order-book depth or spread.
11. Strategy Analyst — checks the deterministic signal and proposed risk levels.
12. Skeptic / Red-Team Analyst — tries to disprove the candidate and can raise a critical veto.

Each specialist receives the same completed OHLCV evidence and produces a constrained JSON vote. Provider errors or invalid responses become failed/HOLD votes and block approval.

## Consensus policy

A candidate is approved for paper simulation only when all twelve specialists return valid votes, at least eight vote BUY, no more than one votes SELL, and no specialist raises a critical veto.

This is intentionally strict. A rejected candidate is a NO TRADE result, not a reason to lower the threshold automatically.

## Automatic paper-trading integration

- The deterministic EMA/RSI/ATR signal is checked first.
- The council runs only for a deterministic BUY candidate that meets the configured technical confidence threshold.
- At most one candidate is sent to the council per automatic cycle.
- The scheduler polls every five minutes, but persistent candle tracking prevents another automatic council run until a new completed 30-minute candle is available.
- Each council run makes twelve separate AI-provider requests; monitor token usage and provider billing.
- Existing position sizing, stop/target references, daily-loss limits, cooldown, maximum positions, trade-count limits and emergency-stop latch remain in force.
- The council has no exchange order-placement functions and cannot access live execution endpoints.
- The existing live execution area remains separate, manually confirmed and feature-flagged off by default.

## Important data limitations

Current council input is Binance public completed-candle OHLCV and the deterministic indicator signal. It does not include a verified news feed, social sentiment feed, order-book depth, bid/ask spread, funding rate, open interest, exchange-specific slippage, or independent multi-timeframe data. Specialists must say when evidence is unavailable rather than invent it.

## API

POST /api/v1/trading/agents/scan

Example body:

    {
      "symbol": "BTCUSDT",
      "timeframe": "30m"
    }

The endpoint returns the deterministic technical signal and all twelve votes. The dashboard displays the consensus and each specialist's reasoning.

## Operating guidance

Use this first in paper mode and compare decisions with realistic fees and slippage. Run a long historical walk-forward test and a separate out-of-sample period before considering any change to execution controls. A passing CI run or positive backtest is not proof of profitability. Never enable unattended real-money execution on the basis of the council vote.