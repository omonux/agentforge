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
  c.execute("CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT,company TEXT,stage TEXT NOT NULL,notes TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY,customer TEXT NOT NULL,email TEXT,subject TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,reply_draft TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS content_items(id TEXT PRIMARY KEY,title TEXT NOT NULL,channel TEXT NOT NULL,format TEXT NOT NULL,status TEXT NOT NULL,script TEXT,caption TEXT,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,name TEXT NOT NULL,trigger_name TEXT NOT NULL,action_plan TEXT NOT NULL,status TEXT NOT NULL,created TEXT,updated TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS watchlist(id TEXT PRIMARY KEY,symbol TEXT NOT NULL UNIQUE,note TEXT,created TEXT)")
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
 with db() as c: c.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ident,x.customer,x.email,x.subject,x.message,"open",x.priority,None,now,now))
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
