import os, sqlite3, uuid
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
 yield
app=FastAPI(title="AgentForge API",version="0.1.0",lifespan=life)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",")],allow_methods=["*"],allow_headers=["*"])
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
 tid=str(uuid.uuid4())
 with db() as c: c.execute("INSERT INTO paper_trades VALUES(?,?,?,?,?,?)",(tid,t.symbol.upper(),t.side,t.quantity,t.reference_price,stamp()))
 return {"id":tid,"symbol":t.symbol.upper(),"side":t.side,"quantity":t.quantity,"reference_price":t.reference_price,"status":"simulated","notice":"Simulation only. No real order was placed."}
