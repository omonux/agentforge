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
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 const [symbol,setSymbol]=useState("EURUSD");
 useEffect(()=>{apiFetch(API+"/api/v1/trading/forex/status").then(async r=>{if(r.ok)setStatus(await r.json())}).catch(()=>setError("Forex service unavailable"))},[]);
 async function get(path:string,apply:(value:any)=>void){
  setBusy(true);setError("");try{const r=await apiFetch(API+path);const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"TickerAll request failed");apply(data)}
  catch(e){setError(e instanceof Error?e.message:"Connection failed")}finally{setBusy(false)}
 }
 return <section className="omx-auto-section" style={{marginTop:24}}>
  <h2>Forex Intelligence · TickerAll + MT5</h2>
  <p className="muted">AgentForge Connect API · Read-only Forex integration. Your API key stays in Render, never in this browser or the GitHub repository.</p>
  <p><b>API key:</b> {status?.feed_configured?"Configured in Render":"Not configured"} · <b>MT5 account ID:</b> {status?.account_configured?"Configured":"Not configured"} · <b>Broker order execution:</b> Disabled</p>
  <div className="actions"><button className="secondary" disabled={busy||!status?.feed_configured} onClick={()=>get("/api/v1/trading/forex/accounts",d=>{const list=Array.isArray(d.accounts)?d.accounts:[];setAccounts(list);setSelectedAccountId(list.find((a:Account)=>a.is_demo)?.id||"");setVerified(false)})}>Check TickerAll connection</button><button className="secondary" disabled={busy||(!selectedAccountId&&!status?.account_configured)} onClick={()=>get("/api/v1/trading/forex/account"+(selectedAccountId?"?account_id="+encodeURIComponent(selectedAccountId):""),d=>{setVerified(true);setError("");setAccounts(prev=>prev.map(a=>a.id===selectedAccountId?{...a,broker:d.broker,server:d.server,is_demo:d.is_demo,status:d.status}:a))})}>Verify demo account</button></div>
  {accounts.map(a=><div className="taskrow" key={a.id}><span><b>{a.broker||"MT5"} · {a.server||"Broker"}</b><small>Account ID: {a.id} · {a.is_demo?"DEMO":"Not verified as demo"} · {a.status||"Unknown"} · {a.hot===false?"Session cold":"Session state not checked"}</small></span></div>)}
  {accounts.filter(a=>a.is_demo).length>1&&<label>Demo account <select value={selectedAccountId} onChange={e=>{setSelectedAccountId(e.target.value);setVerified(false)}}>{accounts.filter(a=>a.is_demo).map(a=><option key={a.id} value={a.id}>{a.server||"MT5"} · {a.id}</option>)}</select></label>}
  {verified&&<p role="status">Demo account verified successfully. Broker execution remains disabled.</p>}
  <div className="omx-auto-grid"><label>Forex pair<select value={symbol} onChange={e=>{setSymbol(e.target.value);setCandles(null)}}><option value="EURUSD">EUR/USD</option><option value="GBPUSD">GBP/USD</option><option value="USDJPY">USD/JPY</option></select></label></div>
  <div className="actions"><button className="secondary" disabled={busy||!status?.account_configured} onClick={()=>get("/api/v1/trading/forex/candles/"+symbol+"?timeframe=M30&hours=72",setCandles)}>Test 30-minute candles</button></div>
  {candles&&<p role="status">TickerAll closed candles validated: {candles.count} for {candles.symbol}. Research only; no orders placed.</p>}
  {error&&<p role="alert">{error}</p>}
  <div className="guard">Render → AgentForge web service → Environment: add TICKERALL_API_KEY (secret). Click Check TickerAll connection, then Verify demo account. Copy the returned account ID exactly into TICKERALL_ACCOUNT_ID in Render, then redeploy. Never paste secrets into chat. Only demo accounts and read-only requests are supported. No live trading.</div>
 </section>;
}
