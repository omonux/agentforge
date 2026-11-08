-- AgentForge PostgreSQL trading audit foundation.
-- Tested on Neon development branch dev-agentforge-trading-foundation.
-- Additive only; no live trading enabled; no secrets stored.
CREATE SCHEMA IF NOT EXISTS agentforge;

CREATE TABLE IF NOT EXISTS agentforge.council_decisions (
  id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  exchange text NOT NULL CHECK (exchange IN ('binance','bybit')),
  symbol text NOT NULL CHECK (symbol ~ '^[A-Z0-9]{5,20}$'),
  timeframe text NOT NULL,
  recommendation text NOT NULL CHECK (recommendation IN ('BUY','SELL','HOLD','VETO')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  votes jsonb NOT NULL DEFAULT '[]'::jsonb,
  execution_authorized boolean NOT NULL DEFAULT false CHECK (execution_authorized = false)
);

CREATE TABLE IF NOT EXISTS agentforge.order_intents (
  id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  exchange text NOT NULL CHECK (exchange IN ('binance','bybit')),
  symbol text NOT NULL CHECK (symbol ~ '^[A-Z0-9]{5,20}$'),
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  quantity numeric(38,18) NOT NULL CHECK (quantity > 0),
  client_order_id text NOT NULL,
  status text NOT NULL DEFAULT 'PROPOSED'
    CHECK (status IN ('PROPOSED','REJECTED','SIMULATED','CANCELLED')),
  council_decision_id uuid REFERENCES agentforge.council_decisions(id),
  UNIQUE(exchange,client_order_id)
);

CREATE TABLE IF NOT EXISTS agentforge.risk_events (
  id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  exchange text CHECK (exchange IN ('binance','bybit')),
  symbol text,
  event_type text NOT NULL,
  reason text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  order_intent_id uuid REFERENCES agentforge.order_intents(id)
);

CREATE TABLE IF NOT EXISTS agentforge.portfolio_snapshots (
  id uuid PRIMARY KEY,
  observed_at timestamptz NOT NULL,
  exchange text NOT NULL CHECK (exchange IN ('binance','bybit')),
  equity_usdt numeric(38,18) NOT NULL CHECK (equity_usdt >= 0),
  available_usdt numeric(38,18) NOT NULL CHECK (available_usdt >= 0),
  source text NOT NULL CHECK (source IN ('verified_exchange','paper_simulation')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS council_decisions_created_idx ON agentforge.council_decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS order_intents_created_idx ON agentforge.order_intents(created_at DESC);
CREATE INDEX IF NOT EXISTS risk_events_created_idx ON agentforge.risk_events(created_at DESC);
CREATE INDEX IF NOT EXISTS portfolio_snapshots_exchange_time_idx ON agentforge.portfolio_snapshots(exchange,observed_at DESC);
