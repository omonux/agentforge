import {useState} from "react";
import {apiFetch,API} from "./api";

type Trade={side:string;entry_time:number;exit_time:number;entry:number;exit:number;reason:string;net_return_pct:number};
type Result={symbol:string;interval:string;source:string;candles:number;first_candle_time:number;last_candle_time:number;trade_count:number;win_rate_pct:number;net_return_pct:number;max_drawdown_pct:number;profit_factor:number|null;fee_bps:number;slippage_bps:number;trades:Trade[];notice:string};
export default function OmonuxBacktesting(){
 const [fee,F]=useState(10),[slippage,S]=useState(5),[loading,L]=useState(false),[error,E]=useState(""),[result,R]=useState<Result|null>(null);
 async function run(){
  L(true);E("");R(null);
  try{
   const response=await apiFetch(API+"/api/v1/trading/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol:"BTCUSDT",interval:"15m",limit:500,fee_bps:fee,slippage_bps:slippage})});
   const body=await response.json();
   if(!response.ok)throw Error(typeof body.detail==="string"?body.detail:"Historical backtest failed");
   R(body);
  }catch(err){E(err instanceof Error?err.message:"Backtest unavailable")}finally{L(false)}
 }
 return <section className="panel" aria-label="Historical backtesting">
  <div className="portfoliohead"><div><h3>Historical Backtesting · BTCUSDT</h3><small>15-minute completed Binance candles · research only · no orders</small></div><span className="status paused">PAPER / RESEARCH</span></div>
  <div className="omx-auto-grid">
   <label>Trading fee (basis points)<input type="number" min="0" max="100" step="1" value={fee} onChange={e=>F(Number(e.target.value))}/></label>
   <label>Slippage per fill (basis points)<input type="number" min="0" max="100" step="1" value={slippage} onChange={e=>S(Number(e.target.value))}/></label>
  </div>
  <div className="actions"><button className="primary" type="button" disabled={loading||!Number.isFinite(fee)||!Number.isFinite(slippage)||fee<0||fee>100||slippage<0||slippage>100} onClick={run}>{loading?"Fetching and testing…":"Run BTCUSDT 15m backtest"}</button></div>
  {error&&<p role="alert">{error}</p>}
  {result&&<div role="status">
   <p><strong>{result.trade_count} historical trades</strong> · {result.candles} closed candles · {result.source}</p>
   <div className="omx-auto-grid"><div><strong>Net compounded return</strong><p>{result.net_return_pct.toFixed(2)}%</p></div><div><strong>Win rate</strong><p>{result.win_rate_pct.toFixed(2)}%</p></div><div><strong>Max drawdown</strong><p>{result.max_drawdown_pct.toFixed(2)}%</p></div><div><strong>Profit factor</strong><p>{result.profit_factor===null?"N/A":result.profit_factor.toFixed(2)}</p></div></div>
   <small>Data: {new Date(result.first_candle_time).toLocaleString()} – {new Date(result.last_candle_time).toLocaleString()} · Fee {result.fee_bps} bps · Slippage {result.slippage_bps} bps</small>
   <h4>Historical trades</h4>
   {result.trades.length?result.trades.slice(-30).reverse().map((t,i)=><div className="taskrow" key={i}><span><b>{t.side} · {t.reason}</b><small>{new Date(t.entry_time).toLocaleString()} → {new Date(t.exit_time).toLocaleString()} · {t.entry.toFixed(4)} → {t.exit.toFixed(4)}</small></span><em>{t.net_return_pct.toFixed(2)}%</em></div>):<p>No qualifying trades in this sample.</p>}
   <p className="muted">{result.notice} The backtest excludes funding, borrowing costs, partial fills and out-of-sample validation.</p>
  </div>}
 </section>
}
