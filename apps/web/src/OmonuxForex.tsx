import {useEffect,useState} from "react";
import {apiFetch,API} from "./api";

type ForexStatus={feed_configured:boolean;execution_enabled:boolean;mode:string;markets:string[];next_step:string};
export default function OmonuxForex(){
 const [status,setStatus]=useState<ForexStatus|null>(null);
 const [symbol,setSymbol]=useState("EURUSD");
 const [side,setSide]=useState("BUY");
 const [quote,setQuote]=useState<any>(null);
 const [preview,setPreview]=useState<any>(null);
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 useEffect(()=>{apiFetch(API+"/api/v1/trading/forex/status").then(async r=>{if(r.ok)setStatus(await r.json())}).catch(()=>setError("Forex service unavailable"))},[]);
 async function loadQuote(){setBusy(true);setError("");setQuote(null);setPreview(null);try{
  const r=await apiFetch(API+"/api/v1/trading/forex/quote/"+symbol);
  const d=await r.json();if(!r.ok)throw Error(d.detail||"Quote unavailable");setQuote(d);
 }catch(e){setError(e instanceof Error?e.message:"Quote unavailable")}finally{setBusy(false)}}
 async function makePreview(){setBusy(true);setError("");setPreview(null);try{
  const r=await apiFetch(API+"/api/v1/trading/forex/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol,side,stop_pips:20,confidence:85,risk_percent:0.5})});
  const d=await r.json();if(!r.ok)throw Error(d.detail||"Paper preview unavailable");setPreview(d);
 }catch(e){setError(e instanceof Error?e.message:"Preview unavailable")}finally{setBusy(false)}}
 return <section className="omx-auto-section" style={{marginTop:24}}>
  <h2>Forex Intelligence · MetaTrader 5 / MetaApi</h2>
  <p className="muted">Integrated with AgentForge Crypto. Forex V1 is read-only market research and paper previews; no real broker orders or autonomous Forex entries.</p>
  <p><b>Broker feed:</b> {status?.feed_configured?"Configured — validate live quotes below":"Not connected yet"} · <b>Real execution:</b> Disabled</p>
  <div className="omx-auto-grid">
   <label>Currency pair<select value={symbol} onChange={e=>{setSymbol(e.target.value);setQuote(null);setPreview(null)}}><option value="EURUSD">EUR/USD</option><option value="GBPUSD">GBP/USD</option><option value="USDJPY">USD/JPY</option></select></label>
   <label>Paper direction<select value={side} onChange={e=>setSide(e.target.value)}><option value="BUY">BUY</option><option value="SELL">SELL</option></select></label>
  </div>
  <div className="actions"><button className="secondary" disabled={busy} onClick={loadQuote}>Check MT5 quote</button><button className="secondary" disabled={busy||!status?.feed_configured} onClick={makePreview}>Preview paper trade</button></div>
  {error&&<p role="alert">{error}</p>}
  {quote&&<p>Bid: {quote.bid} · Ask: {quote.ask} · Spread: {quote.spread_pips} pips · Quote age: {quote.quote_age_seconds}s</p>}
  {preview&&<div className="omx-cycle-result"><b>Paper preview only — no order placed</b><p>{preview.side} {preview.symbol} · Entry {preview.entry} · Stop {preview.stop} · Target {preview.target} · Units {preview.units}</p><p>{preview.notice}</p></div>}
  {!status?.feed_configured&&<p className="muted">To connect: set METAAPI_TOKEN, METAAPI_ACCOUNT_ID and METAAPI_PRICE_URL_TEMPLATE as server environment secrets. MT5 desktop terminal is not installed on Render.</p>}
  <p className="muted">Safeguards: 30-second quote freshness, maximum 2-pip spread, minimum 85 confidence for previews, 0.5% default risk, $10 paper notional cap, and no leverage. Profit is never guaranteed.</p>
 </section>;
}
