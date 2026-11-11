import {useEffect,useState} from "react";
import {apiFetch,API} from "./api";
type Status={feed_configured:boolean;account_configured:boolean;execution_enabled:boolean;next_step:string};
type Account={id:string;broker?:string;server?:string;is_demo?:boolean;status?:string;hot?:boolean};
export default function OmonuxForex(){
 const [status,setStatus]=useState<Status|null>(null);
 const [accounts,setAccounts]=useState<Account[]>([]);
 const [selectedAccountId,setSelectedAccountId]=useState("");
 const [verified,setVerified]=useState(false);
 const [candles,setCandles]=useState<any>(null);
 const [research,setResearch]=useState<any>(null);
 const [preflight,setPreflight]=useState<any>(null);
 const [positions,setPositions]=useState<any>(null);
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 const [symbol,setSymbol]=useState("EURUSD");
 async function requestJson(path:string):Promise<any>{
  const response=await apiFetch(API+path,{headers:{"Accept":"application/json"}});
  const contentType=response.headers.get("content-type")||"";
  if(!contentType.toLowerCase().includes("application/json")){
   const hint=response.status===401||response.status===403?" Sign in again and retry.":response.status>=500?" The deployed backend or reverse proxy may be unavailable.":" Verify the deployed API route and reverse-proxy configuration.";
   throw Error("Forex API returned a non-JSON response (HTTP "+response.status+", "+(contentType||"unknown content type")+")."+hint);
  }
  let data:any;
  try{data=await response.json()}catch{throw Error("Forex API returned invalid JSON (HTTP "+response.status+").")}
  if(!response.ok)throw Error(typeof data?.detail==="string"?data.detail:"Forex API request failed (HTTP "+response.status+").");
  return data;
 }
 useEffect(()=>{requestJson("/api/v1/trading/forex/status").then(setStatus).catch(e=>setError(e instanceof Error?e.message:"Forex service unavailable"))},[]);
 async function get(path:string,apply:(value:any)=>void){
  setBusy(true);setError("");
  try{apply(await requestJson(path))}
  catch(e){setError(e instanceof Error?e.message:"Connection failed")}
  finally{setBusy(false)}
 }
 return <section className="omx-auto-section" style={{marginTop:24}}>
  <h2>Forex Intelligence · TickerAll + MT5</h2>
  <p className="muted">AgentForge Connect API · Read-only Forex integration. Your API key stays in Render, never in this browser or the GitHub repository.</p>
  <p><b>API key:</b> {status?.feed_configured?"Configured in Render":"Not configured"} · <b>MT5 account ID:</b> {status?.account_configured?"Configured":"Not configured"} · <b>Broker order execution:</b> Disabled</p>
  <div className="actions"><button className="secondary" disabled={busy||!status?.feed_configured} onClick={()=>get("/api/v1/trading/forex/accounts",d=>{const list=Array.isArray(d.accounts)?d.accounts:[];setAccounts(list);setSelectedAccountId(list.find((a:Account)=>a.is_demo)?.id||"");setVerified(false)})}>Check TickerAll connection</button><button className="secondary" disabled={busy||(!selectedAccountId&&!status?.account_configured)} onClick={()=>get("/api/v1/trading/forex/account"+(selectedAccountId?"?account_id="+encodeURIComponent(selectedAccountId):""),d=>{setVerified(true);setError("");setAccounts(prev=>prev.map(a=>a.id===selectedAccountId?{...a,broker:d.broker,server:d.server,is_demo:d.is_demo,status:d.status}:a))})}>Verify demo account</button></div>
  <div className="actions"><button className="secondary" disabled={busy||!verified||!status?.account_configured} onClick={()=>{setPreflight(null);get("/api/v1/trading/forex/preflight/session",setPreflight)}}>Run MT5 session preflight (read only)</button></div>
  {preflight&&<p role="status"><b>MT5 session ready:</b> {preflight.session_ready?"Yes":"No"} · <b>Demo verified:</b> {preflight.verified_demo?"Yes":"No"} · <b>Open positions:</b> {preflight.open_positions} · <b>Trading permission:</b> Not verified · <b>Stop loss:</b> Not verified · <b>Execution:</b> Disabled. {preflight.next_step}</p>}
  <div className="actions"><button className="secondary" disabled={busy||!verified||!status?.account_configured} onClick={()=>{setPositions(null);get("/api/v1/trading/forex/positions",setPositions)}}>View open MT5 positions (read only)</button></div>
  {positions&&<div className="taskrow"><span><b>Open MT5 demo positions: {positions.count}</b><small>Read-only broker snapshot. Stop status distinguishes set, explicitly unset, and unknown broker values. This does not authorize execution.</small><small>Stops: {positions.stop_status_counts?.set??0} set · {positions.stop_status_counts?.not_set??0} not set · {positions.stop_status_counts?.unknown??0} unknown</small>
   {positions.count===0?<small>No open positions reported at the time of this check.</small>:<div style={{overflowX:"auto"}}><table><thead><tr><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>Stop loss</th><th>Take profit</th><th>P/L</th><th>Magic</th><th>Ticket</th></tr></thead><tbody>{positions.positions.map((p:any,i:number)=><tr key={p.ticket||i}><td>{p.symbol||"Unknown"}</td><td>{p.side||"Unknown"}</td><td>{p.volume??"Unknown"}</td><td>{p.open_price??"Unknown"}</td><td>{p.stop_loss_status==="set"?p.stop_loss:p.stop_loss_status==="not_set"?"Not set":"Unknown — verify in MT5"}</td><td>{p.take_profit_status==="set"?p.take_profit:p.take_profit_status==="not_set"?"Not set":"Unknown"}</td><td>{p.profit??"Unknown"}</td><td>{p.magic??"Unknown"}</td><td>{p.ticket||"Unknown"}</td></tr>)}</tbody></table></div>}
  </span></div>}
  {accounts.map(a=><div className="taskrow" key={a.id}><span><b>{a.broker||"MT5"} · {a.server||"Broker"}</b><small>Account ID: {a.id} · {a.is_demo?"DEMO":"Not verified as demo"} · {a.status||"Unknown"} · {a.hot===false?"Session cold":"Session state not checked"}</small></span></div>)}
  {accounts.filter(a=>a.is_demo).length>1&&<label>Demo account <select value={selectedAccountId} onChange={e=>{setSelectedAccountId(e.target.value);setVerified(false)}}>{accounts.filter(a=>a.is_demo).map(a=><option key={a.id} value={a.id}>{a.server||"MT5"} · {a.id}</option>)}</select></label>}
  {verified&&<p role="status">Demo account verified successfully. Broker execution remains disabled.</p>}
  <div className="omx-auto-grid"><label>Forex pair<select value={symbol} onChange={e=>{setSymbol(e.target.value);setCandles(null);setResearch(null)}}><option value="EURUSD">EUR/USD</option><option value="GBPUSD">GBP/USD</option><option value="USDJPY">USD/JPY</option></select></label></div>
  <div className="actions"><button className="secondary" disabled={busy||!status?.account_configured} onClick={()=>get("/api/v1/trading/forex/candles/"+symbol+"?timeframe=M30&hours=72",setCandles)}>Test 30-minute candles</button></div>
  <div className="actions"><button className="secondary" disabled={busy||!status?.account_configured} onClick={()=>get("/api/v1/trading/forex/research/"+symbol+"?timeframe=M30&hours=168",setResearch)}>Run 12-agent Forex research</button></div>
  {research&&<div className="taskrow"><span><b>Forex research · {research.symbol} · {research.timeframe}</b><small>Direction: {research.signal?.side||"HOLD"} · Council: {research.council?.decision||research.decision||"NO_TRADE"} · Votes: {research.council?.supporting_votes??0}/12 · Completed agents: {research.council?.completed_agents??0}/12 · No broker order placed</small>{research.risk_warning&&<small role="status"><b>Loss-risk warning: {research.risk_warning.risk_level}</b> · Probability of loss: unknown · {research.risk_warning.reasons.join("; ")} · Research only, no trade authorized</small>}{Array.isArray(research.council?.agents)&&research.council.agents.map((a:any)=><small key={a.id}>{a.name}: {a.stance} · {a.status} · {a.reason}</small>)}</span></div>}
  {candles&&<p role="status">TickerAll closed candles validated: {candles.count} for {candles.symbol}. Research only; no orders placed.</p>}
  {error&&<p role="alert">{error}</p>}
  <div className="guard">Render → AgentForge web service → Environment: add TICKERALL_API_KEY (secret). Click Check TickerAll connection, then Verify demo account. Copy the returned account ID exactly into TICKERALL_ACCOUNT_ID in Render, then redeploy. Never paste secrets into chat. Only demo accounts and read-only requests are supported. No live trading.</div>
 </section>;
}
