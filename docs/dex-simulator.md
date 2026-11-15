# DEX swap simulator (non-executing foundation)

This module evaluates **hypothetical USD-denominated round-trip quotes**. It does not retrieve live market prices, place orders, connect wallets, sign transactions, or broadcast swaps. No trading profitability is guaranteed.

Use `backend/app/dex_simulator.py` to evaluate comparable routes with gas, pool fees, price impact, staleness, and minimum net profit. Run `PYTHONPATH=backend pytest -q backend/tests/test_dex_simulator.py`.

Before production integration: add verified Uniswap V3 quoter/chain RPC sources, token allowlists, precise token decimal conversion, exact route and path validation, gas estimation, price impact/slippage modeling, fork simulation, MEV exposure assessment, audit, authorization, and manual approval. Do not connect this to live trade execution. Existing MT5 and crypto trading safety controls remain untouched.
