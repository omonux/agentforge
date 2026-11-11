# AgentForge MT5 demo auto-trade safety gate (stage 1)

This is a **pure, non-executing** decision gate. It does not trade autonomously, connect to the broker, or place orders. It only evaluates proposed DEMO trades against strict safety constraints.

Checks: verified demo identity, online/hot session, recent verified position roster, no open/pending order, emergency kill switch, max 0.25% estimated risk per trade, 1% realized daily loss cutoff, protective SL/TP direction, 10/12 council approval, allowlisted symbols, manual approval. The gate cannot verify risk sizing or the accuracy of input snapshots by itself.

**Not yet implemented:** persistent broker-backed kill switch, risk sizing from contract specifications, trustworthy daily P&L snapshots, duplicate order journal, order reconciliation, market-data freshness and spread checks, authenticated approval API, broker SL/TP acceptance and read-back, scheduled trading loop, production monitoring. These must be verified before connecting to the existing transport. Real-money trading remains prohibited.

Run: `PYTHONPATH=backend pytest -q backend/tests/test_demo_autotrade_gate.py`.
