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
 const [statusLoading,setStatusLoading]=useState(true);
 const [symbol,setSymbol]=useState("EURUSD");
 const [paperSide,setPaperSide]=useState<"BUY"|"SELL">("BUY");
 const [paperEntry,setPaperEntry]=useState("");
 const [paperStop,setPaperStop]=useState("");
 const [paperTarget,setPaperTarget]=useState("");
 const [paperRisk,setPaperRisk]=useState("0.5");
 const [paperTrades,setPaperTrades]=useState<Array<{id:number;symbol:string;side:string;entry:number;stop:number;target:number;risk:number;status:string;exit?:number;pnl?:number}>>([]);
 const [paperQuote,setPaperQuote]=useState("");
 const [paperMessage,setPaperMessage]=useState("");
 const [tab,setTab]=useState<"overview"|"research"|"paper">("overview");
 const [paperConfirm,setPaperConfirm]=useState(false);
 const entry=Number(paperEntry),stop=Number(paperStop),target=Number(paperTarget),risk=Number(paperRisk),quote=Number(paperQuote);
 const validPlan=paperEntry.trim()!==""&&paperStop.trim()!==""&&paperTarget.trim()!==""&&Number.isFinite(entry)&&Number.isFinite(stop)&&Number.isFinite(target)&&entry>0&&stop>0&&target>0&&risk>0&&risk<=1&&(paperSide==="BUY"?stop<entry&&target>entry:stop>entry&&target<entry);
 const riskReward=validPlan?Math.abs(target-entry)/Math.abs(entry-stop):0;
 const riskUsd=100*risk/100;
 const pipSize=symbol==="USDJPY"?0.01:0.0001;
 const pipValue=validPlan?Math.abs(entry-stop)/pipSize:0;
 function loadPaperExample(){
  const base=symbol==="USDJPY"?150: symbol==="GBPUSD"?1.3:1.115;
  const pip=symbol==="USDJPY"?0.01:0.0001;
  const entryPrice=base, stopPrice=paperSide==="BUY"?base-20*pip:base+20*pip;
  const targetPrice=paperSide==="BUY"?base+40*pip:base-40*pip;
  const digits=symbol==="USDJPY"?3:5;
  setPaperEntry(entryPrice.toFixed(digits));setPaperStop(stopPrice.toFixed(digits));setPaperTarget(targetPrice.toFixed(digits));
  setPaperQuote(targetPrice.toFixed(digits));setPaperRisk("0.5");setPaperConfirm(false);
  setPaperMessage("Example loaded. These are fictional test prices, not current MT5 quotes. Tick the confirmation box, record the simulated entry, then click Evaluate simulated exits.");
 }
 function testExampleExit(kind:"STOP"|"TARGET"){
  const open=paperTrades.find(t=>t.status==="OPEN"&&t.symbol===symbol);
  if(!open){setPaperMessage("First record a simulated entry. Click Load example, tick the confirmation box, then Record simulated entry.");return}
  const exit=kind==="STOP"?open.stop:open.target;
  setPaperQuote(String(exit));
  setPaperTrades(prev=>prev.map(t=>t.id===open.id?{...t,status:kind==="STOP"?"STOP TRIGGERED":"TARGET TRIGGERED",exit,pnl:kind==="STOP"?-t.risk:t.risk*Math.abs(t.target-t.entry)/Math.abs(t.entry-t.stop)}:t));
  setPaperMessage(kind==="STOP"?"Test passed: simulated stop loss triggered. No broker order was sent.":"Test passed: simulated take profit triggered. No broker order was sent.");
 }
 function createPaperTrade(){
  if(!validPlan||riskReward<1.5||!paperConfirm){setPaperMessage("A valid stop, target, minimum 1.5 reward/risk, and explicit confirmation are required.");return}
  setPaperTrades(prev=>[{id:Date.now(),symbol,side:paperSide,entry,stop,target,risk:riskUsd,status:"OPEN"},...prev]);
  setPaperMessage("Simulated entry recorded locally. No MT5 or broker order was sent. Enter a new observed price to test exits.");
  setPaperConfirm(false);
 }
 function evaluatePaper(){
  if(!paperQuote.trim()||!Number.isFinite(quote)||quote<=0){setPaperMessage("Enter a valid observed price to evaluate the simulated positions.");return}
  let closed=0;
  setPaperTrades(prev=>prev.map(t=>{
   if(t.status!=="OPEN"||t.symbol!==symbol)return t;
   const stopHit=t.side==="BUY"?quote<=t.stop:quote>=t.stop;
   const targetHit=t.side==="BUY"?quote>=t.target:quote<=t.target;
   if(!stopHit&&!targetHit)return t;
   closed++;
   const pnl=t.risk*(t.side==="BUY"?(quote-t.entry)/(t.entry-t.stop):(t.entry-quote)/(t.stop-t.entry));
   return {...t,status:stopHit?"STOP TRIGGERED":"TARGET TRIGGERED",exit:quote,pnl};
  }));
  setPaperMessage(closed?closed+" simulated position(s) closed at the manually entered observed price. Gaps and slippage are reflected by that price.":"No simulated stop or target crossed at this observed price.");
 }
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
 async function refreshStatus(){
  setStatusLoading(true);
  try{
   const data=await requestJson("/api/v1/trading/forex/status");
   setStatus(data);setError("");
  }catch(e){setStatus(null);setError(e instanceof Error?e.message:"Forex service unavailable")}
  finally{setStatusLoading(false)}
 }
 useEffect(()=>{void refreshStatus()},[]);
 async function get(path:string,apply:(value:any)=>void){
  setBusy(true);setError("");
  try{apply(await requestJson(path))}
  catch(e){setError(e instanceof Error?e.message:"Connection failed")}
  finally{setBusy(false)}
 }
 return <section className="omx-auto-section" style={{marginTop:24,display:"grid",gap:16}}>
  <div style={{borderRadius:20,padding:"26px 24px",background:"linear-gradient(120deg,#0b1732,#123b55 65%,#0c5752)",color:"#fff"}}>
   <div style={{fontSize:12,letterSpacing:2,fontWeight:700,opacity:.8}}>OMONUX / FOREX INTELLIGENCE</div>
   <h2 style={{color:"#fff",fontSize:"clamp(24px,3vw,36px)",margin:"12px 0 6px"}}>Your Forex command center</h2>
   <p style={{color:"#d6e9ef",maxWidth:680}}>Explore real broker data, review AI research and practice disciplined entries with simulated stops and targets. Live broker execution stays off.</p>
   <div style={{display:"flex",flexWrap:"wrap",gap:10,marginTop:18}}>
    <span style={{padding:"8px 12px",borderRadius:24,background:"#ffffff20"}}>● {status?.feed_configured?"TickerAll connected":"Connection not verified"}</span>
    <span style={{padding:"8px 12px",borderRadius:24,background:"#ffffff20"}}>MT5 · Demo only</span>
    <span style={{padding:"8px 12px",borderRadius:24,background:"#ffffff20"}}>Broker orders disabled</span>
   </div>
  </div>
  <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
   {(["overview","research","paper"] as const).map(t=><button key={t} className={tab===t?"":"secondary"} onClick={()=>setTab(t)}>{t==="overview"?"① Connection & positions":t==="research"?"② AI research":"③ Paper execution lab"}</button>)}
  </div>
  {tab==="overview"&&<><p className="muted">AgentForge Connect API · Read-only Forex integration. Your API key stays in Render, never in this browser or the GitHub repository.</p>
  <p><b>API key:</b> {statusLoading?"Checking…":status===null?"Unavailable — status request failed":status.feed_configured?"Configured in Render":"Not configured"} · <b>MT5 account ID:</b> {statusLoading?"Checking…":status===null?"Unavailable — status request failed":status.account_configured?"Configured":"Not configured"} · <b>Broker order execution:</b> Disabled</p>
  <div className="actions"><button className="secondary" disabled={busy||statusLoading} onClick={()=>void refreshStatus()}>Retry Forex status</button><button className="secondary" disabled={busy||!status?.feed_configured} onClick={()=>get("/api/v1/trading/forex/accounts",d=>{const list=Array.isArray(d.accounts)?d.accounts:[];setAccounts(list);setSelectedAccountId(list.find((a:Account)=>a.is_demo)?.id||"");setVerified(false)})}>Check TickerAll connection</button><button className="secondary" disabled={busy||(!selectedAccountId&&!status?.account_configured)} onClick={()=>get("/api/v1/trading/forex/account"+(selectedAccountId?"?account_id="+encodeURIComponent(selectedAccountId):""),d=>{setVerified(true);setError("");setAccounts(prev=>prev.map(a=>a.id===selectedAccountId?{...a,broker:d.broker,server:d.server,is_demo:d.is_demo,status:d.status}:a))})}>Verify demo account</button></div>
  <div className="actions"><button className="secondary" disabled={busy||!verified||!status?.account_configured} onClick={()=>{setPreflight(null);get("/api/v1/trading/forex/preflight/session",setPreflight)}}>Run MT5 session preflight (read only)</button></div>
  {positions&&<div className="taskrow" style={{borderLeft:"4px solid #e59b32"}}><span><b>MT5 demo execution readiness · BLOCKED</b><small>{positions.count} open broker positions detected · {positions.stop_status_counts?.not_set??0} explicitly without stop loss · {positions.stop_status_counts?.unknown??0} unknown stop states.</small><small>Read-only research and local paper simulation remain available. Broker demo orders are blocked until existing exposure is resolved, the session preflight passes, and TickerAll confirms broker-enforced protective stops, permissions, and order reconciliation.</small><small>Do not use a real-money account for this test. Check and manage existing positions directly in MetaTrader 5.</small></span></div>}
  {preflight&&<p role="status"><b>MT5 session ready:</b> {preflight.session_ready?"Yes":"No"} · <b>Demo verified:</b> {preflight.verified_demo?"Yes":"No"} · <b>Open positions:</b> {preflight.open_positions} · <b>Trading permission:</b> Not verified · <b>Stop loss:</b> Not verified · <b>Execution:</b> Disabled. {preflight.next_step}</p>}
  <div className="actions"><button className="secondary" disabled={busy||!verified||!status?.account_configured} onClick={()=>{setPositions(null);get("/api/v1/trading/forex/positions",setPositions)}}>View open MT5 positions (read only)</button></div>
  {positions&&<div className="taskrow"><span><b>Open MT5 demo positions: {positions.count}</b><small>Read-only broker snapshot. Stop status distinguishes set, explicitly unset, and unknown broker values. This does not authorize execution.</small><small>Stops: {positions.stop_status_counts?.set??0} set · {positions.stop_status_counts?.not_set??0} not set · {positions.stop_status_counts?.unknown??0} unknown</small>
   {positions.count===0?<small>No open positions reported at the time of this check.</small>:<div style={{overflowX:"auto"}}><table><thead><tr><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>Stop loss</th><th>Take profit</th><th>P/L</th><th>Magic</th><th>Ticket</th></tr></thead><tbody>{positions.positions.map((p:any,i:number)=><tr key={p.ticket||i}><td>{p.symbol||"Unknown"}</td><td>{p.side||"Unknown"}</td><td>{p.volume??"Unknown"}</td><td>{p.open_price??"Unknown"}</td><td>{p.stop_loss_status==="set"?p.stop_loss:p.stop_loss_status==="not_set"?"Not set":"Unknown — verify in MT5"}</td><td>{p.take_profit_status==="set"?p.take_profit:p.take_profit_status==="not_set"?"Not set":"Unknown"}</td><td>{p.profit??"Unknown"}</td><td>{p.magic??"Unknown"}</td><td>{p.ticket||"Unknown"}</td></tr>)}</tbody></table></div>}
  </span></div>}
  {accounts.map(a=><div className="taskrow" key={a.id}><span><b>{a.broker||"MT5"} · {a.server||"Broker"}</b><small>Account ID: {a.id} · {a.is_demo?"DEMO":"Not verified as demo"} · {a.status||"Unknown"} · {a.hot===true?"Session reported hot":a.hot===false?"Session reported cold":"Session state not checked"}</small></span></div>)}
  {accounts.filter(a=>a.is_demo).length>1&&<label>Demo account <select value={selectedAccountId} onChange={e=>{setSelectedAccountId(e.target.value);setVerified(false)}}>{accounts.filter(a=>a.is_demo).map(a=><option key={a.id} value={a.id}>{a.server||"MT5"} · {a.id}</option>)}</select></label>}
  {verified&&<p role="status">Demo account verified successfully. Broker execution remains disabled.</p>}
  </>}
  {tab==="research"&&<><div className="omx-auto-grid"><label>Forex pair<select value={symbol} onChange={e=>{setSymbol(e.target.value);setCandles(null);setResearch(null)}}><option value="EURUSD">EUR/USD</option><option value="GBPUSD">GBP/USD</option><option value="USDJPY">USD/JPY</option></select></label></div>
  <div className="actions"><button className="secondary" disabled={busy||!status?.account_configured} onClick={()=>get("/api/v1/trading/forex/candles/"+symbol+"?timeframe=M30&hours=72",setCandles)}>Test 30-minute candles</button></div>
  <div className="actions"><button className="secondary" disabled={busy||!status?.account_configured} onClick={()=>get("/api/v1/trading/forex/research/"+symbol+"?timeframe=M30&hours=168",setResearch)}>Run 12-agent Forex research</button></div>
  {research&&<div className="taskrow"><span><b>Forex research · {research.symbol} · {research.timeframe}</b><small>Direction: {research.signal?.side||"HOLD"} · Council: {research.council?.decision||research.decision||"NO_TRADE"} · Votes: {research.council?.supporting_votes??0}/12 · Completed agents: {research.council?.completed_agents??0}/12 · No broker order placed</small>{research.risk_warning&&<small role="status"><b>Loss-risk warning: {research.risk_warning.risk_level}</b> · Probability of loss: unknown · {research.risk_warning.reasons.join("; ")} · Research only, no trade authorized</small>}{Array.isArray(research.council?.agents)&&research.council.agents.map((a:any)=><small key={a.id}>{a.name}: {a.stance} · {a.status} · {a.reason}</small>)}</span></div>}
  {candles&&<p role="status">TickerAll closed candles validated: {candles.count} for {candles.symbol}. Research only; no orders placed.</p>}
  </>}
  {tab==="paper"&&<div style={{display:"grid",gap:16}}>
   <div className="taskrow"><span><b>Paper execution · $100 virtual test balance</b><small>Local simulation only. Nothing is transmitted to MT5. Trade records disappear on page reload. Prices are manually supplied; this is not an automated broker stop.</small></span></div>
   <div className="taskrow"><span><b>Quick start · no calculations required</b><small>Step 1: Choose a pair and direction. Step 2: Load example prices. Step 3: Confirm and record the simulated trade. Step 4: Test a stop or target exit. Example prices are fictional.</small><button className="secondary" onClick={loadPaperExample}>Load example trade automatically</button></span></div>
   <div className="omx-auto-grid">
    <label>Forex pair<select value={symbol} onChange={e=>{setSymbol(e.target.value);setPaperConfirm(false)}}><option value="EURUSD">EUR/USD</option><option value="GBPUSD">GBP/USD</option><option value="USDJPY">USD/JPY</option></select></label>
    <label>Direction<select value={paperSide} onChange={e=>{setPaperSide(e.target.value as "BUY"|"SELL");setPaperConfirm(false)}}><option value="BUY">BUY · Long</option><option value="SELL">SELL · Short</option></select></label>
    <label>Reference entry price<input type="number" step="any" min="0" value={paperEntry} onChange={e=>{setPaperEntry(e.target.value);setPaperConfirm(false)}} placeholder="Enter verified quote"/></label>
    <label>Protective stop price<input type="number" step="any" min="0" value={paperStop} onChange={e=>{setPaperStop(e.target.value);setPaperConfirm(false)}} placeholder="Required"/></label>
    <label>Take-profit price<input type="number" step="any" min="0" value={paperTarget} onChange={e=>{setPaperTarget(e.target.value);setPaperConfirm(false)}} placeholder="Required"/></label>
    <label>Risk budget (% of $100)<input type="number" min="0.1" max="1" step="0.1" value={paperRisk} onChange={e=>{setPaperRisk(e.target.value);setPaperConfirm(false)}}/></label>
   </div>
   <div className="taskrow"><span><b>Risk preview</b><small>Maximum planned loss at stop: {validPlan?"$"+riskUsd.toFixed(2):"—"} · Distance: {validPlan?pipValue.toFixed(1)+" pips":"—"} · Reward/risk: {validPlan?riskReward.toFixed(2)+":1":"—"}</small><small>{!validPlan?"Enter prices with the stop on the loss side and target on the profit side.":riskReward<1.5?"Blocked: minimum reward/risk is 1.5:1.":"Eligible for a local simulated entry only; no live market validation."}</small></span></div>
   <label style={{display:"flex",alignItems:"center",gap:8}}><input type="checkbox" checked={paperConfirm} onChange={e=>setPaperConfirm(e.target.checked)}/> I understand this is a local simulation, not an MT5 order or automatic stop</label>
   <div className="actions"><button disabled={!validPlan||riskReward<1.5||!paperConfirm} onClick={createPaperTrade}>Record simulated {paperSide} entry</button></div>
   <div className="taskrow"><span><b>Test stop-loss / take-profit exit</b><small>Enter an independently observed price. Stops and targets trigger only when you click Evaluate; there is no continuous broker monitoring.</small>
    <label>Observed price<input type="number" step="any" min="0" value={paperQuote} onChange={e=>setPaperQuote(e.target.value)} placeholder="Latest observed price"/></label>
    <button className="secondary" onClick={evaluatePaper}>Evaluate simulated exits</button>
    <div className="actions"><button className="secondary" onClick={()=>testExampleExit("STOP")}>Test stop loss</button><button className="secondary" onClick={()=>testExampleExit("TARGET")}>Test take profit</button></div></span></div>
   {paperMessage&&<p role="status">{paperMessage}</p>}
   <div className="taskrow"><span><b>Simulated trade journal · {paperTrades.length} entries</b>{paperTrades.length===0?<small>No simulated trades recorded yet.</small>:<div style={{overflowX:"auto"}}><table><thead><tr><th>Pair</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>Status</th><th>Simulated P/L</th></tr></thead><tbody>{paperTrades.map(t=><tr key={t.id}><td>{t.symbol}</td><td>{t.side}</td><td>{t.entry}</td><td>{t.stop}</td><td>{t.target}</td><td>{t.status}</td><td>{t.pnl===undefined?"—":"$"+t.pnl.toFixed(2)}</td></tr>)}</tbody></table></div>}</span></div>
  </div>}
  {error&&<p role="alert">{error}</p>}
  {tab==="overview"&&<div className="guard">Render → AgentForge web service → Environment: add TICKERALL_API_KEY (secret). Click Check TickerAll connection, then Verify demo account. Copy the returned account ID exactly into TICKERALL_ACCOUNT_ID in Render, then redeploy. Never paste secrets into chat. Only demo accounts and read-only requests are supported. No live trading.</div>}
 </section>;
}
