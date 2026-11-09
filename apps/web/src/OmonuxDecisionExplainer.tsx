import {useCallback,useEffect,useMemo,useState} from "react";
import {Activity,AlertTriangle,ArrowDownRight,ArrowUpRight,CheckCircle2,Clock3,RefreshCw,ShieldCheck,SlidersHorizontal} from "lucide-react";
import {apiFetch,API} from "./api";
import "./OmonuxDecisionExplainer.css";

type Decision={type:string;symbol:string|null;reason:string|null;meaning:string;time:string};
type Diagnostics={engine_running:boolean;emergency_stopped:boolean;paper_positions:number;latest_outcome:Decision|null;recent_decisions:Decision[];notice:string};
const labels:Record<string,string>={PAPER_ENTRY:"Paper trade opened",COUNCIL_DECISION:"12-agent council review",RISK_BLOCK:"Entry prevented",MARKET_DATA_BLOCK:"Market data not ready",CYCLE_ERROR:"Cycle error",SCHEDULER_ERROR:"Scheduler error",RISK_CHECK_ERROR:"Risk check error",UNIVERSE_SCAN:"50-market scan",ENGINE_STARTED:"Engine started",ENGINE_STOPPED:"Engine stopped"};
function category(e:Decision){return e.type==="PAPER_ENTRY"?"positive":e.type.includes("ERROR")?"error":e.type.includes("BLOCK")?"caution":"neutral"}
function readable(e:Decision){
 const reason=e.reason||e.meaning;
 if(e.type==="COUNCIL_DECISION"){
  const buy=reason.match(/buy=(\d+)\/12/),sell=reason.match(/sell=(\d+)\/12/),approved=reason.match(/paper_approved=(True|False)/);
  return {headline:approved?.[1]==="True"?"Council approved a paper candidate":"Council did not approve an entry",detail:`BUY votes: ${buy?.[1]??"?"}/12 · SELL votes: ${sell?.[1]??"?"}/12. ${reason}`};
 }
 if(e.type==="RISK_BLOCK"&&reason.includes("HOLD"))return {headline:"No directional trade setup",detail:"Technical indicators currently favor waiting. "+reason};
 if(e.type==="RISK_BLOCK"&&reason.includes("confidence"))return {headline:"Confidence below your limit",detail:reason+". This threshold is configured in Paper Trading settings."};
 if(e.type==="RISK_BLOCK"&&reason.includes("already reviewed"))return {headline:"Waiting for the next completed candle",detail:reason};
 if(e.type==="MARKET_DATA_BLOCK")return {headline:"Exchange prices could not be verified",detail:reason};
 if(e.type==="PAPER_ENTRY")return {headline:"A simulated position was opened",detail:reason};
 if(e.type.includes("ERROR"))return {headline:"Technical issue needs attention",detail:reason};
 return {headline:labels[e.type]||e.meaning,detail:reason};
}
export default function OmonuxDecisionExplainer(){
 const [data,SD]=useState<Diagnostics|null>(null),[error,SE]=useState(""),[busy,SB]=useState(false),[filter,SF]=useState("ALL"),[lastRefresh,SL]=useState("");
 const refresh=useCallback(async()=>{SB(true);try{const response=await apiFetch(API+"/api/v1/trading/auto/diagnostics");const result=await response.json();if(!response.ok)throw Error(result.detail||"Diagnostics unavailable");SD(result);SE("");SL(new Date().toLocaleTimeString())}catch(e){SE(e instanceof Error?e.message:"Diagnostics unavailable")}finally{SB(false)}},[]);
 useEffect(()=>{refresh();const timer=window.setInterval(()=>{if(!document.hidden)refresh()},30000);return()=>window.clearInterval(timer)},[refresh]);
 const events=useMemo(()=>(data?.recent_decisions||[]).filter(e=>filter==="ALL"||e.type===filter),[data,filter]);
 const latest=data?.latest_outcome;
 const latestCopy=latest?readable(latest):null;
 const entryCount=data?.recent_decisions.filter(e=>e.type==="PAPER_ENTRY").length||0;
 const blockedCount=data?.recent_decisions.filter(e=>e.type==="RISK_BLOCK"||e.type==="MARKET_DATA_BLOCK").length||0;
 return <section className="omx-decision" aria-label="AI paper trading decision intelligence">
  <div className="omx-decision-hero"><div className="omx-decision-kicker"><Activity size={15}/> OMONUX · DECISION INTELLIGENCE <span className="omx-decision-pill">PAPER ONLY</span></div>
   <div className="omx-decision-heading"><div><h3>Understand every trading decision.</h3><p>Know why the 12-agent council approved, waited, or blocked a BUY or SELL. Based on recorded engine events, not invented predictions.</p></div><button type="button" className="omx-decision-refresh" disabled={busy} onClick={refresh}><RefreshCw size={15} className={busy?"omx-decision-spinning":""}/>{busy?"Checking…":"Refresh analysis"}</button></div>
   <div className="omx-decision-meta"><Clock3 size={13}/> {lastRefresh?"Updated "+lastRefresh:"Waiting for first update"} · Automatic refresh every 30 seconds while visible</div>
  </div>
  {error&&<div className="omx-decision-error" role="alert"><AlertTriangle size={18}/><span>Unable to load current diagnostics: {error}. Previous data, if shown, may be stale.</span></div>}
  {data&&<><div className="omx-decision-metrics">
   <div><span>Paper engine</span><strong className={data.engine_running?"omx-decision-green":""}>{data.engine_running?"● Running":"○ Stopped"}</strong><small>{data.engine_running?"Eligible cycles can run":"Start the engine to evaluate entries"}</small></div>
   <div><span>Risk protection</span><strong className={data.emergency_stopped?"omx-decision-red":"omx-decision-green"}>{data.emergency_stopped?"Stop active":"Protected"}</strong><small>{data.emergency_stopped?"New entries are disabled":"Safety latch clear"}</small></div>
   <div><span>Open positions</span><strong>{data.paper_positions}</strong><small>Simulated trades only</small></div>
   <div><span>Recent decisions</span><strong>{entryCount} <span className="omx-decision-metric-suffix">entries</span></strong><small>{blockedCount} recorded blocks · last 300 audit events</small></div>
  </div>
  <div className="omx-decision-feature" role="status"><div className="omx-decision-feature-icon">{latest?.type==="PAPER_ENTRY"?<CheckCircle2 size={24}/>:latest?.type.includes("ERROR")?<AlertTriangle size={24}/>:<ShieldCheck size={24}/>}</div><div><span className="omx-decision-eyebrow">LATEST RECORDED OUTCOME</span><h4>{latestCopy?.headline||"No trading decisions recorded yet"}</h4><p>{latestCopy?.detail||"Start the paper engine and run a cycle. The explanation will appear here after an event is recorded."}</p>{latest&&<small>{latest.symbol||"Trading engine"} · {new Date(latest.time).toLocaleString()}</small>}</div></div>
  <div className="omx-decision-history"><div className="omx-decision-history-head"><div><h4>Decision timeline</h4><p>Every item below comes from the backend audit history.</p></div><label><SlidersHorizontal size={15}/><select aria-label="Filter trading decisions" value={filter} onChange={e=>SF(e.target.value)}><option value="ALL">All decisions</option><option value="RISK_BLOCK">Risk blocks</option><option value="COUNCIL_DECISION">Council votes</option><option value="MARKET_DATA_BLOCK">Data issues</option><option value="CYCLE_ERROR">Cycle errors</option><option value="SCHEDULER_ERROR">Scheduler errors</option><option value="PAPER_ENTRY">Paper entries</option></select></label></div>
  <div className="omx-decision-events">{events.slice(0,40).map((e,i)=>{const copy=readable(e);return <div className={"omx-decision-event omx-decision-"+category(e)} key={e.time+"-"+i}><div className="omx-decision-event-mark">{e.type==="PAPER_ENTRY"?<ArrowUpRight size={17}/>:e.type.includes("BLOCK")||e.type.includes("ERROR")?<AlertTriangle size={16}/>:<ArrowDownRight size={16}/>}</div><div className="omx-decision-event-copy"><div className="omx-decision-event-top"><strong>{copy.headline}</strong><span>{e.symbol||"ENGINE"}</span></div><p>{copy.detail}</p><small>{labels[e.type]||e.type} · {new Date(e.time).toLocaleString()}</small></div></div>})}</div>
  {!events.length&&<div className="omx-decision-empty">No recorded decisions match this filter.</div>}</div>
  <div className="omx-decision-footer"><ShieldCheck size={16}/><span>BUY/SELL signals are proposals, not orders. The AI council and risk checks must both approve a paper entry. HOLD can be a valid result. No real exchange orders are placed.</span></div>
  </>}
 </section>
}
