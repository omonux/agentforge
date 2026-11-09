import {useCallback,useEffect,useRef,useState} from "react";
import {apiFetch,API} from "./api";

type Route={buy_venue:string;sell_venue:string;gross_edge_bps:number;estimated_net_edge_bps:number;top_of_book_base_qty:number;indicative_notional_usdt:number;passes_assumed_cost_threshold:boolean};
type Market={symbol:string;status?:string;reason?:string;best_route?:Route;fetch_duration_ms?:number};
type Snapshot={checked_at_unix_ms:number;markets:Market[];market_count:number;notice:string};
const available=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","LTCUSDT"];
export default function OmonuxOrderbookMonitor(){
 const [selected,SS]=useState<string[]>(["BTCUSDT","ETHUSDT","SOLUSDT"]);
 const [fee,SF]=useState(20),[slippage,SL]=useState(10),[extra,SE]=useState(5);
 const [auto,SA]=useState(false),[busy,SB]=useState(false),[error,ER]=useState(""),[snapshot,SR]=useState<Snapshot|null>(null);
 const [history,SH]=useState<{time:number;symbol:string;edge:number}[]>([]);
 const [stored,ST]=useState<{checked_at_ms:number;estimated_net_edge_bps:number;gross_edge_bps:number;buy_venue:string;sell_venue:string}[]>([]);
 const [historyError,HE]=useState("");
 const [historySymbol,HS]=useState("BTCUSDT");
 const mounted=useRef(true),inFlight=useRef(false);
 const loadHistory=useCallback(async()=>{
  try{
   const response=await apiFetch(API+"/api/v1/trading/orderbook/history?symbol="+encodeURIComponent(historySymbol)+"&limit=100");
   const result=await response.json();
   if(!response.ok)throw Error(result.detail||"History unavailable");
   if(mounted.current){ST(result.observations||[]);HE("");}
  }catch(e){if(mounted.current)HE(e instanceof Error?e.message:"History unavailable")}
 },[historySymbol]);
 useEffect(()=>{loadHistory()},[loadHistory]);
 const scan=useCallback(async()=>{
  if(inFlight.current||!selected.length)return;
  inFlight.current=true;SB(true);ER("");
  try{
   const response=await apiFetch(API+"/api/v1/trading/orderbook/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbols:selected,fee_bps:fee,slippage_bps:slippage,extra_cost_bps:extra})});
   const data=await response.json();
   if(!response.ok)throw Error(data.detail||"Order-book scan unavailable");
   if(mounted.current){SR(data);loadHistory();SH(old=>[...old,...data.markets.filter((m:Market)=>m.best_route).map((m:Market)=>({time:data.checked_at_unix_ms,symbol:m.symbol,edge:m.best_route!.estimated_net_edge_bps}))].slice(-200));}
  }catch(e){if(mounted.current)ER(e instanceof Error?e.message:"Scan failed")}finally{inFlight.current=false;if(mounted.current)SB(false)}
 },[selected,fee,slippage,extra,loadHistory]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{if(!auto)return;scan();const id=window.setInterval(()=>{if(!document.hidden)scan()},30000);return()=>window.clearInterval(id)},[auto,scan]);
 function toggle(symbol:string){SS(old=>old.includes(symbol)?old.filter(s=>s!==symbol):[...old,symbol])}
 return <section className="panel" aria-label="Live order-book intelligence">
  <div className="portfoliohead"><div><h3>Live Market Intelligence</h3><small>Binance + Bybit · public top-of-book quotes · estimated cross-venue edges</small></div><span className="status paused">READ ONLY</span></div>
  <p className="muted">No API key required for public quotes. Monitoring runs every 30 seconds while this tab is visible; it stops when you leave the page. No exchange orders are placed.</p>
  <div className="actions">{available.map(symbol=><button key={symbol} type="button" className={selected.includes(symbol)?"primary":"secondary"} aria-pressed={selected.includes(symbol)} onClick={()=>toggle(symbol)} disabled={busy}>{symbol.replace("USDT","")}</button>)}</div>
  <div className="omx-auto-grid">
   <label>Combined fees (bps)<input type="number" min="0" max="100" step="1" value={fee} onChange={e=>SF(Number(e.target.value))}/></label>
   <label>Estimated slippage (bps)<input type="number" min="0" max="100" step="1" value={slippage} onChange={e=>SL(Number(e.target.value))}/></label>
   <label>Other costs (bps)<input type="number" min="0" max="100" step="1" value={extra} onChange={e=>SE(Number(e.target.value))}/></label>
  </div>
  <div className="actions"><button type="button" className="primary" onClick={scan} disabled={busy||selected.length===0||[fee,slippage,extra].some(v=>!Number.isFinite(v)||v<0||v>100)}>{busy?"Checking exchanges…":"Scan live quotes"}</button><button type="button" className="secondary" aria-pressed={auto} onClick={()=>SA(!auto)}>{auto?"Stop monitoring":"Start 30s monitoring"}</button><button type="button" className="secondary" onClick={()=>SH([])} disabled={!history.length}>Clear observations</button></div>
  {error&&<p role="alert">{error}</p>}
  {snapshot&&<div aria-live="polite"><p><b>{snapshot.market_count} markets checked</b> · {new Date(snapshot.checked_at_unix_ms).toLocaleString()} · {snapshot.markets.filter(m=>m.best_route?.passes_assumed_cost_threshold).length} above assumed cost threshold (not executable signals)</p>
   {snapshot.markets.map(m=><div className="taskrow" key={m.symbol}><span><b>{m.symbol}</b>{m.best_route?<small>Buy {m.best_route.buy_venue} / Sell {m.best_route.sell_venue} · gross {m.best_route.gross_edge_bps.toFixed(2)} bps · top-level size {m.best_route.top_of_book_base_qty.toFixed(5)} · ~${m.best_route.indicative_notional_usdt.toFixed(2)} · fetch {m.fetch_duration_ms}ms</small>:<small>{m.reason||"Market data unavailable"}</small>}</span><em>{m.best_route?m.best_route.estimated_net_edge_bps.toFixed(2)+" bps net est.":"UNAVAILABLE"}</em></div>)}
   <p className="muted">{snapshot.notice}</p>
  </div>}
  <h4>Saved market observations</h4>
  <div className="actions"><label>Market <select value={historySymbol} onChange={e=>HS(e.target.value)}>{available.map(s=><option value={s} key={s}>{s}</option>)}</select></label><button type="button" className="secondary" onClick={loadHistory}>Refresh saved history</button></div>
  {historyError&&<p role="alert">{historyError}</p>}
  <p className="muted">Last {stored.length} saved snapshots for {historySymbol}. Stored in the application database; persistence across redeploys requires durable storage.</p>
  {stored.slice(0,15).map((h,i)=><div className="taskrow" key={h.checked_at_ms+"-"+i}><span><b>{new Date(h.checked_at_ms).toLocaleString()}</b><small>Buy {h.buy_venue} / Sell {h.sell_venue} · gross {h.gross_edge_bps.toFixed(2)} bps</small></span><em>{h.estimated_net_edge_bps.toFixed(2)} bps net est.</em></div>)}
  <h4>Recent observations ({history.length} points, this page session only)</h4>
  {history.length?<div className="omx-auto-bottom"><div>{history.slice(-20).reverse().map((h,i)=><div className="taskrow" key={i}><span><b>{h.symbol}</b><small>{new Date(h.time).toLocaleTimeString()}</small></span><em>{h.edge.toFixed(2)} bps</em></div>)}</div></div>:<p className="muted">Start monitoring to collect indicative observations. These are not filled trades or realized profits.</p>}
  <p className="guard">Snapshots from two exchanges are not simultaneous. A positive estimated edge is not proof of executable arbitrage; actual bid/ask liquidity, latency and costs may differ. Research only.</p>
 </section>
}
