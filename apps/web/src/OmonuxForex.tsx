import {useEffect,useState} from "react";
import {apiFetch,API} from "./api";
type Status={feed_configured:boolean;account_configured:boolean;execution_enabled:boolean;next_step:string};
type Account={id:string;broker?:string;server?:string;is_demo?:boolean;status?:string;hot?:boolean};
export default function OmonuxForex(){
 const [status,setStatus]=useState<Status|null>(null);
 const [accounts,setAccounts]=useState<Account[]>([]);
 const [accountSummary,setAccountSummary]=useState<any>(null);
 const [accountCheckedAt,setAccountCheckedAt]=useState("");
 const [accountHistory,setAccountHistory]=useState<Array<{time:string;equity:number;balance:number}>>([]);
 const [autoRefresh,setAutoRefresh]=useState(true);
 const [accountPollError,setAccountPollError]=useState("");
 const [selectedAccountId,setSelectedAccountId]=useState("");
 const [verified,setVerified]=useState(false);
 const [candles,setCandles]=useState<any>(null);
 const [research,setResearch]=useState<any>(null);
 const [macro,setMacro]=useState<any>(null);
 const [macroLoading,setMacroLoading]=useState(false);
 const [macroError,setMacroError]=useState("");
 const [preflight,setPreflight]=useState<any>(null);
 const [exitMonitor,setExitMonitor]=useState<any>(null);
 const [autoReadiness,setAutoReadiness]=useState<any>(null);
 const [exitTarget,setExitTarget]=useState("100");
 const [exitRetrace,setExitRetrace]=useState("30");
 const [positions,setPositions]=useState<any>(null);
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 const [statusLoading,setStatusLoading]=useState(true);
 const [symbol,setSymbol]=useState("EURUSD");
 const [protectTicket,setProtectTicket]=useState("");
 const [protectStop,setProtectStop]=useState("");
 const [protectConfirm,setProtectConfirm]=useState(false);
 const [protectMessage,setProtectMessage]=useState("");
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
 async function protectDemoStop(){
  if(!protectTicket||!Number.isFinite(Number(protectStop))||Number(protectStop)<=0||!protectConfirm){setProtectMessage("Select an unprotected position, enter a valid stop price and confirm.");return}
  setBusy(true);setProtectMessage("");setError("");
  try{
   const response=await apiFetch(API+"/api/v1/trading/forex/positions/protect",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({ticket:protectTicket,stop_loss:Number(protectStop),confirmation:true})});
   const result=await response.json();
   if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Broker protection request failed");
   setProtectMessage(result.confirmed?"Broker confirmed stop loss for ticket "+protectTicket+".":"Not confirmed; check MT5.");
   setProtectConfirm(false);setProtectStop("");setProtectTicket("");
   setPositions(await requestJson("/api/v1/trading/forex/positions"));
  }catch(e){setProtectMessage(e instanceof Error?e.message:"Stop update failed; inspect MT5 before retrying")}
  finally{setBusy(false)}
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
 async function refreshAccountSummary(manual=false){
  if(manual)setBusy(true);
  try{
   const data=await requestJson("/api/v1/trading/forex/account");
   const a=data?.account;
   if(a&&a.balance!=null&&a.equity!=null&&Number.isFinite(Number(a.balance))&&Number.isFinite(Number(a.equity))){
    const point={time:new Date().toLocaleTimeString(),balance:Number(a.balance),equity:Number(a.equity)};
    setAccountSummary(data);setAccountCheckedAt(point.time);setAccountPollError("");
    setAccountHistory(prev=>[...prev.slice(-119),point]);
   }else throw Error("Broker returned incomplete balance or equity");
  }catch(e){setAccountPollError(e instanceof Error?e.message:"Unable to refresh broker figures")}
  finally{if(manual)setBusy(false)}
 }
 useEffect(()=>{
  if(!status?.account_configured||!autoRefresh)return;
  void refreshAccountSummary();
  const id=window.setInterval(()=>{if(!document.hidden)void refreshAccountSummary()},30000);
  return ()=>window.clearInterval(id);
 },[status?.account_configured,autoRefresh]);
 async function loadMacro(){
  setMacroLoading(true);setMacroError("");
  try{setMacro(await requestJson("/api/v1/trading/forex/macro-intelligence"))}
  catch(e){setMacroError(e instanceof Error?e.message:"Macroeconomic feed unavailable")}
  finally{setMacroLoading(false)}
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
 return <section className="omx-auto-section forex-premium" style={{marginTop:24,display:"grid",gap:16}}>

  <style>{".forex-premium .fx-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}.forex-premium .fx-card{padding:22px;border-radius:20px;background:linear-gradient(135deg,#1d305b,#111b38);border:1px solid #40557b;color:#fff;box-shadow:0 12px 28px #0002}.forex-premium .fx-card strong{display:block;font-size:30px;margin:8px 0;color:#fff}.forex-premium .fx-card small{color:#c0d4ee}.forex-premium .fx-operations{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:13px}.forex-premium .fx-operation{padding:20px;border-radius:18px;background:linear-gradient(135deg,#233a6b,#172746);border:1px solid #47658d;color:#d6e9ff}.forex-premium .fx-operation b{display:block;color:#fff;font-size:17px;margin:10px 0}.forex-premium .fx-operation p{font-size:13px;line-height:1.6}.forex-premium .fx-tabs{display:flex;flex-wrap:wrap;gap:10px;padding:12px;background:#101d38;border-radius:20px;border:1px solid #3b5276}.forex-premium .fx-tabs button{flex:1 1 190px;padding:16px;border-radius:13px;font-weight:800}.forex-premium .fx-tabs button.fx-selected{background:linear-gradient(100deg,#7c3aed,#2563eb,#0891b2);color:white;border-color:transparent}.forex-premium .taskrow{background:linear-gradient(135deg,#1b2d53,#13213d);border:1px solid #3d5277;border-radius:18px;padding:18px}.forex-premium .taskrow small{display:block;line-height:1.6;margin-top:7px}.forex-premium input,.forex-premium select{border-radius:10px;padding:10px}.forex-premium button{transition:transform .15s}.forex-premium button:hover:not(:disabled){transform:translateY(-2px)}.forex-premium table{min-width:620px;width:100%;border-collapse:collapse}.forex-premium th{background:#233c6b;padding:12px}.forex-premium td{padding:11px;border-bottom:1px solid #364c6f}"}</style>
  <div style={{padding:"clamp(24px,4vw,48px)",borderRadius:25,background:"radial-gradient(circle at 85% 15%,#7c3aed77,transparent 45%),radial-gradient(circle at 5% 90%,#06b6d455,transparent 50%),linear-gradient(120deg,#101936,#1a3559)",color:"white",border:"1px solid #4d5b89"}}>
   <div style={{fontSize:12,letterSpacing:2.5,fontWeight:800,color:"#9de9ff"}}>◆ OMONUX · FOREX OPERATIONS CENTER</div>
   <h2 style={{fontSize:"clamp(30px,5vw,54px)",lineHeight:1.1,color:"white",margin:"18px 0",fontWeight:900}}>Trade intelligence.<br/><span style={{color:"#9de9ff"}}>Beautifully organized.</span></h2>
   <p style={{fontSize:16,color:"#d2e5fa",maxWidth:720,lineHeight:1.7}}>Your premium workspace for MT5 demo positions, risk protection, 12-agent research and paper execution. Every operation has its own room.</p>
   <div style={{display:"flex",flexWrap:"wrap",gap:10,marginTop:22}}>
    <span style={{background:"#115e59",borderRadius:25,padding:"10px 16px",fontWeight:700}}>● TickerAll {status?.feed_configured?"connected":"not verified"}</span>
    <span style={{background:"#2b4582",borderRadius:25,padding:"10px 16px",fontWeight:700}}>◈ MT5 Demo</span>
    <span style={{background:"#7f334b",borderRadius:25,padding:"10px 16px",fontWeight:700}}>◆ New broker orders locked</span>
   </div>
  </div>
  <div style={{padding:24,borderRadius:22,background:"linear-gradient(115deg,#113c3c,#162850 55%,#37235e)",border:"1px solid #467e91",color:"white"}}>
   <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap"}}><div><div style={{letterSpacing:2,fontSize:12,color:"#9de9ff",fontWeight:800}}>MT5 DEMO · ACCOUNT PERFORMANCE</div><h3 style={{color:"white",fontSize:26,margin:"8px 0"}}>Is your $100,000 growing?</h3><p style={{color:"#c7d9f1",margin:0}}>Balance is closed-trade money. Equity includes open positions. Floating P/L changes as prices move.</p></div><button disabled={busy||!status?.account_configured} onClick={()=>void refreshAccountSummary(true)}>↻ Refresh broker figures</button></div>
   <div style={{display:"flex",flexWrap:"wrap",alignItems:"center",gap:14,marginTop:16,color:"#cfe5ff"}}>
    <label style={{display:"flex",gap:8,alignItems:"center",cursor:"pointer"}}><input type="checkbox" checked={autoRefresh} onChange={e=>setAutoRefresh(e.target.checked)}/> Auto-refresh every 30 seconds</label>
    <span style={{fontSize:12}}>Last successful update: {accountCheckedAt||"Waiting for first broker snapshot"}</span>
    {accountPollError&&<span role="alert" style={{color:"#ffb4b4",fontSize:12}}>Refresh issue: {accountPollError} · Showing last successful values</span>}
   </div>
   {accountHistory.length>0&&<div style={{marginTop:22,padding:18,borderRadius:18,background:"#0d1d36",border:"1px solid #3c5c80"}}>
    <div style={{display:"flex",justifyContent:"space-between",flexWrap:"wrap",gap:8,marginBottom:12}}><b style={{color:"white"}}>Equity movement · live session</b><span style={{fontSize:12,color:"#b7d6f5"}}>{accountHistory.length} broker snapshots · last 120 · resets on reload</span></div>
    {(()=>{const values=accountHistory.map(p=>p.equity);const min=Math.min(...values,100000),max=Math.max(...values,100000);const range=Math.max(max-min,1);const x=(i:number)=>18+(i/Math.max(1,values.length-1))*764;const y=(v:number)=>170-((v-min)/range)*145;const points=values.map((v,i)=>x(i)+","+y(v)).join(" ");return <svg viewBox="0 0 800 195" role="img" aria-label="MT5 demo equity over the current browser session" style={{width:"100%",height:"auto",maxHeight:260}}><line x1="18" y1={y(100000)} x2="782" y2={y(100000)} stroke="#e2b36c" strokeDasharray="7 5" opacity=".85"/><text x="22" y={Math.max(13,y(100000)-5)} fill="#ffd99c" fontSize="12">$100k reference</text><polyline fill="none" stroke={values[values.length-1]>=values[0]?"#34d399":"#fb7185"} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" points={points}/>{values.map((v,i)=><circle key={i} cx={x(i)} cy={y(v)} r={i===values.length-1?5:2} fill="#9de9ff"/>)}<text x="18" y="190" fill="#b6cce7" fontSize="12">{min.toLocaleString("en-US",{maximumFractionDigits:2})} USD min</text><text x="780" y="190" textAnchor="end" fill="#b6cce7" fontSize="12">{max.toLocaleString("en-US",{maximumFractionDigits:2})} USD max</text></svg>})()}
    <p style={{fontSize:12,color:"#b8cce5",margin:"8px 0 0"}}>This is an on-screen history of broker snapshots while this page stays open. It is not a permanent trading-performance record or a guaranteed continuous market feed.</p>
   </div>}
   {accountSummary?.account?(()=>{
    const a=accountSummary.account;
    const balance=Number(a.balance),equity=Number(a.equity);
    const valid=Number.isFinite(balance)&&Number.isFinite(equity)&&a.balance!=null&&a.equity!=null;
    const floating=equity-balance, baseline=100000;
    const money=(v:number)=>v.toLocaleString("en-US",{style:"currency",currency:"USD"});
    return <><div className="fx-cards" style={{marginTop:22}}>
      <div className="fx-card" style={{borderTop:"4px solid #06b6d4"}}><small>ACCOUNT BALANCE</small><strong>{Number.isFinite(balance)&&a.balance!=null?money(balance):"—"}</strong><small>Realized balance · MT5 demo</small></div>
      <div className="fx-card" style={{borderTop:"4px solid #8b5cf6"}}><small>CURRENT EQUITY</small><strong>{Number.isFinite(equity)&&a.equity!=null?money(equity):"—"}</strong><small>Includes unrealized P/L</small></div>
      <div className="fx-card" style={{borderTop:"4px solid "+(floating>=0?"#10b981":"#ef4444")}}><small>FLOATING PROFIT / LOSS</small><strong style={{color:floating>=0?"#86efac":"#fca5a5"}}>{valid?(floating>=0?"+":"")+money(floating):"—"}</strong><small>{valid?(floating>=0?"Open positions currently positive":"Open positions currently negative"):"Awaiting broker data"}</small></div>
      <div className="fx-card" style={{borderTop:"4px solid "+(equity>=baseline?"#10b981":"#ef4444")}}><small>EQUITY VS $100K REFERENCE</small><strong style={{color:equity>=baseline?"#86efac":"#fca5a5"}}>{valid?(equity>=baseline?"+":"")+money(equity-baseline):"—"}</strong><small>Reference only; deposits and withdrawals not adjusted</small></div>
     </div><p style={{fontSize:12,color:"#b7cce6",marginTop:14}}>Last checked: {accountCheckedAt||"—"} · Snapshot on demand, not a streaming feed. Demo funds only. Broker data may be delayed.</p></>
   })():<p style={{color:"#d2e6fa",marginTop:16}}>Click <b>Refresh broker figures</b> to see your latest balance, equity, and whether open positions are gaining or losing. This does not place trades.</p>}
  </div>
  <div className="fx-cards">
   <div className="fx-card" style={{borderTop:"4px solid #10b981"}}><small>DATA CONNECTION</small><strong>{statusLoading?"…":status?.feed_configured?"Online":"Check"}</strong><small>TickerAll integration</small></div>
   <div className="fx-card" style={{borderTop:"4px solid #8b5cf6"}}><small>OPEN MT5 POSITIONS</small><strong>{positions?.count??"—"}</strong><small>{positions?"Broker snapshot loaded":"Load broker positions"}</small></div>
   <div className="fx-card" style={{borderTop:"4px solid #f59e0b"}}><small>WITHOUT STOP LOSS</small><strong>{positions?.stop_status_counts?.not_set??"—"}</strong><small>{positions?"Needs review":"Awaiting position check"}</small></div>
   <div className="fx-card" style={{borderTop:"4px solid #06b6d4"}}><small>SIMULATED TRADES</small><strong>{paperTrades.length}</strong><small>Local session journal</small></div>
  </div>
  <div style={{padding:24,borderRadius:22,background:"linear-gradient(135deg,#152644,#1b2853)",border:"1px solid #40517d"}}>
   <div style={{color:"#93e7ff",fontWeight:800,letterSpacing:2,fontSize:12}}>EXPLORE YOUR WORKSPACE</div>
   <h3 style={{color:"white",fontSize:26,margin:"10px 0 20px"}}>Four powerful trading operations</h3>
   <div className="fx-operations">
    <div className="fx-operation"><span style={{fontSize:28}}>🔗</span><b>Broker connectivity</b><p>Check your TickerAll connection, verify your MT5 demo account and inspect broker status.</p></div>
    <div className="fx-operation"><span style={{fontSize:28}}>🛡️</span><b>Position protection</b><p>Find missing stops, review exposure and request one-at-a-time demo protection.</p></div>
    <div className="fx-operation"><span style={{fontSize:28}}>🧠</span><b>12-agent research</b><p>Analyze closed candles, market direction, council votes and research risks.</p></div>
    <div className="fx-operation"><span style={{fontSize:28}}>📊</span><b>Paper execution lab</b><p>Practice entries, stop losses, take profits and review your simulation journal.</p></div>
   </div>
  </div>
  <div className="fx-tabs">
   {(["overview","research","paper"] as const).map(t=><button key={t} className={tab===t?"fx-selected":"secondary"} onClick={()=>setTab(t)}>{t==="overview"?"◈ Connection & positions":t==="research"?"✦ AI research council":"◇ Paper execution lab"}</button>)}
  </div>
  <div style={{padding:"18px 22px",background:"linear-gradient(90deg,#2b2464,#173b60)",borderRadius:17,border:"1px solid #5a65a1"}}>
   <b style={{fontSize:21,color:"white"}}>{tab==="overview"?"Broker connection & protective stops":tab==="research"?"Multi-agent market intelligence":"Risk-controlled paper trading"}</b>
   <p style={{color:"#d1e3fa",marginBottom:0}}>{tab==="overview"?"Inspect MT5 demo exposure and broker-reported protection.":tab==="research"?"Run real candle research; no orders are placed.":"Practice with a virtual $100 balance; this does not transmit orders to MT5."}</p>
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
  {tab==="overview"&&<div style={{padding:24,borderRadius:22,background:"linear-gradient(115deg,#173c3c,#1b284a)",border:"1px solid #3e7b8d",color:"white"}}>
   <div style={{color:"#92e6ff",fontSize:12,fontWeight:800,letterSpacing:2}}>AUTONOMOUS MT5 DEMO · SAFETY READINESS</div>
   <h3 style={{fontSize:25,color:"white",margin:"10px 0"}}>Automatic trading prerequisites</h3>
   <p style={{color:"#c9def3"}}>Check which broker capabilities are actually verified before enabling an unattended trading engine. This diagnostic does not submit orders.</p>
   <button disabled={busy} onClick={()=>get("/api/v1/trading/forex/auto-trading/readiness",setAutoReadiness)}>↻ Check automatic trading readiness</button>
   {autoReadiness&&<><p style={{color:autoReadiness.ready?"#86efac":"#fbbf91",fontWeight:800}}>{autoReadiness.ready?"Ready for reviewed demo enablement":"AUTO-TRADING BLOCKED — prerequisites incomplete"}</p><div style={{display:"grid",gap:8}}>{autoReadiness.checks.map((c:any)=><div key={c.id} style={{padding:12,borderRadius:10,background:"#14243d",border:"1px solid #36546b"}}><b style={{color:c.passed?"#86efac":"#fca5a5"}}>{c.passed?"✓":"✕"} {c.label}</b><div style={{fontSize:12,color:"#c4d8ec",marginTop:4}}>{c.detail}</div></div>)}</div><p style={{color:"#fbd38d",fontSize:12}}>{autoReadiness.next_step}</p></>}
  </div>}
  {tab==="overview"&&<div style={{padding:24,borderRadius:22,background:"linear-gradient(115deg,#3a254d,#172c50)",border:"1px solid #8067b1",color:"white"}}>
   <div style={{letterSpacing:2,color:"#e2b9ff",fontSize:12,fontWeight:800}}>POSITION EXIT INTELLIGENCE · DEMO</div>
   <h3 style={{color:"white",fontSize:25,margin:"10px 0"}}>Profit targets & trailing-gain monitor</h3>
   <p style={{color:"#d7d8f2",lineHeight:1.6}}>Analyze broker-reported position profits and flag when a target is reached, profits pull back, or a position is losing. This is an advisory monitor, not an automatic close engine.</p>
   <div className="omx-auto-grid"><label>Review profit at ($)<input type="number" min="1" max="100000" value={exitTarget} onChange={e=>setExitTarget(e.target.value)}/></label><label>Flag retracement from peak ($)<input type="number" min="1" max="100000" value={exitRetrace} onChange={e=>setExitRetrace(e.target.value)}/></label></div>
   <button disabled={busy||!status?.account_configured||!(Number(exitTarget)>=1)||!(Number(exitRetrace)>=1)} onClick={()=>get("/api/v1/trading/forex/exit-monitor?profit_target_usd="+encodeURIComponent(exitTarget)+"&trailing_retrace_usd="+encodeURIComponent(exitRetrace),setExitMonitor)}>↻ Analyze open-position exits</button>
   {exitMonitor&&<><p style={{color:"#fbd38d",fontSize:12}}>{exitMonitor.warning}</p><div style={{overflowX:"auto"}}><table><thead><tr><th>Pair</th><th>Ticket</th><th>Floating P/L</th><th>Observed peak</th><th>Pullback</th><th>Assessment</th><th>Broker SL / TP</th></tr></thead><tbody>{exitMonitor.positions.map((p:any)=><tr key={p.ticket}><td>{p.symbol}</td><td>{p.ticket}</td><td style={{color:p.profit_usd>=0?"#86efac":"#fca5a5"}}>{p.profit_usd??"Unknown"}</td><td>{p.peak_profit_usd??"—"}</td><td>{p.drawdown_from_peak_usd??"—"}</td><td>{p.status.replaceAll("_"," ")}</td><td>{p.stop_loss_status} / {p.take_profit_status}</td></tr>)}</tbody></table></div><p style={{fontSize:12,color:"#b9c9e6"}}>Checked {new Date(exitMonitor.retrieved_at).toLocaleString()} · No trades were closed.</p></>}
  </div>}
  {positions&&positions.count>0&&<div className="taskrow" style={{borderLeft:"4px solid #40a6ba"}}><span><b>Protect one existing MT5 DEMO position</b><small>Uses TickerAll's documented position PATCH API. No automatic price selection; use a broker-valid stop based on your own risk limit. This changes a real DEMO broker position, not the local simulation. Requires the server flag TICKERALL_DEMO_STOP_UPDATES_ENABLED=true.</small><div className="actions"><label>Unprotected position <select value={protectTicket} onChange={e=>{setProtectTicket(e.target.value);setProtectConfirm(false)}}><option value="">Choose ticket</option>{positions.positions.filter((p:any)=>p.ticket&&p.stop_loss_status==="not_set").map((p:any)=><option key={p.ticket} value={p.ticket}>{p.symbol} {p.side} · {p.volume} lots · ticket {p.ticket}</option>)}</select></label><label>Stop-loss price <input type="number" step="any" min="0" value={protectStop} onChange={e=>{setProtectStop(e.target.value);setProtectConfirm(false)}} placeholder="Broker-valid price"/></label></div><label><input type="checkbox" checked={protectConfirm} onChange={e=>setProtectConfirm(e.target.checked)}/> I authorize changing the stop loss on this single MT5 DEMO position</label><div className="actions"><button disabled={busy||!protectTicket||!protectConfirm||!(Number(protectStop)>0)} onClick={()=>void protectDemoStop()}>Apply & verify demo stop loss</button></div>{protectMessage&&<small role="status">{protectMessage}</small>}</span></div>}
  {accounts.map(a=><div className="taskrow" key={a.id}><span><b>{a.broker||"MT5"} · {a.server||"Broker"}</b><small>Account ID: {a.id} · {a.is_demo?"DEMO":"Not verified as demo"} · {a.status||"Unknown"} · {a.hot===true?"Session reported hot":a.hot===false?"Session reported cold":"Session state not checked"}</small></span></div>)}
  {accounts.filter(a=>a.is_demo).length>1&&<label>Demo account <select value={selectedAccountId} onChange={e=>{setSelectedAccountId(e.target.value);setVerified(false)}}>{accounts.filter(a=>a.is_demo).map(a=><option key={a.id} value={a.id}>{a.server||"MT5"} · {a.id}</option>)}</select></label>}
  {verified&&<p role="status">Demo account verified successfully. Broker execution remains disabled.</p>}
  </>}
  {tab==="research"&&<div style={{padding:24,borderRadius:20,background:"linear-gradient(135deg,#173b57,#26214f)",border:"1px solid #456a95",color:"white"}}>
   <div style={{color:"#9de9ff",fontSize:12,letterSpacing:2,fontWeight:800}}>GLOBAL ECONOMIC INTELLIGENCE · PUBLIC DATA</div>
   <h3 style={{fontSize:25,color:"white",margin:"10px 0"}}>Economic fundamentals across major currencies</h3>
   <p style={{color:"#c7d9f3",lineHeight:1.6}}>Fetch published inflation, GDP growth and unemployment figures for the United States, United Kingdom, Euro Area, Japan and Switzerland. Data comes from the World Bank and may be years old; it is not breaking news or a live trade signal.</p>
   <button disabled={macroLoading} onClick={()=>void loadMacro()}>{macroLoading?"Loading World Bank data…":"↻ Fetch economic indicators"}</button>
   {macroError&&<p role="alert" style={{color:"#ffb4b4"}}>{macroError}</p>}
   {macro&&<><p style={{color:"#b9d5ef",fontSize:12}}>Source: <a href={macro.source_url} target="_blank" rel="noreferrer" style={{color:"#8de8ff"}}>{macro.source}</a> · Retrieved {new Date(macro.retrieved_at).toLocaleString()} · Annual historical data · Trade execution disabled</p>
   <div style={{overflowX:"auto"}}><table><thead><tr><th>Economy</th><th>Indicator</th><th>Published value</th><th>Year</th><th>Feed status</th></tr></thead><tbody>{macro.observations.map((o:any,i:number)=><tr key={i}><td>{({USA:"United States",GBR:"United Kingdom",EMU:"Euro Area",JPN:"Japan",CHE:"Switzerland"} as Record<string,string>)[o.country]||o.country}</td><td>{({inflation_consumer_pct:"Inflation (CPI)",gdp_growth_pct:"GDP growth",unemployment_pct:"Unemployment"} as Record<string,string>)[o.indicator]||o.indicator}</td><td>{o.status==="available"?o.value+"%":"—"}</td><td>{o.year||"—"}</td><td style={{color:o.status==="available"?"#86efac":"#fca5a5"}}>{o.status}</td></tr>)}</tbody></table></div>
   <p style={{color:"#fbd38d",fontSize:12}}>Historical context only. No economic-calendar, news, exchange order or automatic trade integration is claimed here.</p></>}
  </div>}
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
