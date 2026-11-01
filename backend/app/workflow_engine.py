"""Approval-gated workflow runner with an allowlisted action set.

This deliberately does not execute arbitrary shell commands, SQL, URLs, payments,
trades, or unreviewed publishing actions.
"""
import json
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .main import db, stamp, ask, AGENTS
from .omonux_integrations import send_telegram_message

router=APIRouter(prefix="/api/v1/workflow-runs",tags=["Workflow Runs"])

class RunRequest(BaseModel):
 workflow_id:str=Field(min_length=1,max_length=80)
 input_text:str=Field(default="",max_length=10000)

class ApprovalRequest(BaseModel):
 confirmed:bool

def ensure_runs():
 with db() as c:
  c.execute("""CREATE TABLE IF NOT EXISTS workflow_runs(
   id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,status TEXT NOT NULL,
   input_text TEXT NOT NULL,actions_json TEXT NOT NULL,result_json TEXT,
   error TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,approved_at TEXT)""")
  c.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON workflow_runs(created)")

def parse_plan(raw):
 try: plan=json.loads(raw)
 except (TypeError,ValueError): raise HTTPException(400,"This workflow needs a structured JSON action plan before it can run.")
 if not isinstance(plan,list) or not 1<=len(plan)<=5:
  raise HTTPException(400,"Action plan must be a JSON array containing between 1 and 5 actions.")
 clean=[]
 for item in plan:
  if not isinstance(item,dict): raise HTTPException(400,"Each workflow action must be an object.")
  kind=item.get("type")
  if kind=="agent_task":
   agent=item.get("agent"); title=item.get("title"); prompt=item.get("prompt")
   if agent not in AGENTS or not isinstance(title,str) or not title.strip() or not isinstance(prompt,str) or not prompt.strip():
    raise HTTPException(400,"agent_task requires a supported agent, title and prompt.")
   clean.append({"type":kind,"agent":agent,"title":title[:120],"prompt":prompt[:8000]})
  elif kind=="content_draft":
   title=item.get("title"); script=item.get("script",""); channel=item.get("channel","youtube")
   if not isinstance(title,str) or not title.strip() or not isinstance(script,str):
    raise HTTPException(400,"content_draft requires a title and script.")
   if channel not in ("youtube","tiktok","instagram","linkedin"):
    raise HTTPException(400,"Unsupported content channel.")
   clean.append({"type":kind,"title":title[:180],"script":script[:12000],"channel":channel})
  elif kind=="telegram_message":
   message=item.get("message")
   if not isinstance(message,str) or not message.strip():
    raise HTTPException(400,"telegram_message requires message text.")
   clean.append({"type":kind,"message":message[:3000]})
  else:
   raise HTTPException(400,"Unsupported action type. Allowed: agent_task, content_draft, telegram_message.")
 return clean

def get_workflow(workflow_id):
 with db() as c:
  row=c.execute("SELECT * FROM workflows WHERE id=?",(workflow_id,)).fetchone()
 return dict(row) if row else None

@router.post("")
def create_workflow_run(req:RunRequest):
 ensure_runs()
 workflow=get_workflow(req.workflow_id)
 if not workflow: raise HTTPException(404,"Workflow not found.")
 actions=parse_plan(workflow["action_plan"])
 ident=str(uuid.uuid4()); now=stamp()
 with db() as c:
  c.execute("INSERT INTO workflow_runs(id,workflow_id,status,input_text,actions_json,created,updated) VALUES(?,?,?,?,?,?,?)",
   (ident,req.workflow_id,"awaiting_approval",req.input_text,json.dumps(actions),now,now))
 return {"id":ident,"workflow_id":req.workflow_id,"status":"awaiting_approval","actions":actions,
         "message":"Workflow run is queued for your approval. No action has executed yet."}

@router.get("")
def list_workflow_runs():
 ensure_runs()
 with db() as c:
  records=c.execute("SELECT * FROM workflow_runs ORDER BY created DESC LIMIT 100").fetchall()
 return [{**dict(r),"actions":json.loads(r["actions_json"]),"result":json.loads(r["result_json"]) if r["result_json"] else None} for r in records]

@router.post("/{run_id}/reject")
def reject_workflow_run(run_id:str,req:ApprovalRequest):
 if req.confirmed is not True: raise HTTPException(400,"Explicit rejection confirmation is required.")
 ensure_runs()
 with db() as c:
  changed=c.execute("UPDATE workflow_runs SET status='rejected',updated=? WHERE id=? AND status='awaiting_approval'",(stamp(),run_id))
 if changed.rowcount!=1: raise HTTPException(409,"Only a run awaiting approval can be rejected.")
 return {"id":run_id,"status":"rejected"}

@router.post("/{run_id}/approve")
async def approve_workflow_run(run_id:str,req:ApprovalRequest):
 if req.confirmed is not True: raise HTTPException(400,"Explicit approval is required.")
 ensure_runs()
 with db() as c: row=c.execute("SELECT * FROM workflow_runs WHERE id=?",(run_id,)).fetchone()
 if not row: raise HTTPException(404,"Workflow run not found.")
 if row["status"]!="awaiting_approval": raise HTTPException(409,"This workflow run is no longer awaiting approval.")
 actions=json.loads(row["actions_json"])
 with db() as c:
  changed=c.execute("UPDATE workflow_runs SET status='running',approved_at=?,updated=? WHERE id=? AND status='awaiting_approval'",(stamp(),stamp(),run_id))
 if changed.rowcount!=1: raise HTTPException(409,"Another request already approved this workflow run.")
 results=[]
 try:
  for action in actions:
   if action["type"]=="agent_task":
    prompt=action["prompt"]
    if row["input_text"]:
     prompt=prompt.replace("{{input}}",row["input_text"])
     if "{{input}}" not in action["prompt"]: prompt += "\n\nRun-specific input:\n"+row["input_text"]
    result=await ask(action["agent"],prompt)
    task_id=str(uuid.uuid4())
    with db() as c:
     c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)",(task_id,action["agent"],action["title"],prompt,"completed",result,None,stamp()))
    results.append({"type":"agent_task","task_id":task_id,"title":action["title"],"result":result})
   elif action["type"]=="content_draft":
    ident=str(uuid.uuid4()); now=stamp()
    with db() as c:
     c.execute("INSERT INTO content_items VALUES(?,?,?,?,?,?,?,?,?)",(ident,action["title"],action["channel"],"short_video","draft",action["script"],"",now,now))
    results.append({"type":"content_draft","content_id":ident,"title":action["title"],"status":"draft"})
   elif action["type"]=="telegram_message":
    message=action["message"].replace("{{input}}",row["input_text"])
    sent=await send_telegram_message(message)
    if not sent: raise RuntimeError("Telegram is not configured or the message could not be delivered.")
    results.append({"type":"telegram_message","sent":True})
  with db() as c:
   c.execute("UPDATE workflow_runs SET status='completed',result_json=?,updated=?,error=NULL WHERE id=? AND status='running'",(json.dumps(results),stamp(),run_id))
  return {"id":run_id,"status":"completed","results":results}
 except Exception as exc:
  detail=exc.detail if isinstance(exc,HTTPException) else str(exc)
  with db() as c:
   c.execute("UPDATE workflow_runs SET status='failed',error=?,updated=? WHERE id=? AND status='running'",(str(detail)[:1000],stamp(),run_id))
  if isinstance(exc,HTTPException): raise
  raise HTTPException(502,"Workflow execution failed. Review the run record for the safe error summary.")
