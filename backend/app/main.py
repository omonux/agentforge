import os, sqlite3, uuid, asyncio
from .omonux_engine import fetch_candles, build_signal
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
load_dotenv()
DB=Path(os.getenv("DATABASE_PATH","./agentforge.db"))
BASE=os.getenv("AI_BASE_URL","").rstrip("/")
KEY=os.getenv("AI_API_KEY","")
MODEL=os.getenv("AI_MODEL","")
AGENTS={
"support":("Customer Support","Answer from supplied policy/context only. Never invent order, account, refund or policy facts. Escalate uncertainty."),
"sales":("Sales Assistant","Qualify prospects from authorized sources and draft personalized follow-ups. Never send messages."),
"content":("Content Studio","Create original research-aware scripts, captions and content plans. Never claim content was published."),
"automation":("Workflow Assistant","Create reviewable workflow plans. Never perform external side effects."),
"research":("Research Analyst","Analyze supplied sources, separate facts from assumptions and explain limitations.")
}
def stamp(): return datetime.now(timezone.utc).isoformat()
def db():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
@asynccontextmanager
async def life(app):
 with db() as c:
  c.execute("CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, agent TEXT, title TEXT, prompt TEXT, status TEXT, result TEXT, error TEXT, created TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS paper_trades(id TEXT PRIMARY KEY,symbol TEXT,side TEXT,qty REAL,price REAL,created TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT,company TEXT,stage TEXT NOT NULL,notes TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY,customer TEXT NOT NULL,email TEXT,subject TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,reply_draft TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS content_items(id TEXT PRIMARY KEY,title TEXT NOT NULL,channel TEXT NOT NULL,format TEXT NOT NULL,status TEXT NOT NULL,script TEXT,caption TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,name TEXT NOT NULL,trigger_name TEXT NOT NULL,action_plan TEXT NOT NULL,status TEXT NOT NULL,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS watchlist(id TEXT PRIMARY KEY,symbol TEXT NOT NULL UNIQUE,note TEXT,created TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS backtests(id TEXT PRIMARY KEY,symbol TEXT,fast_window INTEGER,slow_window INTEGER,initial_cash REAL,final_equity REAL,return_pct REAL,max_drawdown_pct REAL,trade_count INTEGER,created TEXT,report TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS auto_trade_settings(id INTEGER PRIMARY KEY CHECK(id=1),running INTEGER NOT NULL DEFAULT 0,mode TEXT NOT NULL DEFAULT 'paper',risk_percent REAL NOT NULL DEFAULT 1,min_confidence INTEGER NOT NULL DEFAULT 60,max_open_positions INTEGER NOT NULL DEFAULT 3,max_daily_loss_percent REAL NOT NULL DEFAULT 5,cooldown_minutes INTEGER NOT NULL DEFAULT 15,max_trades_per_day INTEGER NOT NULL DEFAULT 10,max_notional_percent REAL NOT NULL DEFAULT 25,updated TEXT)")
  c.execute("INSERT OR IGNORE INTO auto_trade_settings(id,updated) VALUES(1,?)",(stamp(),))
  c.execute("CREATE TABLE IF NOT EXISTS auto_trade_positions(id TEXT PRIMARY KEY,symbol TEXT NOT NULL,side TEXT NOT NULL,quantity REAL NOT NULL,entry_price REAL NOT NULL,stop_price REAL NOT NULL,target_price REAL NOT NULL,opened TEXT NOT NULL)")
  c.execute("CREATE TABLE IF NOT EXISTS auto_trade_events(id TEXT PRIMARY KEY,event_type TEXT NOT NULL,symbol TEXT,details TEXT,pnl REAL,created TEXT NOT NULL)")
  c.execute("CREATE TABLE IF NOT EXISTS trading_safety_state(id INTEGER PRIMARY KEY CHECK(id=1),emergency_stopped INTEGER NOT NULL DEFAULT 0,reason TEXT,updated TEXT NOT NULL)")
  c.execute("INSERT OR IGNORE INTO trading_safety_state(id,updated) VALUES(1,?)",(stamp(),))
 scheduler=asyncio.create_task(auto_trade_scheduler())
 try:
  yield
 finally:
  scheduler.cancel()
  try: await scheduler
  except asyncio.CancelledError: pass
app=FastAPI(title="AgentForge API",version="0.1.0",lifespan=life)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",")],allow_methods=["*"],allow_headers=["*"],allow_credentials=True)
class Task(BaseModel):
 agent:str
 title:str=Field(min_length=2,max_length=120)
 prompt:str=Field(min_length=3,max_length=12000)
class PaperTrade(BaseModel):
 symbol:str=Field(min_length=2,max_length=20,pattern=r"^[A-Za-z0-9._-]+$")
 side:str
 quantity:float=Field(gt=0,le=1000000)
 reference_price:float=Field(gt=0)
async def ask(agent,prompt):
 if agent not in AGENTS: raise HTTPException(400,"Unknown agent type.")
 if not (BASE and KEY and MODEL): raise HTTPException(503,"AI provider is not configured. Set AI_BASE_URL, AI_API_KEY and AI_MODEL in backend/.env.")
 name,policy=AGENTS[agent]
 try:
  async with httpx.AsyncClient(timeout=90) as client:
   r=await client.post(BASE+"/chat/completions",headers={"Authorization":"Bearer "+KEY},json={"model":MODEL,"temperature":0.3,"messages":[{"role":"system","content":f"You are {name} in AgentForge. {policy} Be useful, honest and concise."},{"role":"user","content":prompt}]})
   r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]
 except httpx.HTTPStatusError as e: raise HTTPException(502,f"AI provider HTTP {e.response.status_code}.")
 except Exception: raise HTTPException(502,"AI provider request failed or returned an invalid response.")
@app.get("/health")
def health(): return {"status":"ok","ai_configured":bool(BASE and KEY and MODEL)}

# --- AI provider diagnostics (never return credentials) ---
@app.get("/api/v1/ai/status")
def ai_status():
 configured=bool(BASE and KEY and MODEL)
 provider="OpenAI" if BASE.startswith("https://api.openai.com") else ("OpenAI-compatible" if BASE else "Not configured")
 return {"configured":configured,"provider":provider,"model":MODEL if configured else None,"base_url":BASE if configured else None,"key_present":bool(KEY)}

@app.post("/api/v1/ai/test")
async def ai_test():
 if not (BASE and KEY and MODEL):
  raise HTTPException(503,"OpenAI is not configured. Add AI_API_KEY in your hosting environment and set AI_BASE_URL and AI_MODEL.")
 try:
  answer=await ask("research","Reply with exactly: AgentForge AI connection successful.")
  return {"connected":True,"provider":"OpenAI" if BASE.startswith("https://api.openai.com") else "OpenAI-compatible","model":MODEL,"message":answer}
 except HTTPException as e:
  if e.status_code==502: raise HTTPException(502,"The AI provider could not complete the test. Check the API key, model name and API billing/limits in your provider dashboard.")
  raise

@app.get("/api/v1/agents")
def agents(): return [{"id":k,"name":v[0],"description":v[1]} for k,v in AGENTS.items()]
@app.post("/api/v1/tasks")
async def create_task(t:Task):
 if t.agent not in AGENTS: raise HTTPException(400,"Unknown agent.")
 tid=str(uuid.uuid4()); created=stamp()
 with db() as c: c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)",(tid,t.agent,t.title,t.prompt,"running",None,None,created))
 try: result=await ask(t.agent,t.prompt)
 except HTTPException as e:
  with db() as c: c.execute("UPDATE tasks SET status=?,error=? WHERE id=?",("failed",str(e.detail),tid))
  raise
 with db() as c:
  c.execute("UPDATE tasks SET status=?,result=? WHERE id=?",("completed",result,tid))
  row=dict(c.execute("SELECT * FROM tasks WHERE id=?",(tid,)).fetchone())
 return row
@app.get("/api/v1/tasks")
def tasks():
 with db() as c: return [dict(x) for x in c.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 100")]
@app.get("/api/v1/trading")
def trading(): return {"product":"Omonux Trading","mode":"paper_only","live_trading_enabled":False,"message":"No broker connected and no live orders are possible."}
@app.get("/api/v1/trading/paper/trades")
def trades():
 with db() as c: return [dict(x) for x in c.execute("SELECT * FROM paper_trades ORDER BY created DESC LIMIT 100")]
@app.post("/api/v1/trading/paper/trades")
def paper(t:PaperTrade):
 if t.side not in ("buy","sell"): raise HTTPException(400,"Side must be buy or sell.")
 positions,_=calculate_positions()
 held=next((p["quantity"] for p in positions if p["symbol"]==t.symbol.upper()),0.0)
 if t.side=="sell" and t.quantity>held+1e-10: raise HTTPException(400,f"Cannot sell {t.quantity}; paper position is {held}.")
 tid=str(uuid.uuid4())
 with db() as c: c.execute("INSERT INTO paper_trades VALUES(?,?,?,?,?,?)",(tid,t.symbol.upper(),t.side,t.quantity,t.reference_price,stamp()))
 return {"id":tid,"symbol":t.symbol.upper(),"side":t.side,"quantity":t.quantity,"reference_price":t.reference_price,"status":"simulated","notice":"Simulation only. No real order was placed."}

# --- CRM: lead records and support inbox ---
class LeadIn(BaseModel):
 name:str=Field(min_length=1,max_length=120)
 email:str|None=None
 company:str|None=None
 stage:str="new"
 notes:str|None=None
class TicketIn(BaseModel):
 customer:str=Field(min_length=1,max_length=120)
 email:str|None=None
 subject:str=Field(min_length=2,max_length=180)
 message:str=Field(min_length=2,max_length=10000)
 priority:str="normal"
class TicketStatus(BaseModel):
 status:str
 reply_draft:str|None=None
class ContentIn(BaseModel):
 title:str=Field(min_length=2,max_length=180)
 channel:str="youtube"
 format:str="short_video"
 script:str|None=None
 caption:str|None=None
class WorkflowIn(BaseModel):
 name:str=Field(min_length=2,max_length=160)
 trigger_name:str=Field(min_length=2,max_length=160)
 action_plan:str=Field(min_length=2,max_length=10000)
class TradingAnalysisIn(BaseModel):
 symbol:str=Field(min_length=2,max_length=20,pattern=r"^[A-Za-z0-9._-]+$")
 timeframe:str=Field(default="daily",max_length=40)
 market_context:str=Field(min_length=20,max_length=12000)
class BacktestIn(BaseModel):
 symbol:str=Field(min_length=2,max_length=20,pattern=r"^[A-Za-z0-9._-]+$")
 closes:list[float]=Field(min_length=30,max_length=5000)
 fast_window:int=Field(ge=2,le=100)
 slow_window:int=Field(ge=5,le=300)
 initial_cash:float=Field(gt=0,le=100000000)
 fee_bps:float=Field(default=10,ge=0,le=100)
 slippage_bps:float=Field(default=5,ge=0,le=100)
class WatchItem(BaseModel):
 symbol:str=Field(min_length=2,max_length=20,pattern=r"^[A-Za-z0-9._-]+$")
 note:str|None=None
def rows(sql,args=()):
 with db() as c: return [dict(x) for x in c.execute(sql,args)]
def one(sql,args=()):
 with db() as c: r=c.execute(sql,args).fetchone(); return dict(r) if r else None
@app.get("/api/v1/crm/leads")
def get_leads(): return rows("SELECT * FROM leads ORDER BY updated DESC LIMIT 500")
@app.post("/api/v1/crm/leads")
def add_lead(x:LeadIn):
 if x.stage not in ("new","qualified","proposal","won","lost"): raise HTTPException(400,"Invalid lead stage.")
 now=stamp(); ident=str(uuid.uuid4())
 with db() as c: c.execute("INSERT INTO leads VALUES(?,?,?,?,?,?,?,?)",(ident,x.name,x.email,x.company,x.stage,x.notes,now,now))
 return one("SELECT * FROM leads WHERE id=?",(ident,))
@app.patch("/api/v1/crm/leads/{ident}")
def edit_lead(ident:str,x:LeadIn):
 if x.stage not in ("new","qualified","proposal","won","lost"): raise HTTPException(400,"Invalid lead stage.")
 with db() as c:
  cur=c.execute("UPDATE leads SET name=?,email=?,company=?,stage=?,notes=?,updated=? WHERE id=?",(x.name,x.email,x.company,x.stage,x.notes,stamp(),ident))
  if not cur.rowcount: raise HTTPException(404,"Lead not found.")
 return one("SELECT * FROM leads WHERE id=?",(ident,))
@app.get("/api/v1/support/tickets")
def get_tickets(): return rows("SELECT * FROM tickets ORDER BY created DESC LIMIT 500")
@app.post("/api/v1/support/tickets")
def add_ticket(x:TicketIn):
 if x.priority not in ("low","normal","high","urgent"): raise HTTPException(400,"Invalid priority.")
 ident=str(uuid.uuid4()); now=stamp()
 with db() as c: c.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)",(ident,x.customer,x.email,x.subject,x.message,"open",x.priority,None,now,now))
 return one("SELECT * FROM tickets WHERE id=?",(ident,))
@app.patch("/api/v1/support/tickets/{ident}")
def edit_ticket(ident:str,x:TicketStatus):
 if x.status not in ("open","pending","resolved","escalated"): raise HTTPException(400,"Invalid ticket status.")
 with db() as c:
  cur=c.execute("UPDATE tickets SET status=?,reply_draft=?,updated=? WHERE id=?",(x.status,x.reply_draft,stamp(),ident))
  if not cur.rowcount: raise HTTPException(404,"Ticket not found.")
 return one("SELECT * FROM tickets WHERE id=?",(ident,))
@app.post("/api/v1/support/tickets/{ident}/draft-reply")
async def draft_reply(ident:str):
 ticket=one("SELECT * FROM tickets WHERE id=?",(ident,))
 if not ticket: raise HTTPException(404,"Ticket not found.")
 result=await ask("support",f"Draft a helpful reply to this customer. Do not invent policy, account, order, refund or delivery facts. If information is missing, ask for it or recommend human escalation. Do not send the reply.\nCustomer: {ticket['customer']}\nSubject: {ticket['subject']}\nMessage: {ticket['message']}")
 with db() as c: c.execute("UPDATE tickets SET reply_draft=?,updated=? WHERE id=?",(result,stamp(),ident))
 return one("SELECT * FROM tickets WHERE id=?",(ident,))
# --- Content production board: draft -> review -> approved; publishing is intentionally not automated ---
@app.get("/api/v1/content")
def get_content(): return rows("SELECT * FROM content_items ORDER BY updated DESC LIMIT 500")
@app.post("/api/v1/content")
def add_content(x:ContentIn):
 if x.channel not in ("youtube","tiktok","instagram","linkedin","other"): raise HTTPException(400,"Invalid channel.")
 ident=str(uuid.uuid4()); now=stamp()
 with db() as c: c.execute("INSERT INTO content_items VALUES(?,?,?,?,?,?,?,?,?)",(ident,x.title,x.channel,x.format,"draft",x.script,x.caption,now,now))
 return one("SELECT * FROM content_items WHERE id=?",(ident,))
@app.patch("/api/v1/content/{ident}/status")
def content_status(ident:str,status:str):
 if status not in ("draft","review","approved","archived"): raise HTTPException(400,"Invalid content status.")
 with db() as c:
  cur=c.execute("UPDATE content_items SET status=?,updated=? WHERE id=?",(status,stamp(),ident))
  if not cur.rowcount: raise HTTPException(404,"Content item not found.")
 return one("SELECT * FROM content_items WHERE id=?",(ident,))
@app.post("/api/v1/content/{ident}/generate")
async def generate_content(ident:str):
 item=one("SELECT * FROM content_items WHERE id=?",(ident,))
 if not item: raise HTTPException(404,"Content item not found.")
 result=await ask("content",f"Create a production-ready {item['format']} for {item['channel']}. Include a strong opening hook, scene-by-scene plan, spoken script, caption and clear call to action. Title: {item['title']}. Avoid fabricated trend statistics and copyrighted imitation.")
 with db() as c: c.execute("UPDATE content_items SET script=?,updated=? WHERE id=?",(result,stamp(),ident))
 return one("SELECT * FROM content_items WHERE id=?",(ident,))
# --- Automation plans are stored but never executed without future connector + approval work ---
@app.get("/api/v1/automations")
def get_workflows(): return rows("SELECT * FROM workflows ORDER BY updated DESC LIMIT 500")
@app.post("/api/v1/automations")
def add_workflow(x:WorkflowIn):
 ident=str(uuid.uuid4()); now=stamp()
 with db() as c: c.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?)",(ident,x.name,x.trigger_name,x.action_plan,"draft",now,now))
 return one("SELECT * FROM workflows WHERE id=?",(ident,))
@app.patch("/api/v1/automations/{ident}/status")
def workflow_status(ident:str,status:str):
 if status not in ("draft","awaiting_approval","paused"): raise HTTPException(400,"Only draft, awaiting_approval or paused are supported. No workflow runner is enabled.")
 with db() as c:
  cur=c.execute("UPDATE workflows SET status=?,updated=? WHERE id=?",(status,stamp(),ident))
  if not cur.rowcount: raise HTTPException(404,"Workflow not found.")
 return one("SELECT * FROM workflows WHERE id=?",(ident,))
# --- Omonux market data and signal research (closed candles; no execution) ---
@app.get("/api/v1/trading/market/{symbol}")
async def omonux_market(symbol: str, interval: str = "30m", limit: int = 120):
 try:
  candles_data=await fetch_candles(symbol,interval,limit)
  if len(candles_data)<30: raise HTTPException(422,"The exchange returned too few closed candles.")
  return {"symbol":symbol.upper(),"interval":interval,"candles":candles_data,"count":len(candles_data),"source":"Binance public market data","notice":"The forming candle is excluded. Market data can be delayed or unavailable."}
 except ValueError as e: raise HTTPException(400,str(e))
 except httpx.HTTPStatusError as e: raise HTTPException(502,f"Market data provider returned HTTP {e.response.status_code}.")
 except httpx.RequestError: raise HTTPException(502,"Could not reach Binance market data. Try again shortly.")

@app.get("/api/v1/trading/signals")
async def omonux_signals(symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT", interval: str = "30m"):
 results=[]
 requested=[item.strip() for item in symbols.split(",") if item.strip()][:10]
 if not requested: raise HTTPException(400,"Provide at least one market symbol.")
 for symbol in requested:
  try:
   candles_data=await fetch_candles(symbol,interval,120)
   results.append(build_signal(symbol.upper(),candles_data))
  except ValueError as e: raise HTTPException(400,str(e))
  except httpx.HTTPStatusError as e:
   results.append({"symbol":symbol.upper(),"status":"unavailable","error":f"Market provider HTTP {e.response.status_code}"})
  except httpx.RequestError:
   results.append({"symbol":symbol.upper(),"status":"unavailable","error":"Market data provider unavailable"})
 return {"signals":results,"mode":"research_only","source":"Binance public closed candles","disclaimer":"Signals are deterministic technical research, not financial advice. They do not place orders and do not guarantee results."}

# --- Omonux Trading research watchlist; no live prices, broker connection or live execution ---
@app.get("/api/v1/trading/watchlist")
def get_watchlist(): return rows("SELECT * FROM watchlist ORDER BY created DESC")
@app.post("/api/v1/trading/watchlist")
def add_watch(x:WatchItem):
 ident=str(uuid.uuid4())
 try:
  with db() as c: c.execute("INSERT INTO watchlist VALUES(?,?,?,?)",(ident,x.symbol.upper(),x.note,stamp()))
 except sqlite3.IntegrityError: raise HTTPException(409,"Symbol is already on the watchlist.")
 return one("SELECT * FROM watchlist WHERE id=?",(ident,))
@app.delete("/api/v1/trading/watchlist/{ident}")
def delete_watch(ident:str):
 with db() as c:
  cur=c.execute("DELETE FROM watchlist WHERE id=?",(ident,))
  if not cur.rowcount: raise HTTPException(404,"Watchlist item not found.")
 return {"deleted":True}
@app.get("/api/v1/analytics/summary")
def analytics():
 return {"tasks_total":one("SELECT COUNT(*) AS n FROM tasks")["n"],"tasks_completed":one("SELECT COUNT(*) AS n FROM tasks WHERE status='completed'")["n"],"leads_total":one("SELECT COUNT(*) AS n FROM leads")["n"],"tickets_open":one("SELECT COUNT(*) AS n FROM tickets WHERE status IN ('open','pending','escalated')")["n"],"content_drafts":one("SELECT COUNT(*) AS n FROM content_items WHERE status='draft'")["n"],"paper_trades":one("SELECT COUNT(*) AS n FROM paper_trades")["n"]}

# --- Research-grade paper trading utilities: user-supplied close prices only ---
def calculate_positions():
 trades=rows("SELECT * FROM paper_trades ORDER BY created ASC")
 positions={}
 realized=0.0
 for trade in trades:
  sym=trade["symbol"]; side=trade["side"]; qty=float(trade["qty"]); price=float(trade["price"])
  pos=positions.setdefault(sym,{"symbol":sym,"quantity":0.0,"cost_basis":0.0,"realized_pnl":0.0})
  if side=="buy":
   pos["quantity"]+=qty; pos["cost_basis"]+=qty*price
  else:
   avg=pos["cost_basis"]/pos["quantity"] if pos["quantity"] else 0.0
   pnl=(price-avg)*qty
   pos["realized_pnl"]+=pnl; realized+=pnl
   pos["quantity"]-=qty; pos["cost_basis"]-=avg*qty
  if abs(pos["quantity"])<1e-10: pos["quantity"]=0.0; pos["cost_basis"]=0.0
 return [dict(p,average_entry=(p["cost_basis"]/p["quantity"] if p["quantity"] else 0.0)) for p in positions.values() if p["quantity"]>0],realized
@app.get("/api/v1/trading/paper/portfolio")
async def paper_portfolio():
 positions,realized=calculate_positions()
 unrealized_total=0.0
 all_marked=True
 for position in positions:
  try:
   candles=await fetch_candles(position["symbol"],"30m",60)
   mark=float(candles[-1]["close"])
   unrealized=(mark-position["average_entry"])*position["quantity"]
   position["mark_price"]=mark
   position["unrealized_pnl"]=round(unrealized,2)
   position["total_pnl"]=round(position["realized_pnl"]+unrealized,2)
   unrealized_total+=unrealized
  except Exception:
   # Keep the holding visible, but never invent a mark or report a partial
   # portfolio total as if it covered every open position.
   position["mark_price"]=None
   position["unrealized_pnl"]=None
   position["total_pnl"]=None
   all_marked=False
 return {"mode":"paper_only","positions":positions,"realized_pnl":round(realized,2),"unrealized_pnl":round(unrealized_total,2) if all_marked else None,"total_pnl":round(realized+unrealized_total,2) if all_marked else None,"open_positions":len(positions),"mark_to_market_complete":all_marked,"notice":"Unrealized P&L uses the latest available completed 30-minute candle. Totals are withheld if any open position cannot be priced."}
@app.post("/api/v1/trading/backtests")
def run_backtest(x:BacktestIn):
 if x.fast_window>=x.slow_window: raise HTTPException(400,"Fast window must be smaller than slow window.")
 if any(v<=0 for v in x.closes): raise HTTPException(400,"All close prices must be positive numbers.")
 cash=float(x.initial_cash); units=0.0; peak=cash; max_dd=0.0; trades_count=0; equity=[]
 fee=x.fee_bps/10000; slip=x.slippage_bps/10000
 prev_signal=0
 for i,close in enumerate(x.closes):
  if i+1<x.slow_window:
   equity.append(cash+units*close); continue
  fast=sum(x.closes[i-x.fast_window+1:i+1])/x.fast_window
  slow=sum(x.closes[i-x.slow_window+1:i+1])/x.slow_window
  signal=1 if fast>slow else 0
  if signal==1 and prev_signal==0 and units==0:
   fill=close*(1+slip); units=cash/(fill*(1+fee)); cash=0.0; trades_count+=1
  elif signal==0 and prev_signal==1 and units>0:
   fill=close*(1-slip); cash=units*fill*(1-fee); units=0.0; trades_count+=1
  prev_signal=signal
  value=cash+units*close; equity.append(value); peak=max(peak,value)
  if peak>0: max_dd=max(max_dd,(peak-value)/peak)
 final=cash+units*x.closes[-1]
 buy_hold=x.initial_cash*(x.closes[-1]/x.closes[0])
 report={"strategy":"Long-only simple moving-average crossover","data_points":len(x.closes),"assumptions":"User-supplied closing prices; fee and slippage applied on simulated fills; no dividends, taxes, funding, borrow or market impact.","buy_and_hold_equity":round(buy_hold,2),"strategy_equity":round(final,2),"cash":round(cash,2),"open_units":round(units,8),"equity_curve":[round(v,2) for v in equity[-250:]]}
 ident=str(uuid.uuid4()); ret=(final/x.initial_cash-1)*100
 with db() as conn: conn.execute("INSERT INTO backtests VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ident,x.symbol.upper(),x.fast_window,x.slow_window,x.initial_cash,final,ret,max_dd*100,trades_count,stamp(),str(report)))
 return {"id":ident,"symbol":x.symbol.upper(),"return_pct":round(ret,2),"max_drawdown_pct":round(max_dd*100,2),"trade_count":trades_count,"report":report,"warning":"Historical simulation on supplied prices only. Not a prediction, recommendation or guarantee."}
@app.get("/api/v1/trading/backtests")
def list_backtests():
 return rows("SELECT id,symbol,fast_window,slow_window,initial_cash,final_equity,return_pct,max_drawdown_pct,trade_count,created FROM backtests ORDER BY created DESC LIMIT 100")

@app.post("/api/v1/trading/analysis")
async def trading_analysis(x:TradingAnalysisIn):
 prompt=("Provide an educational, risk-first market scenario analysis using ONLY the market information supplied below. "
 "Do not invent live prices, news, indicators or events. Do not tell the user to buy, sell or use leverage. "
 "Separate observed inputs from assumptions. Explain bullish, bearish and neutral scenarios, invalidation conditions, "
 "missing data, and risk-management questions. State clearly that this is not personalized financial advice.\n"
 f"Symbol: {x.symbol.upper()}\nTimeframe: {x.timeframe}\nUser-supplied market context:\n{x.market_context}")
 result=await ask("research",prompt)
 return {"symbol":x.symbol.upper(),"timeframe":x.timeframe,"analysis":result,"data_source":"user_supplied_context","disclaimer":"Educational scenario analysis only. Not a trading signal, personalized financial advice or a guarantee."}


# --- Private single-owner authentication and browser session protection ---
import base64, hashlib, hmac, secrets, time
from collections import defaultdict, deque
from fastapi import Request, Response
from fastapi.responses import JSONResponse

SESSION_COOKIE = "agentforge_session"
CSRF_COOKIE = "agentforge_csrf"
LOGIN_ATTEMPTS = defaultdict(deque)

class LoginInput(BaseModel):
 username: str = Field(min_length=1, max_length=80)
 password: str = Field(min_length=1, max_length=1024)

def auth_config():
 secret=os.getenv("SESSION_SECRET","")
 password=os.getenv("ADMIN_PASSWORD","")
 salt=os.getenv("ADMIN_PASSWORD_SALT","")
 if len(secret)<32 or len(password)<14 or len(salt)<16 or any(v.startswith("REPLACE_") for v in (secret,password,salt)):
  return None
 return secret.encode(),password,salt.encode()

def make_session(secret:bytes):
 expiry=int(time.time())+60*60*8
 payload=f"owner:{expiry}"
 signature=hmac.new(secret,payload.encode(),hashlib.sha256).digest()
 return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")+"."+base64.urlsafe_b64encode(signature).decode().rstrip("=")

def valid_session(token:str|None,secret:bytes):
 if not token or "." not in token: return False
 try:
  p,s=token.split(".",1)
  payload=base64.urlsafe_b64decode(p+"="*((4-len(p)%4)%4)).decode()
  signature=base64.urlsafe_b64decode(s+"="*((4-len(s)%4)%4))
  expected=hmac.new(secret,payload.encode(),hashlib.sha256).digest()
  who,expiry=payload.split(":",1)
  return who=="owner" and int(expiry)>int(time.time()) and hmac.compare_digest(signature,expected)
 except Exception: return False

def cookie_secure(): return os.getenv("COOKIE_SECURE","true").lower()=="true"

@app.post("/api/v1/auth/login")
def auth_login(data:LoginInput,request:Request,response:Response):
 cfg=auth_config()
 if not cfg: raise HTTPException(503,"Authentication is not configured. Set SESSION_SECRET, ADMIN_PASSWORD and ADMIN_PASSWORD_SALT.")
 secret,password,salt=cfg
 ip=request.client.host if request.client else "unknown"
 now=time.time(); attempts=LOGIN_ATTEMPTS[ip]
 while attempts and now-attempts[0]>900: attempts.popleft()
 if len(attempts)>=5: raise HTTPException(429,"Too many sign-in attempts. Try again in 15 minutes.")
 attempts.append(now)
 candidate=hashlib.pbkdf2_hmac("sha256",data.password.encode(),salt,310000)
 expected=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000)
 if data.username!="owner" or not hmac.compare_digest(candidate,expected):
  raise HTTPException(401,"The username or password is incorrect.")
 attempts.clear()
 csrf=secrets.token_urlsafe(32)
 response.set_cookie(SESSION_COOKIE,make_session(secret),httponly=True,secure=cookie_secure(),samesite="strict",max_age=28800,path="/")
 response.set_cookie(CSRF_COOKIE,csrf,httponly=False,secure=cookie_secure(),samesite="strict",max_age=28800,path="/")
 return {"authenticated":True,"username":"owner","csrf_token":csrf,"expires_in":28800}

@app.post("/api/v1/auth/logout")
def auth_logout(response:Response):
 response.delete_cookie(SESSION_COOKIE,path="/",secure=cookie_secure(),httponly=True,samesite="strict")
 response.delete_cookie(CSRF_COOKIE,path="/",secure=cookie_secure(),samesite="strict")
 return {"authenticated":False}

@app.get("/api/v1/auth/me")
def auth_me(request:Request):
 cfg=auth_config()
 if not cfg or not valid_session(request.cookies.get(SESSION_COOKIE),cfg[0]):
  raise HTTPException(401,"Sign in required.")
 return {"authenticated":True,"username":"owner"}

@app.middleware("http")
async def require_private_workspace(request:Request,call_next):
 path=request.url.path
 if path=="/health" or path=="/api/v1/auth/login" or path=="/api/v1/auth/me":
  return await call_next(request)
 cfg=auth_config()
 if not cfg:
  return JSONResponse(status_code=503,content={"detail":"Private workspace authentication is not configured."})
 secret=cfg[0]
 if not valid_session(request.cookies.get(SESSION_COOKIE),secret):
  return JSONResponse(status_code=401,content={"detail":"Sign in required."})
 if request.method not in ("GET","HEAD","OPTIONS"):
  cookie=request.cookies.get(CSRF_COOKIE,"")
  header=request.headers.get("x-csrf-token","")
  if not cookie or not header or not hmac.compare_digest(cookie,header):
   return JSONResponse(status_code=403,content={"detail":"Security token missing or invalid. Refresh the page and try again."})
 return await call_next(request)


# --- OMONUX automatic paper-trading engine: persistent settings, risk gates and audit ---
class AutoTradeConfig(BaseModel):
 mode:str="paper"
 risk_percent:float=Field(default=1,ge=0.1,le=5)
 min_confidence:int=Field(default=60,ge=1,le=100)
 max_open_positions:int=Field(default=3,ge=1,le=20)
 max_daily_loss_percent:float=Field(default=5,gt=0,le=100)
 cooldown_minutes:int=Field(default=15,ge=0,le=1440)
 max_trades_per_day:int=Field(default=10,ge=1,le=100)
 max_notional_percent:float=Field(default=25,gt=0,le=100)

def auto_settings():
 row=one("SELECT * FROM auto_trade_settings WHERE id=1")
 if not row:
  with db() as c: c.execute("INSERT OR IGNORE INTO auto_trade_settings(id,updated) VALUES(1,?)",(stamp(),))
  row=one("SELECT * FROM auto_trade_settings WHERE id=1")
 return row

def auto_event(kind,symbol=None,details=None,pnl=None):
 with db() as c:
  c.execute("INSERT INTO auto_trade_events VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),kind,symbol,details,pnl,stamp()))

async def auto_trade_scheduler():
 while True:
  try:
   if auto_settings()["running"]:
    await auto_trade_run_once()
  except Exception as exc:
   auto_event("SCHEDULER_ERROR",details=str(exc))
  await asyncio.sleep(60)

@app.get("/api/v1/trading/auto/status")
def auto_trade_status():
 settings=auto_settings()
 return {"running":bool(settings["running"]),"settings":{k:settings[k] for k in ("mode","risk_percent","min_confidence","max_open_positions","max_daily_loss_percent","cooldown_minutes","max_trades_per_day","max_notional_percent")},"open_positions":rows("SELECT * FROM auto_trade_positions ORDER BY opened DESC"),"mode_notice":"Paper trading only. No exchange orders are supported by this engine."}

@app.put("/api/v1/trading/auto/config")
def auto_trade_config(x:AutoTradeConfig):
 if x.mode!="paper":
  raise HTTPException(400,"Only paper mode is available. Live execution is not implemented.")
 with db() as c:
  c.execute("""UPDATE auto_trade_settings SET mode=?,risk_percent=?,min_confidence=?,max_open_positions=?,max_daily_loss_percent=?,cooldown_minutes=?,max_trades_per_day=?,max_notional_percent=?,updated=? WHERE id=1""",
   (x.mode,x.risk_percent,x.min_confidence,x.max_open_positions,x.max_daily_loss_percent,x.cooldown_minutes,x.max_trades_per_day,x.max_notional_percent,stamp()))
 return auto_trade_status()

@app.get("/api/v1/trading/safety/status")
def trading_safety_status():
 state=one("SELECT emergency_stopped,reason,updated FROM trading_safety_state WHERE id=1")
 if not state: return {"emergency_stopped":False,"reason":None,"updated":None}
 return {"emergency_stopped":bool(state["emergency_stopped"]),"reason":state["reason"],"updated":state["updated"],"scope":"paper automatic trading engine only"}

class SafetyStopRequest(BaseModel):
 reason:str=Field(default="Operator emergency stop",min_length=3,max_length=240)

class SafetyResetRequest(BaseModel):
 confirmation:str

@app.post("/api/v1/trading/safety/emergency-stop")
def trading_emergency_stop(x:SafetyStopRequest):
 with db() as c:
  c.execute("UPDATE trading_safety_state SET emergency_stopped=1,reason=?,updated=? WHERE id=1",(x.reason,stamp()))
  c.execute("UPDATE auto_trade_settings SET running=0,updated=? WHERE id=1",(stamp(),))
 auto_event("EMERGENCY_STOP",details=x.reason)
 return trading_safety_status()

@app.post("/api/v1/trading/safety/reset")
def trading_safety_reset(x:SafetyResetRequest):
 if x.confirmation!="RESET TRADING SAFETY":
  raise HTTPException(400,'Type exactly "RESET TRADING SAFETY" to clear the stop latch.')
 with db() as c:
  c.execute("UPDATE trading_safety_state SET emergency_stopped=0,reason=NULL,updated=? WHERE id=1",(stamp(),))
 auto_event("SAFETY_RESET",details="Operator manually cleared emergency stop; engine remains stopped")
 return trading_safety_status()

@app.post("/api/v1/trading/auto/start")
def auto_trade_start():
 if trading_safety_status()["emergency_stopped"]:
  raise HTTPException(423,"Emergency stop is active. Review the incident and manually reset trading safety before restarting.")
 with db() as c: c.execute("UPDATE auto_trade_settings SET running=1,updated=? WHERE id=1",(stamp(),))
 auto_event("ENGINE_STARTED",details="Paper trading engine started")
 return auto_trade_status()

@app.post("/api/v1/trading/auto/stop")
def auto_trade_stop():
 with db() as c: c.execute("UPDATE auto_trade_settings SET running=0,updated=? WHERE id=1",(stamp(),))
 auto_event("ENGINE_STOPPED",details="Paper trading engine stopped")
 return auto_trade_status()

@app.get("/api/v1/trading/auto/events")
def auto_trade_events():
 return rows("SELECT * FROM auto_trade_events ORDER BY created DESC LIMIT 300")

@app.post("/api/v1/trading/auto/run-once")
async def auto_trade_run_once():
 if trading_safety_status()["emergency_stopped"]:
  raise HTTPException(423,"Emergency stop is active. No trading cycle can run until an operator manually resets safety.")
 settings=auto_settings()
 if not settings["running"]:
  raise HTTPException(409,"Start the paper trading engine before running a cycle.")
 today=datetime.now(timezone.utc).date().isoformat()
 day_events=rows("SELECT * FROM auto_trade_events WHERE created LIKE ?",(today+"%",))
 entries_today=sum(1 for e in day_events if e["event_type"]=="PAPER_ENTRY")
 daily_pnl=sum(float(e["pnl"] or 0) for e in day_events if e["event_type"]=="PAPER_EXIT")
 equity=10000.0
 # Include current mark-to-market losses on every open paper position. If a quote
 # cannot be obtained, fail closed: do not open new positions using incomplete risk data.
 unrealized_pnl=0.0
 for held in rows("SELECT * FROM auto_trade_positions"):
  try:
   mark_candles=await fetch_candles(held["symbol"],"30m",60)
   mark_price=float(mark_candles[-1]["close"])
   unrealized_pnl+=(mark_price-float(held["entry_price"]))*float(held["quantity"])
  except (ValueError,httpx.HTTPError,IndexError,KeyError) as exc:
   auto_event("RISK_CHECK_ERROR",held.get("symbol"),str(exc))
   raise HTTPException(503,"Risk check could not price every open paper position. No new trades will be opened until market data is available.")
 daily_total_pnl=daily_pnl+unrealized_pnl
 if daily_total_pnl <= -(equity*settings["max_daily_loss_percent"]/100):
  with db() as c: c.execute("UPDATE auto_trade_settings SET running=0,updated=? WHERE id=1",(stamp(),))
  auto_event("RISK_BLOCK",details=f"Daily loss limit reached including unrealized P&L ({daily_total_pnl:.2f})")
  raise HTTPException(409,"Daily loss limit reached including open-position losses. The engine has been stopped; review the audit log before restarting.")
 actions=[]
 # Manage existing positions first using latest closed candle prices.
 open_positions=rows("SELECT * FROM auto_trade_positions ORDER BY opened")
 for pos in open_positions:
  try:
   cs=await fetch_candles(pos["symbol"],"30m",60)
   price=float(cs[-1]["close"])
   exit_reason="STOP_LOSS" if price<=pos["stop_price"] else ("TAKE_PROFIT" if price>=pos["target_price"] else None)
   if exit_reason:
    pnl=(price-float(pos["entry_price"]))*float(pos["quantity"])
    with db() as c: c.execute("DELETE FROM auto_trade_positions WHERE id=?",(pos["id"],))
    auto_event("PAPER_EXIT",pos["symbol"],exit_reason,pnl)
    actions.append({"symbol":pos["symbol"],"action":"CLOSE","reason":exit_reason,"price":price,"pnl":round(pnl,2)})
  except (ValueError,httpx.HTTPError,IndexError) as e:
   auto_event("CYCLE_ERROR",pos["symbol"],str(e))
 open_positions=rows("SELECT * FROM auto_trade_positions")
 if len(open_positions)>=settings["max_open_positions"]:
  auto_event("RISK_BLOCK",details="Maximum open positions reached")
  return {"actions":actions,"blocked":"Maximum open positions reached","open_positions":len(open_positions)}
 if entries_today>=settings["max_trades_per_day"]:
  auto_event("RISK_BLOCK",details="Maximum trades per day reached")
  return {"actions":actions,"blocked":"Maximum trades per day reached"}
 last_exit=one("SELECT created FROM auto_trade_events WHERE event_type='PAPER_EXIT' ORDER BY created DESC LIMIT 1")
 if last_exit and settings["cooldown_minutes"]>0:
  elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(last_exit["created"])).total_seconds()/60
  if elapsed<settings["cooldown_minutes"]:
   return {"actions":actions,"blocked":"Cooldown active","cooldown_remaining_minutes":round(settings["cooldown_minutes"]-elapsed,1)}
 for symbol in ("BTCUSDT","ETHUSDT","SOLUSDT"):
  if len(open_positions)>=settings["max_open_positions"] or entries_today>=settings["max_trades_per_day"]: break
  if any(p["symbol"]==symbol for p in open_positions): continue
  try:
   cs=await fetch_candles(symbol,"30m",120)
   signal=build_signal(symbol,cs)
   if signal["side"]!="BUY" or signal["confidence"]<settings["min_confidence"]: continue
   price=float(signal["price"]); stop=float(signal["risk_levels"]["stop_reference"]); target=float(signal["risk_levels"]["target_reference"])
   risk_cash=equity*settings["risk_percent"]/100
   quantity=min(risk_cash/max(price-stop,1e-12),(equity*settings["max_notional_percent"]/100)/price)
   if quantity<=0 or not all(map(lambda v: v>0,(price,stop,target))) or stop>=price or target<=price: continue
   ident=str(uuid.uuid4())
   with db() as c:
    c.execute("INSERT INTO auto_trade_positions VALUES(?,?,?,?,?,?,?,?)",(ident,symbol,"BUY",quantity,price,stop,target,stamp()))
   auto_event("PAPER_ENTRY",symbol,f"confidence={signal['confidence']}; qty={quantity:.8f}; stop={stop}; target={target}")
   actions.append({"symbol":symbol,"action":"OPEN_PAPER","quantity":round(quantity,8),"entry":price,"stop":stop,"target":target,"confidence":signal["confidence"]})
   open_positions.append({"symbol":symbol}); entries_today+=1
  except (ValueError,httpx.HTTPError,IndexError) as e:
   auto_event("CYCLE_ERROR",symbol,str(e))
 with db() as c: c.execute("UPDATE auto_trade_settings SET updated=? WHERE id=1",(stamp(),))
 return {"actions":actions,"open_positions":len(rows("SELECT * FROM auto_trade_positions")),"daily_entries":entries_today,"daily_realized_pnl":round(daily_pnl,2),"unrealized_pnl_at_cycle_start":round(unrealized_pnl,2),"daily_total_pnl_at_cycle_start":round(daily_total_pnl,2),"mode":"paper_only","notice":"No real exchange order was placed."}

# OMONUX legacy chart-image analysis, protected by the workspace auth middleware above.
from .omonux_chart_analysis import router as omonux_chart_router
app.include_router(omonux_chart_router)
# Encrypted OMONUX exchange and Telegram integration settings.
from .omonux_integrations import router as omonux_integrations_router
app.include_router(omonux_integrations_router)
# Read-only exchange account checks are restricted to exchange testnets.
from .omonux_exchange_testnet import router as omonux_exchange_router
app.include_router(omonux_exchange_router)

# Read-only production account checks; no live order endpoints are exposed.
from .omonux_live_account import router as omonux_live_account_router
app.include_router(omonux_live_account_router)
