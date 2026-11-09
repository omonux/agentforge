import {useCallback,useEffect,useState} from "react";
import {apiFetch,API} from "./api";

type Decision={type:string;symbol:string|null;reason:string|null;meaning:string;time:string};
type Diagnostics={engine_running:boolean;emergency_stopped:boolean;paper_positions:number;latest_outcome:Decision|null;recent_decisions:Decision[];notice:string};
const status=(type:string)=>type==="PAPER_ENTRY"?"PAPER BUY/SELL OPENED":type==="COUNCIL_DECISION"?"COUNCIL REVIEW":type.includes("ERROR")?"ERROR":type==="RISK_BLOCK"?"ENTRY BLOCKED":type==="MARKET_DATA_BLOCK"?"DATA BLOCK":"ENGINE EVENT";
export default function OmonuxDecisionExplainer(){
 const [data,SD]=useState<Diagnostics|null>(null),[error,SE]=useState(""),[busy,SB]=useState(false),[filter,SF]=useState("ALL");
 const refresh=useCallback(async()=>{SB(true);try{const response=await apiFetch(API+"/api/v1/trading/auto/diagnostics");const result=await response.json();if(!response.ok)throw Error(result.detail||"Diagnostics unavailable");SD(result);SE("")}catch(e){SE(e instanceof Error?e.message:"Diagnostics unavailable")}finally{SB(false)}},[]);
 useEffect(()=>{refresh();const timer=window.setInterval(()=>{if(!document.hidden)refresh()},30000);return()=>window.clearInterval(timer)},[refresh]);
 const items=(data?.recent_decisions||[]).filter(e=>filter==="ALL"||e.type===filter);
 return <section className="omx-universe-panel" aria-label="Paper trading decision diagnostics">
  <div className="portfoliohead"><div><h3>Why didn't the AI BUY or SELL?</h3><small>Real audit history · technical signals → AI council → risk approval → simulated position</small></div><button type="button" className="secondary" disabled={busy} onClick={refresh}>{busy?"Checking…":"Refresh diagnostics"}</button></div>
  {error&&<p role="alert">{error}</p>}
  {data&&<><div className="omx-universe-stats"><div><b>{data.engine_running?"RUNNING":"STOPPED"}</b><small>Paper engine</small></div><div><b>{data.emergency_stopped?"ACTIVE":"CLEAR"}</b><small>Emergency stop</small></div><div><b>{data.paper_positions}</b><small>Open paper positions</small></div><div><b>{data.recent_decisions.filter(x=>x.type==="PAPER_ENTRY").length}</b><small>Recent paper entries</small></div></div>
   <div role="status" className="omx-scan-diagnostics"><b>Latest recorded trading outcome</b>{data.latest_outcome?<p><strong>{status(data.latest_outcome.type)}</strong> {data.latest_outcome.symbol||""}: {data.latest_outcome.reason||data.latest_outcome.meaning} · {new Date(data.latest_outcome.time).toLocaleString()}</p>:<p>No recorded trading decisions yet. Start the paper engine and run a cycle, then refresh.</p>}</div>
   <div className="actions"><label>Show events <select value={filter} onChange={e=>SF(e.target.value)}><option value="ALL">All decisions</option><option value="RISK_BLOCK">Entry blocks</option><option value="COUNCIL_DECISION">Council votes</option><option value="MARKET_DATA_BLOCK">Market data blocks</option><option value="CYCLE_ERROR">Cycle errors</option><option value="SCHEDULER_ERROR">Scheduler errors</option><option value="PAPER_ENTRY">Paper entries</option></select></label></div>
   <div className="omx-market-list">{items.slice(0,40).map((e,i)=><div className="omx-market-row" key={e.time+"-"+i}><b>{e.symbol||"Engine"}</b><span>{status(e.type)}</span><small>{e.reason||e.meaning}</small><em>{new Date(e.time).toLocaleTimeString()}</em></div>)}</div>
   {!items.length&&<p className="muted">No recorded events match this filter.</p>}
   <p className="guard">{data.notice} A technical BUY is not an order: council and risk checks must also pass. A HOLD means no qualified directional setup; provider errors appear separately.</p>
  </>}
 </section>
}
