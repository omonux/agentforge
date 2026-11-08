import {useState} from "react";
import {apiFetch,API} from "./api";
import {BrainCircuit,RefreshCw,ShieldCheck,TrendingUp,FlaskConical} from "lucide-react";

export default function OmonuxStrategyLab({onNotice}:{onNotice:(s:string)=>void}){
 const [symbol,S]=useState("BTCUSDT"),[timeframe,T]=useState("30m"),[busy,B]=useState(false),[report,R]=useState<any>(null);
 async function run(e:any){e.preventDefault();B(true);R(null);try{const r=await apiFetch(API+"/api/v1/trading/research/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol,timeframe,candle_limit:1000})});const d=await r.json();if(!r.ok)throw Error(d.detail||"Research run failed");R(d);onNotice("Walk-forward strategy research completed. Review out-of-sample results.");}catch(err){onNotice(err instanceof Error?err.message:"Research run failed");}finally{B(false)}}
 const test=report?.out_of_sample;
 return <section className="panel omx-strategy-lab">
  <div className="portfoliohead"><div><h3><BrainCircuit size={17}/> Strategy intelligence lab</h3><small>Walk-forward research · parameter selection separated from final test</small></div><span className="status">RESEARCH ONLY</span></div>
  <p>Tests a small, fixed EMA/RSI strategy family against completed exchange candles. Parameters are selected on the first 70% and evaluated on an untouched final 30%.</p>
  <form className="backtestform" onSubmit={run}><div className="twocol">
   <label>Market symbol<input value={symbol} onChange={e=>S(e.target.value.toUpperCase())} maxLength={20}/></label>
   <label>Timeframe<select value={timeframe} onChange={e=>T(e.target.value)}><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="30m">30 minutes</option><option value="1h">1 hour</option><option value="4h">4 hours</option><option value="1d">1 day</option></select></label>
  </div><button className="primary" disabled={busy}><FlaskConical size={15}/>{busy?"Testing strategies…":"Run walk-forward research"}</button></form>
  {busy&&<div className="guard"><RefreshCw size={14}/> Downloading completed candles and evaluating parameter candidates. This can take a moment.</div>}
  {report&&<div className="research-report">
   <div className={"council-verdict "+(report.assessment==="POSITIVE_OUT_OF_SAMPLE"?"approved":"blocked")}><div><small>OUT-OF-SAMPLE ASSESSMENT</small><h4>{report.assessment==="POSITIVE_OUT_OF_SAMPLE"?"POSITIVE — NEEDS MORE VALIDATION":"NOT VALIDATED"}</h4><p>{report.data.total_completed_candles} candles · {report.data.split}</p></div><strong>EMA {report.selected_parameters.fast_ema}/{report.selected_parameters.slow_ema}<br/>RSI {report.selected_parameters.rsi_filter}</strong></div>
   <div className="stats"><div className="stat"><small>Test return</small><strong>{test.return_pct}%</strong></div><div className="stat"><small>Max drawdown</small><strong>{test.max_drawdown_pct}%</strong></div><div className="stat"><small>Profit factor</small><strong>{test.profit_factor}</strong></div><div className="stat"><small>Win rate</small><strong>{test.win_rate_pct}%</strong></div></div>
   <div className="taskrow"><span><b>Out-of-sample trades</b><small>Final 30%, untouched during parameter selection</small></span><b>{test.trades}</b></div>
   <div className="taskrow"><span><b>Buy-and-hold comparison</b><small>Same test period, before fees</small></span><b>{report.buy_and_hold_test_return_pct}%</b></div>
   <div className="taskrow"><span><b>Selected parameters</b><small>Chosen using training-period return penalized for drawdown</small></span><b>{report.selected_parameters.fast_ema}/{report.selected_parameters.slow_ema}</b></div>
   <div className="guard"><ShieldCheck size={14}/> {report.limitations.join(" ")}</div>
  </div>}
 </section>
}
