import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
import { apiFetch, API } from "./api";
import "./omonux-live-research.css";

type ResearchCard = {
  symbol: string;
  market: "CRYPTO" | "FOREX";
  side?: string;
  confidence?: number;
  entry?: number;
  stop?: number;
  target?: number;
  source?: string;
  time?: string | number;
  note?: string;
  error?: string;
};

const cryptoSymbols = "BTCUSDT,ETHUSDT,SOLUSDT";
const forexSymbols = ["EURUSD", "GBPUSD", "USDJPY"];

function price(value?: number) {
  if (value == null || !Number.isFinite(Number(value))) return "Unavailable";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function timeLabel(value?: string | number) {
  if (value == null) return "Time unavailable";
  const date = new Date(typeof value === "number" ? value : value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

function signalCard(symbol: string, market: ResearchCard["market"], payload: any): ResearchCard {
  const signal = payload?.signal ?? payload;
  const plan = payload?.trade_plan;
  const side = String(plan?.side ?? signal?.side ?? "HOLD").toUpperCase();
  const isCandidate = side === "BUY" || side === "SELL";
  return {
    symbol,
    market,
    side,
    confidence: signal?.confidence ?? signal?.score,
    entry: plan?.entry_reference ?? signal?.price ?? signal?.latest_closed_price,
    stop: plan?.stop_loss_reference ?? signal?.risk_levels?.stop_reference,
    target: plan?.take_profit_reference ?? signal?.risk_levels?.target_reference,
    source: signal?.source ?? payload?.source ?? (market === "CRYPTO" ? "Binance public closed candles" : "TickerAll MT5 demo candles"),
    time: signal?.candle_time ?? signal?.timestamp,
    note: !isCandidate ? "No directional setup passed the current research rules." :
      plan?.notice ?? "Research reference only. Confirm current price, spread, contract size, and risk with your broker.",
  };
}

export default function OmonuxLiveResearch() {
  const [cards, setCards] = useState<ResearchCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setBusy(true);
    setError("");
    const next: ResearchCard[] = [];
    try {
      const response = await apiFetch(API + "/api/v1/trading/signals?symbols=" + cryptoSymbols + "&interval=30m");
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Crypto market data is unavailable");
      for (const item of data?.signals ?? []) {
        if (item?.status === "unavailable") {
          next.push({ symbol: item.symbol, market: "CRYPTO", error: item.error || "Market data unavailable" });
        } else next.push(signalCard(item.symbol, "CRYPTO", item));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Crypto research unavailable");
      for (const symbol of cryptoSymbols.split(",")) next.push({ symbol, market: "CRYPTO", error: "Could not retrieve fresh market data" });
    }

    const forex = await Promise.all(forexSymbols.map(async symbol => {
      try {
        const response = await apiFetch(API + "/api/v1/trading/forex/research/" + symbol + "?timeframe=M30&hours=168");
        const data = await response.json();
        if (!response.ok) throw new Error(data?.detail || "Forex research unavailable");
        return signalCard(symbol, "FOREX", data);
      } catch (e) {
        return { symbol, market: "FOREX" as const, error: e instanceof Error ? e.message : "TickerAll research unavailable" };
      }
    }));
    next.push(...forex);
    setCards(next);
    setUpdated(new Date().toLocaleTimeString());
    setBusy(false);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return <section className="panel omx-live-research" aria-label="Live market research">
    <div className="portfoliohead">
      <div><h3>Live market research &amp; trade plans</h3><small>Crypto and Forex · latest completed candles · refreshed every minute</small></div>
      <button className="secondary" type="button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={14}/>{busy ? "Refreshing…" : "Refresh markets"}</button>
    </div>
    <div className="omx-live-notice"><ShieldCheck size={16}/><span>Read-only research. Entry, stop, and target are references for your review; this screen cannot submit broker or exchange orders.</span></div>
    {error && <p className="omx-live-error" role="status">{error}</p>}
    <div className="omx-live-grid">
      {cards.map(card => <article className="omx-live-card" key={card.market + card.symbol}>
        <div className="omx-live-card-head"><div><span className="omx-live-market">{card.market}</span><h4>{card.symbol}</h4></div>
          {card.error ? <span className="omx-live-status unavailable">UNAVAILABLE</span> :
            <span className={"omx-live-status " + (card.side === "BUY" ? "buy" : card.side === "SELL" ? "sell" : "hold")}>
              {card.side === "BUY" ? <TrendingUp size={13}/> : card.side === "SELL" ? <TrendingDown size={13}/> : <Activity size={13}/>}{card.side || "HOLD"}
            </span>}
        </div>
        {card.error ? <p className="omx-live-error">{card.error}</p> : <>
          <div className="omx-live-levels"><div><small>Entry reference</small><b>{price(card.entry)}</b></div><div><small>Stop loss</small><b>{price(card.stop)}</b></div><div><small>Take profit</small><b>{price(card.target)}</b></div></div>
          <p className="omx-live-note">{card.note}</p>
          <small className="omx-live-source">{card.source || "Verified source unavailable"} · candle {timeLabel(card.time)}{card.confidence != null ? ` · confidence ${card.confidence}%` : ""}</small>
        </>}
      </article>)}
      {!cards.length && <div className="omx-live-empty">{busy ? "Loading market research…" : "No market results yet. Refresh to try again."}</div>}
    </div>
    <small className="omx-live-updated">Last refresh: {updated || "Waiting for market data"}. A delayed, stale, or incomplete feed is not a trade signal.</small>
  </section>;
}
