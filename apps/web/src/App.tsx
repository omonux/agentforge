import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowUpRight, BarChart3, Bot, BriefcaseBusiness, CheckCircle2,
  ChevronDown, CircleHelp, Clock3, Command, CreditCard, FileSearch, Film,
  LayoutDashboard, LifeBuoy, Menu, MessageCircle, Plus, Search, Send,
  Settings2, ShieldCheck, Sparkles, TrendingUp, Workflow, X, Zap
} from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
type Agent = { id: string; name: string; description: string };
type Task = { id: string; agent_type: string; title: string; status: string; result?: string; error?: string; created_at: string };
const nav = [
  { label: "Workspace", items: [{ id: "overview", label: "Overview", icon: LayoutDashboard }, { id: "agents", label: "AI Agents", icon: Bot }, { id: "workflows", label: "Automations", icon: Workflow }, { id: "research", label: "Research", icon: FileSearch }, { id: "content", label: "Content Studio", icon: Film }] },
  { label: "Business", items: [{ id: "support", label: "Customer Support", icon: LifeBuoy }, { id: "sales", label: "Sales Pipeline", icon: BriefcaseBusiness }, { id: "analytics", label: "Analytics", icon: BarChart3 }] },
  { label: "Omonux", items: [{ id: "trading", label: "Omonux Trading", icon: TrendingUp }] },
];
const agentCards = [
  { id: "support", name: "Customer Support", detail: "Answer questions, triage tickets and prepare escalations.", icon: MessageCircle, color: "violet" },
  { id: "sales", name: "Sales Assistant", detail: "Qualify prospects and draft personalized follow-ups.", icon: BriefcaseBusiness, color: "blue" },
  { id: "content", name: "Content Studio", detail: "Create research-backed scripts, captions and content plans.", icon: Film, color: "pink" },
  { id: "automation", name: "Workflow Builder", detail: "Turn repetitive work into reviewable automation plans.", icon: Workflow, color: "orange" },
  { id: "research", name: "Research Analyst", detail: "Analyze sources and turn information into clear reports.", icon: FileSearch, color: "green" },
];

export default function App() {
  const [page, setPage] = useState("overview");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [menuOpen, setMenuOpen] = useState(false);
  const [showTask, setShowTask] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState("research");
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  async function refresh() {
    try {
      const [health, agentRes, taskRes] = await Promise.all([
        fetch(API + "/health"), fetch(API + "/api/v1/agents"), fetch(API + "/api/v1/tasks")
      ]);
      if (!health.ok || !agentRes.ok || !taskRes.ok) throw new Error("API unavailable");
      const h = await health.json();
      setApiStatus("online");
      setAgents(await agentRes.json());
      setTasks(await taskRes.json());
      if (!h.ai_configured) setNotice("API is online. Add your AI provider credentials to enable live agent responses.");
    } catch {
      setApiStatus("offline");
      setNotice("Backend not connected. Start the FastAPI server to run tasks; the interface is in preview mode.");
    }
  }
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 12000); return () => window.clearInterval(timer); }, []);

  const completed = tasks.filter(t => t.status === "completed").length;
  const activeAgent = useMemo(() => agentCards.find(a => a.id === selectedAgent), [selectedAgent]);

  async function runTask(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !prompt.trim()) return;
    setBusy(true); setNotice("");
    try {
      const res = await fetch(API + "/api/v1/tasks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_type: selectedAgent, title, prompt })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Task could not be completed.");
      setNotice("Task completed and saved to your workspace.");
      setTitle(""); setPrompt(""); setShowTask(false); await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Could not reach the API.");
      await refresh();
    } finally { setBusy(false); }
  }

  const titleMap: Record<string, string> = { overview: "Overview", agents: "AI Agents", workflows: "Automations", research: "Research", content: "Content Studio", support: "Customer Support", sales: "Sales Pipeline", analytics: "Analytics", trading: "Omonux Trading" };
  const pageTitle = titleMap[page] || "Overview";

  return <div className="shell">
    <aside className={menuOpen ? "sidebar open" : "sidebar"}>
      <div className="brand"><div className="brand-mark"><Command size={19}/></div><div><strong>AgentForge</strong><span>by Omonux</span></div><button className="icon-btn mobile-close" onClick={() => setMenuOpen(false)}><X size={18}/></button></div>
      <button className="workspace-switch"><div className="workspace-avatar">O</div><div><b>Omonux Workspace</b><small>Free workspace</small></div><ChevronDown size={15}/></button>
      {nav.map(group => <div className="nav-group" key={group.label}><div className="nav-label">{group.label}</div>{group.items.map(item => { const Icon = item.icon; return <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => { setPage(item.id); setMenuOpen(false); }}><Icon size={17}/><span>{item.label}</span>{item.id === "trading" && <span className="soon">PAPER</span>}</button>; })}</div>)}
      <div className="sidebar-bottom"><div className="usage-card"><div className="usage-head"><span>Workspace usage</span><span>0 / 100</span></div><div className="usage-track"><i/></div><small>Free plan · Upgrade when ready</small></div><button className="nav-item"><Settings2 size={17}/>Settings</button><button className="nav-item"><CircleHelp size={17}/>Help centre</button><div className="profile"><div className="profile-avatar">O</div><div><b>Omonux Admin</b><small>Owner workspace</small></div><ChevronDown size={15}/></div></div>
    </aside>
    {menuOpen && <button className="scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)}/>}
    <main className="main">
      <header className="topbar"><div className="top-left"><button className="icon-btn menu-trigger" onClick={() => setMenuOpen(true)}><Menu size={19}/></button><span className="breadcrumb">Workspace</span><span className="crumb-slash">/</span><b>{pageTitle}</b></div><div className="top-actions"><div className={"connection " + apiStatus}><i/>{apiStatus === "online" ? "API connected" : apiStatus === "offline" ? "API offline" : "Connecting"}</div><button className="icon-btn"><Search size={18}/></button><button className="help-button"><CircleHelp size={16}/> Help</button><div className="top-avatar">O</div></div></header>
      <div className="content">
        <div className="welcome-row"><div><div className="eyebrow">SUNDAY, NOVEMBER 1, 2026</div><h1>{page === "overview" ? "Good evening, Omonux" : pageTitle}</h1><p>{page === "overview" ? "Your AI workforce, business operations and trading workspace in one place." : "Manage your work from one clear, secure workspace."}</p></div><button className="primary-btn" onClick={() => setShowTask(true)}><Plus size={17}/> Create a task</button></div>
        {notice && <div className="notice"><Activity size={16}/><span>{notice}</span><button onClick={() => setNotice("")}><X size={15}/></button></div>}
        {page === "overview" && <>
          <div className="stats-grid">
            <Stat icon={<Bot/>} label="AI agents" value={String(agents.length || 5)} foot="Available agent types" tone="purple"/>
            <Stat icon={<Zap/>} label="Tasks completed" value={String(completed)} foot="From saved task history" tone="green"/>
            <Stat icon={<Clock3/>} label="Tasks recorded" value={String(tasks.length)} foot="Last 100 workspace tasks" tone="blue"/>
            <Stat icon={<ShieldCheck/>} label="Trading mode" value="Paper only" foot="No live orders enabled" tone="orange"/>
          </div>
          <div className="section-heading"><div><h2>Your AI workforce</h2><p>Choose a specialist to get work moving.</p></div><button className="text-link" onClick={() => setPage("agents")}>View all agents <ArrowUpRight size={15}/></button></div>
          <div className="agent-grid">{agentCards.map(agent => <AgentCard key={agent.id} agent={agent} onClick={() => { setSelectedAgent(agent.id); setShowTask(true); }}/>)}</div>
          <div className="lower-grid"><section className="panel activity-panel"><div className="panel-head"><div><h3>Recent activity</h3><p>Your latest agent tasks</p></div><button className="text-link" onClick={() => setPage("analytics")}>View history <ArrowUpRight size={14}/></button></div>{tasks.length ? tasks.slice(0,5).map(task => <div className="activity-row" key={task.id}><div className="activity-icon"><Bot size={16}/></div><div className="activity-copy"><b>{task.title}</b><small>{task.agent_type} · {new Date(task.created_at).toLocaleString()}</small></div><span className={"status " + task.status}>{task.status}</span></div>) : <Empty icon={<Activity/>} title="No activity yet" text="Create your first task and its real execution history will appear here."/>}</section>
          <section className="panel quick-panel"><div className="panel-head"><div><h3>Quick start</h3><p>Useful things to try first</p></div><Sparkles size={18} className="muted-icon"/></div><button className="quick-link" onClick={() => { setSelectedAgent("research"); setShowTask(true); setTitle("Research a market opportunity"); setPrompt("Research a market opportunity using the sources I provide. Summarize customer needs, competitors, risks and next steps."); }}><span className="quick-emoji purple-bg"><FileSearch size={17}/></span><span><b>Research a market</b><small>Turn sources into a decision brief</small></span><ArrowUpRight size={15}/></button><button className="quick-link" onClick={() => { setSelectedAgent("content"); setShowTask(true); setTitle("Create a short-form video script"); setPrompt("Create a 30-second vertical video script with a strong hook, clear value, scene directions and a call to action. State any trend assumptions."); }}><span className="quick-emoji pink-bg"><Film size={17}/></span><span><b>Create content</b><small>Draft a short video concept</small></span><ArrowUpRight size={15}/></button><button className="quick-link" onClick={() => { setPage("trading"); }}><span className="quick-emoji green-bg"><TrendingUp size={17}/></span><span><b>Open Omonux Trading</b><small>Explore research and paper trading</small></span><ArrowUpRight size={15}/></button></section></div>
        </>}
        {page === "agents" && <><div className="section-heading"><div><h2>Specialist agents</h2><p>Each agent has a defined role and reports what it actually completed.</p></div></div><div className="agent-grid">{agentCards.map(agent => <AgentCard key={agent.id} agent={agent} onClick={() => { setSelectedAgent(agent.id); setShowTask(true); }}/>)}</div></>}
        {["support","sales","research","content","workflows"].includes(page) && <section className="feature-workspace panel"><div className="feature-icon"><Sparkles/></div><h2>{pageTitle}</h2><p>{page === "support" ? "Draft accurate customer replies, summarize tickets and flag cases that need a human." : page === "sales" ? "Organize prospect research and prepare personalized outreach for review before sending." : page === "content" ? "Create original video scripts, captions, hooks and publishing plans. Publishing integrations come later." : page === "workflows" ? "Design clear automation plans with review and approval before external actions." : "Turn supplied documents and sources into structured, evidence-aware reports."}</p><button className="primary-btn" onClick={() => { setSelectedAgent(page === "workflows" ? "automation" : page); setShowTask(true); }}><Plus size={16}/> Start {pageTitle.toLowerCase()} task</button><div className="guard-note"><ShieldCheck size={16}/> External messages, publishing and payments require explicit approval and connected services.</div></section>}
        {page === "analytics" && <section className="panel"><div className="panel-head"><div><h3>Task analytics</h3><p>Based on actual tasks saved in your workspace.</p></div></div><div className="analytics-summary"><Stat icon={<CheckCircle2/>} label="Completed" value={String(completed)} foot="Successfully returned results" tone="green"/><Stat icon={<Clock3/>} label="Total" value={String(tasks.length)} foot="Saved tasks" tone="blue"/></div>{tasks.length ? tasks.map(task => <div className="activity-row" key={task.id}><div className="activity-icon"><Bot size={16}/></div><div className="activity-copy"><b>{task.title}</b><small>{task.agent_type} · {new Date(task.created_at).toLocaleString()}</small>{task.error && <small className="error-text">{task.error}</small>}</div><span className={"status " + task.status}>{task.status}</span></div>) : <Empty icon={<BarChart3/>} title="No task data yet" text="Run an agent task to start building your activity history."/>}</section>}
        {page === "trading" && <TradingPanel api={API}/>}
      </div>
      <footer className="footer"><span>© 2026 AgentForge by Omonux</span><span><ShieldCheck size={13}/> Built with transparent execution and human approval</span></footer>
    </main>
    {showTask && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setShowTask(false); }}><form className="task-modal" onSubmit={runTask}><div className="modal-top"><div><div className="eyebrow">NEW WORKSPACE TASK</div><h2>Give your agent a job</h2></div><button type="button" className="icon-btn" onClick={() => setShowTask(false)}><X size={18}/></button></div><label>Choose an agent<select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)}>{agentCards.map(a => <option value={a.id} key={a.id}>{a.name}</option>)}</select></label><label>Task name<input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Prepare a competitor research brief" required minLength={2}/></label><label>Instructions<textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Describe what you need. Include relevant context, files or source URLs..." rows={6} required minLength={3}/></label><div className="modal-hint"><ShieldCheck size={15}/> Your task is saved. External actions are not performed automatically.</div><div className="modal-actions"><button type="button" className="secondary-btn" onClick={() => setShowTask(false)}>Cancel</button><button className="primary-btn" disabled={busy}>{busy ? "Working..." : <><Send size={15}/> Run task</>}</button></div></form></div>}
  </div>;
}

function Stat({ icon, label, value, foot, tone }: { icon: React.ReactNode; label: string; value: string; foot: string; tone: string }) {
  return <div className="stat-card"><div className={"stat-icon " + tone}>{icon}</div><div className="stat-label">{label}</div><strong>{value}</strong><small>{foot}</small></div>;
}
function AgentCard({ agent, onClick }: { agent: typeof agentCards[number]; onClick: () => void }) {
  const Icon = agent.icon;
  return <button className="agent-card" onClick={onClick}><div className={"agent-card-icon " + agent.color}><Icon size={20}/></div><div className="agent-card-title"><h3>{agent.name}</h3><ArrowUpRight size={16}/></div><p>{agent.detail}</p><span className="agent-card-action">Create task <Plus size={14}/></span></button>;
}
function Empty({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="empty-state"><div>{icon}</div><b>{title}</b><p>{text}</p></div>;
}
function TradingPanel({ api }: { api: string }) {
  const [status, setStatus] = useState<any>(null);
  const [symbol, setSymbol] = useState("BTCUSD");
  const [side, setSide] = useState("buy");
  const [quantity, setQuantity] = useState("0.01");
  const [price, setPrice] = useState("60000");
  const [message, setMessage] = useState("");
  useEffect(() => { fetch(api + "/api/v1/trading").then(r => r.json()).then(setStatus).catch(() => setStatus(null)); }, [api]);
  async function simulate(e: React.FormEvent) {
    e.preventDefault(); setMessage("");
    try {
      const r = await fetch(api + "/api/v1/trading/paper/trades", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol, side, quantity: Number(quantity), reference_price: Number(price) }) });
      const data = await r.json(); if (!r.ok) throw new Error(data.detail || "Could not save simulation.");
      setMessage("Paper trade recorded. No real order was placed.");
    } catch (err) { setMessage(err instanceof Error ? err.message : "Trading API is unavailable."); }
  }
  return <><div className="trading-banner"><div className="trading-symbol"><TrendingUp size={23}/></div><div><div className="eyebrow">OMONUX FINANCIAL TECHNOLOGY</div><h2>Omonux Trading</h2><p>Market research, watchlists and risk-aware trading experiments.</p></div><span className="paper-pill">PAPER MODE ONLY</span></div><div className="notice warning"><ShieldCheck size={16}/><span>Simulation only. This module does not connect to a broker, provide investment advice, or place live orders.</span></div><div className="trading-grid"><section className="panel"><div className="panel-head"><div><h3>Paper trade simulator</h3><p>Use a reference price you supply to test your process.</p></div></div><form className="trade-form" onSubmit={simulate}><label>Asset symbol<input value={symbol} onChange={e => setSymbol(e.target.value)} required/></label><div className="trade-fields"><label>Side<select value={side} onChange={e => setSide(e.target.value)}><option value="buy">Buy</option><option value="sell">Sell</option></select></label><label>Quantity<input type="number" min="0.000001" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} required/></label></div><label>Simulated reference price<input type="number" min="0.000001" step="any" value={price} onChange={e => setPrice(e.target.value)} required/></label><button className="primary-btn"><TrendingUp size={15}/> Record paper trade</button>{message && <p className="trade-message">{message}</p>}</form></section><section className="panel"><div className="panel-head"><div><h3>Trading roadmap</h3><p>Build safely, one layer at a time.</p></div></div>{["Market data and asset watchlists","Backtesting with historical data","Risk limits and drawdown controls","Paper portfolio and performance reports","Broker integrations after compliance review"].map((x,i)=><div className="roadmap-row" key={x}><span>{i+1}</span><b>{x}</b><small>{i===0?"NEXT":"PLANNED"}</small></div>)}</section></div></>;
}
