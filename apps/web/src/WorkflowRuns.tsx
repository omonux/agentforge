import { useCallback, useEffect, useState } from "react";
import { apiFetch, API } from "./api";
import { CheckCircle2, CircleAlert, Clock3, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

type Workflow = { id: string; name: string; trigger_name: string; action_plan: string; status: string };
type Run = { id: string; workflow_id: string; status: string; input_text: string; actions: any[]; result: any[] | null; error?: string; created: string };
export default function WorkflowRuns({ onNotice }: { onNotice: (message: string) => void }) {
  const [workflows,setWorkflows]=useState<Workflow[]>([]);
  const [runs,setRuns]=useState<Run[]>([]);
  const [inputs,setInputs]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");

  const load=useCallback(async()=>{
    setError("");
    try {
      const [w,r]=await Promise.all([apiFetch(API+"/api/v1/automations"),apiFetch(API+"/api/v1/workflow-runs")]);
      const wd=await w.json(); const rd=await r.json();
      if(!w.ok) throw new Error(wd.detail||"Could not load workflows.");
      if(!r.ok) throw new Error(rd.detail||"Could not load workflow runs.");
      setWorkflows(wd); setRuns(rd);
    } catch(e) { setError(e instanceof Error?e.message:"Could not load workflow runs."); }
  },[]);
  useEffect(()=>{void load()},[load]);

  async function start(workflow:Workflow){
    setBusy("start:"+workflow.id);setError("");
    try {
      const response=await apiFetch(API+"/api/v1/workflow-runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({workflow_id:workflow.id,input_text:inputs[workflow.id]||""})});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"Could not queue workflow.");
      onNotice("Workflow queued. Review and approve it before any action runs.");await load();
    } catch(e){setError(e instanceof Error?e.message:"Could not queue workflow.");}
    finally{setBusy("")}
  }

  async function decide(run:Run,approve:boolean){
    setBusy((approve?"approve:":"reject:")+run.id);setError("");
    try{
      const response=await apiFetch(API+"/api/v1/workflow-runs/"+run.id+(approve?"/approve":"/reject"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmed:true})});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"Workflow action failed.");
      onNotice(approve?"Approved workflow finished with status: "+data.status:"Workflow run rejected.");await load();
    }catch(e){setError(e instanceof Error?e.message:"Workflow action failed.");await load()}
    finally{setBusy("")}
  }

  return <section className="panel workflow-runner">
    <div className="workflow-runner-head"><div><span className="eyebrow">APPROVAL-GATED EXECUTION</span><h3>Workflow runs</h3><p>Only structured, allowlisted actions can run. Every run waits for your approval.</p></div><button className="secondary" onClick={()=>void load()}><RefreshCw size={14}/> Refresh</button></div>
    {error&&<div className="workflow-error"><CircleAlert size={14}/>{error}</div>}
    <div className="workflow-run-list">
      {workflows.length===0?<div className="empty"><Clock3/><b>No saved workflows</b><small>Create a workflow above, then return here to run it.</small></div>:workflows.map(workflow=><article className="workflow-run-card" key={workflow.id}>
        <div><b>{workflow.name}</b><small>{workflow.trigger_name}</small><p>{workflow.action_plan}</p></div>
        <label>Run-specific input (optional)<textarea rows={2} value={inputs[workflow.id]||""} onChange={e=>setInputs(old=>({...old,[workflow.id]:e.target.value}))} placeholder="Add the information this run should use…"/></label>
        <button className="primary" onClick={()=>void start(workflow)} disabled={!!busy}><Play size={14}/>{busy==="start:"+workflow.id?"Queueing…":"Queue for approval"}</button>
      </article>)}
    </div>
    <div className="workflow-runner-head workflow-history-head"><div><span className="eyebrow">AUDIT TRAIL</span><h3>Recent runs</h3></div><span>{runs.length} records</span></div>
    {runs.length===0?<p className="workflow-empty-note">No workflow runs yet.</p>:runs.map(run=><article className="workflow-history" key={run.id}>
      <div className="workflow-history-title"><span className={"workflow-status "+run.status}>{run.status.replace(/_/g," ")}</span><small>{new Date(run.created).toLocaleString()}</small></div>
      <small>{workflows.find(w=>w.id===run.workflow_id)?.name||"Workflow"} · {run.actions.length} action(s)</small>
      {run.input_text&&<p>Input: {run.input_text}</p>}
      {run.error&&<p className="workflow-run-error">{run.error}</p>}
      {run.result&&<pre>{JSON.stringify(run.result,null,2)}</pre>}
      {run.status==="awaiting_approval"&&<div className="workflow-approval-actions"><button className="primary" onClick={()=>void decide(run,true)} disabled={!!busy}><CheckCircle2 size={14}/>{busy==="approve:"+run.id?"Running…":"Approve & execute"}</button><button className="secondary" onClick={()=>void decide(run,false)} disabled={!!busy}><XCircle size={14}/> Reject</button></div>}
    </article>)}
    <div className="guard"><ShieldCheck size={14}/> External actions are limited to the approved Telegram message action. Agent tasks and content drafts are internal. Payments, trades, arbitrary URLs, shell commands and automatic YouTube publishing are not executable workflow actions.</div>
  </section>;
}
