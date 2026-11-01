import { useEffect, useState } from "react";
import { Activity, ArrowRight, Bot, CheckCircle2, CircleAlert, Command, Sparkles, Workflow } from "lucide-react";
import { apiFetch, API } from "./api";

type Props = {
  apiOnline: boolean;
  aiConfigured: boolean;
  totalTasks: number;
  completedTasks: number;
  onCreateTask: () => void;
  onNavigate: (page: string) => void;
};
type Department = { id: string; name: string; page: string; state: string; detail: string };

export default function OperationsPulse({
  apiOnline, aiConfigured, totalTasks, completedTasks, onCreateTask, onNavigate,
}: Props) {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [overviewError, setOverviewError] = useState("");

  useEffect(() => {
    let active = true;
    apiFetch(API + "/api/v1/workspace/overview")
      .then(async (response) => {
        if (!response.ok) throw new Error("Workspace status is temporarily unavailable.");
        return response.json();
      })
      .then((data) => { if (active) setDepartments(data.departments || []); })
      .catch((error) => {
        if (active) setOverviewError(error instanceof Error ? error.message : "Workspace status unavailable.");
      });
    return () => { active = false; };
  }, []);

  const readiness = [
    { label: "Backend service", detail: apiOnline ? "Health endpoint responding" : "Not reachable right now", ok: apiOnline },
    { label: "OpenAI credentials", detail: aiConfigured ? "A server-side key is configured" : "Add AI_API_KEY in your host settings", ok: aiConfigured },
    { label: "Task workspace", detail: totalTasks ? `${totalTasks} saved task${totalTasks === 1 ? "" : "s"}` : "Ready for your first task", ok: true },
  ];

  return (
    <>
      <section className="pulsegrid" aria-label="Operations command centre">
        <div className="pulsepanel pulsehero">
          <div className="pulseeyebrow"><Activity size={13} /> OPERATIONS PULSE</div>
          <h2>Your command centre.</h2>
          <p>See what is configured, launch work quickly, and keep every external action under your control.</p>
          <div className="pulsemetrics">
            <div><strong>{totalTasks}</strong><span>Saved tasks</span></div>
            <div><strong>{completedTasks}</strong><span>Completed</span></div>
            <div><strong>{totalTasks ? Math.round((completedTasks / totalTasks) * 100) : 0}%</strong><span>Completion rate</span></div>
          </div>
          <button className="primary" onClick={onCreateTask}><Sparkles size={15} /> Start a new task <ArrowRight size={14} /></button>
        </div>
        <div className="pulsepanel">
          <div className="pulsepanelhead"><div><span className="pulseeyebrow">SYSTEM READINESS</span><h3>Connection checks</h3></div><Command size={18} /></div>
          <div className="readinesslist">
            {readiness.map((item) => (
              <div className="readinessitem" key={item.label}>
                <span className={item.ok ? "readinessicon ok" : "readinessicon pending"}>{item.ok ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}</span>
                <span><b>{item.label}</b><small>{item.detail}</small></span>
                <em className={item.ok ? "ready" : "pending"}>{item.ok ? "OK" : "CHECK"}</em>
              </div>
            ))}
          </div>
          <p className="pulsehint">A configured key does not confirm a successful model request. Use “Connect AI” above to test it.</p>
        </div>
        <div className="pulsepanel pulseactions">
          <div className="pulsepanelhead"><div><span className="pulseeyebrow">QUICK LAUNCH</span><h3>What do you want to do?</h3></div><Sparkles size={18} /></div>
          <button onClick={onCreateTask}><span className="pulseactionicon"><Bot size={17} /></span><span><b>Run an AI agent</b><small>Research, support, sales or content</small></span><ArrowRight size={15} /></button>
          <button onClick={() => onNavigate("Automations")}><span className="pulseactionicon"><Workflow size={17} /></span><span><b>Build a workflow</b><small>Create a plan with human review</small></span><ArrowRight size={15} /></button>
          <button onClick={() => onNavigate("Analytics")}><span className="pulseactionicon"><Activity size={17} /></span><span><b>Review analytics</b><small>Inspect saved workspace activity</small></span><ArrowRight size={15} /></button>
        </div>
      </section>
      <section className="department-strip" aria-label="Connected workspace departments">
        <div className="department-strip-head">
          <div><span className="pulseeyebrow">ONE CONNECTED WORKSPACE</span><h3>All departments</h3></div>
          <span>{departments.length} areas</span>
        </div>
        {overviewError ? <p className="pulsehint">{overviewError}</p> : (
          <div className="department-grid">
            {departments.map((item) => (
              <button className="department-card" key={item.id} onClick={() => onNavigate(item.page)}>
                <span className={"department-state " + item.state}>{item.state.replace(/_/g, " ")}</span>
                <b>{item.name}</b>
                <small>{item.detail}</small>
                <span className="department-open">Open department →</span>
              </button>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
