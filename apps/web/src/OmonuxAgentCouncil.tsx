import {useState} from "react";
import {apiFetch,API} from "./api";
import {Bot,RefreshCw,ShieldCheck,Users,AlertTriangle,Activity} from "lucide-react";

const defaultAgents=[
 "Market Regime Analyst","Trend Analyst","Momentum Analyst","Volume Analyst",
 "Volatility Analyst","Support & Resistance Analyst","Multi-Timeframe Analyst",
 "Breakout Analyst","Mean-Reversion Analyst","Liquidity & Execution Analyst",
 "Strategy Analyst","Skeptic / Red-Team Analyst"
];
export default function OmonuxAgentCouncil({onNotice}:{onNotice:(s:string)=>void}){
 const [symbol,S]=useState("BTCUSDT"),[timeframe,T]=useState("30m"),[busy,B]=useState(false),[result,R]=useState<any>(null);
 async function scan(e:any){
  e.preventDefault();B(true);R(null);
  try{
   const response=await apiFetch(API+"/api/v1/trading/agents/scan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol,timeframe})});
   const data=await response.json();
   if(!response.ok)throw Error(data.detail||"Twelve-agent scan failed");
   R(data);onNotice("Twelve-agent market council completed. Review the votes and risk warnings.");
  }catch(err){onNotice(err instanceof Error?err.message:"Twelve-agent scan failed");}
  finally{B(false);}
 }
 const council=result?.council, counts=council?.vote_counts;
 return <section className="panel omx-council">
  <div className="portfoliohead"><div><h3><Users size={17}/> Twelve-agent trading council</h3><small>12 specialist reviews · deterministic signal gate · guarded Spot review</small></div><span className="status">AI COUNCIL</span></div>
  <div className="omx-auto-warning"><ShieldCheck size={16}/> The agents analyze the setup and produce a decision packet. A passing result can proceed to manual Spot order review; the agents cannot submit live orders. Missing votes or any critical veto blocks it.</div>
  <form className="backtestform" onSubmit={scan}>
   <div className="twocol">
    <label>Market symbol<input value={symbol} onChange={e=>S(e.target.value.toUpperCase())} maxLength={20} required placeholder="BTCUSDT"/></label>
    <label>Timeframe<select value={timeframe} onChange={e=>T(e.target.value)}><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="30m">30 minutes</option><option value="1h">1 hour</option><option value="4h">4 hours</option><option value="1d">1 day</option></select></label>
   </div>
   <button className="primary" disabled={busy}><Bot size={15}/>{busy?"Running 12 specialist agents…":"Run 12-agent analysis"}</button>
  </form>
  {busy&&<div className="guard"><Activity size={14}/> Each specialist sends a separate analysis request to the same configured AI provider/model. This can take a little time and uses provider API tokens; these are not twelve separately hosted models.</div>}
  {!result&&<div className="council-grid">{defaultAgents.map((name,i)=><div className="council-agent" key={name}><span>{String(i+1).padStart(2,"0")}</span><b>{name}</b><em>READY</em></div>)}</div>}
  {council&&<div className="council-result">
   <div className={"council-verdict "+(council.approved?"approved":"blocked")}>
    <div><small>COUNCIL CONCLUSION</small><h4>{council.execution_gate?.manual_review_eligible?"ELIGIBLE FOR MANUAL SPOT REVIEW":"NO TRADE — SETUP BLOCKED"}</h4><p>{council.buy_consensus_percent}% buy consensus · {council.completed_agents}/12 agents completed</p></div>
    <strong>{council.vote_counts.BUY} BUY<br/>{council.vote_counts.SELL} SELL<br/>{council.vote_counts.HOLD} HOLD</strong>
   </div>
   <div className="stats">
    <div className="stat"><small>Technical signal</small><strong>{result.technical_signal.side}</strong></div>
    <div className="stat"><small>Signal score</small><strong>{result.technical_signal.confidence}%</strong></div>
    <div className="stat"><small>Average BUY confidence</small><strong>{council.average_buy_confidence}%</strong></div>
    <div className="stat"><small>Required BUY votes</small><strong>{council.required_buy_votes}/12</strong></div>
   </div>
   {council.vetoes?.length>0&&<div className="omx-auto-warning"><AlertTriangle size={15}/> Critical veto from: {council.vetoes.join(", ")}</div>}
   {council.errors?.length>0&&<div className="omx-auto-warning"><AlertTriangle size={15}/> Some agents failed: {council.errors.join("; ")}</div>}
   <div className="council-votes">{council.agents.map((agent:any,i:number)=><article className="council-vote" key={agent.id}>
    <div><span>{String(i+1).padStart(2,"0")}</span><b>{agent.name}</b><em className={"vote-"+agent.stance.toLowerCase()}>{agent.status==="failed"?"FAILED":agent.stance}</em></div>
    <p>{agent.reason}</p><small>{agent.confidence}% confidence{agent.veto?" · CRITICAL VETO":""}</small>
   </article>)}</div>
   <div className="omx-auto-warning"><ShieldCheck size={14}/> {council.execution_gate?.required_next_step||council.notice}</div><div className="guard"><ShieldCheck size={14}/> AI decisions never submit orders. Any order still requires a fresh exchange preview, account and permission checks, risk limits, and your explicit confirmation. Evidence uses completed public candles; order-book depth, funding, open interest and verified news are not currently supplied.</div>
  </div>}
 </section>
}
