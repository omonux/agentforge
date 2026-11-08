import { useCallback, useEffect, useState } from "react";
import { apiFetch, API } from "./api";
import { Activity, CheckCircle2, CircleAlert, KeyRound, Link2, LoaderCircle, LockKeyhole, RefreshCw, Save, Trash2, Unplug, Youtube } from "lucide-react";
import "./connect-api.css";

type Field = { name: string; label: string; kind: "secret" | "text"; required: boolean; help: string; configured: boolean };
type Service = { id: string; name: string; group: string; description: string; testable: boolean; configured: boolean; fields: Field[]; check?: { status: string; message: string; checked_at: string } | null };
type Props = { onNotice?: (message: string) => void };

export default function ConnectAPI({ onNotice }: Props) {
  const [services, setServices] = useState<Service[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [edited, setEdited] = useState<Record<string, boolean>>({});
  const defaults: Record<string, string> = { ai_base_url: "https://api.openai.com/v1", ai_model: "gpt-4.1-mini", image_base_url: "https://api.openai.com/v1", image_model: "gpt-image-1" };
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [testing, setTesting] = useState("");
  const [error, setError] = useState("");
  const [encryptionReady, setEncryptionReady] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await apiFetch(API + "/api/v1/connect-api");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load integrations.");
      setServices(data.services || []);
      setEncryptionReady(Boolean(data.encryption_ready));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load integrations.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const saveService = async (service: Service) => {
    const entries = service.fields.map(field => [field.name, (values[field.name] ?? (!field.configured ? defaults[field.name] : "") ?? "").trim()] as const).filter(([name, value]) => value.length > 0 && (edited[name] || !service.fields.find(f => f.name === name)?.configured));
    if (!entries.length) { setError("Enter at least one credential before saving."); return; }
    setSaving(service.id); setError("");
    try {
      for (const [name, value] of entries) {
        const response = await apiFetch(API + "/api/v1/connect-api/secrets", {
          method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Credential could not be saved.");
      }
      setValues(current => {
        const next = { ...current };
        entries.forEach(([name]) => { next[name] = ""; });
        return next;
      });
      setEdited(current => { const next = { ...current }; entries.forEach(([name]) => { delete next[name]; }); return next; });
      onNotice?.(service.name + " credentials encrypted and saved.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Credential could not be saved."); }
    finally { setSaving(""); }
  };

  const removeField = async (field: Field) => {
    if (!window.confirm("Remove the saved " + field.label + "?")) return;
    try {
      const response = await apiFetch(API + "/api/v1/connect-api/secrets/" + encodeURIComponent(field.name), { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Credential could not be removed.");
      onNotice?.(field.label + " removed.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Credential could not be removed."); }
  };

  const testService = async (service: Service) => {
    setTesting(service.id); setError("");
    try {
      const response = await apiFetch(API + "/api/v1/connect-api/test/" + service.id, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Connection test failed.");
      onNotice?.(data.message || service.name + " test completed.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Connection test failed."); await load(); }
    finally { setTesting(""); }
  };

  const connectYouTube = async () => {
    setTesting("youtube");
    try {
      const response = await apiFetch(API + "/api/v1/youtube/oauth/start");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "YouTube OAuth is not configured.");
      window.location.assign(data.authorization_url);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start YouTube connection."); setTesting(""); }
  };

  const total = services.length;
  const configured = services.filter(service => service.configured).length;

  return <div className="connect-api">
    <div className="connect-hero">
      <div className="connect-hero-icon"><KeyRound size={22}/></div>
      <div className="connect-hero-copy"><span>AGENTFORGE INTEGRATIONS</span><h2>Connect API</h2><p>Manage your provider credentials in one private place. Save each provider once, test its connection, and use it across the departments that support it.</p></div>
      <button className="connect-refresh" onClick={() => void load()} disabled={loading}><RefreshCw size={15}/> Refresh</button>
    </div>
    <div className="connect-summary">
      <div><b>{configured}/{total}</b><span>Services configured</span></div>
      <div><b>{services.reduce((n, s) => n + s.fields.filter(f => f.configured).length, 0)}</b><span>Credentials saved</span></div>
      <div className={encryptionReady ? "connect-encryption good" : "connect-encryption warn"}><LockKeyhole size={17}/><span>{encryptionReady ? "Encrypted storage ready" : "Encryption key required"}</span></div>
    </div>
    {!encryptionReady && <div className="connect-warning"><CircleAlert size={17}/><div><b>One-time security setup required</b><p>Set <code>SECRET_ENCRYPTION_KEY</code> in <code>backend/.env</code> (or your private hosting environment) before saving credentials. Generate it with <code>python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"</code>. Back it up securely. If it is lost, saved credentials cannot be decrypted.</p></div></div>}
    {error && <div className="connect-error"><CircleAlert size={15}/>{error}</div>}
    {loading ? <div className="connect-loading"><LoaderCircle size={18}/> Loading integrations…</div> : <div className="connect-groups">
      {services.map(service => <article className="connect-card" key={service.id}>
        <div className="connect-card-head">
          <div><span className="connect-group-label">{service.group}</span><h3>{service.name}</h3><p>{service.description}</p></div>
          <span className={"connect-state " + (service.check?.status === "connected" ? "connected" : service.configured ? "configured" : "missing")}>{service.check?.status === "connected" ? "Test passed" : service.check?.status === "manual" ? "Manual verification" : service.configured ? "Configured" : "Needs setup"}</span>
        </div>
        <div className="connect-fields">
          {service.fields.map(field => <div className="connect-field" key={field.name}>
            <label htmlFor={field.name}>{field.label}{field.required && <i>Required</i>}</label>
            <div className="connect-input-row">
              <input id={field.name} type={field.kind === "secret" ? "password" : "text"} autoComplete="off" value={values[field.name] ?? (!field.configured ? defaults[field.name] : "") ?? ""} onChange={e => { setValues(current => ({ ...current, [field.name]: e.target.value })); setEdited(current => ({ ...current, [field.name]: true })); }} placeholder={field.configured ? "Saved securely · enter a new value to replace" : field.help} />
              {field.configured && <button className="connect-icon-button" type="button" title="Remove saved credential" onClick={() => void removeField(field)}><Trash2 size={14}/></button>}
              {field.configured && <span className="connect-saved"><CheckCircle2 size={13}/> Saved</span>}
            </div>
            <small>{field.help}</small>
          </div>)}
        </div>
        <div className="connect-card-foot">
          <button className="connect-save" onClick={() => void saveService(service)} disabled={saving === service.id || !encryptionReady} title={!encryptionReady ? "Encrypted storage is not ready; contact the workspace administrator." : "Save the entered credentials"}><Save size={14}/>{saving === service.id ? "Saving…" : "Save credentials"}</button>
          {service.testable && <button className="connect-test" onClick={() => void testService(service)} disabled={testing === service.id || !service.configured}><Activity size={14}/>{testing === service.id ? "Testing…" : "Test connection"}</button>}
          {service.id === "youtube" && <button className="connect-youtube" onClick={() => void connectYouTube()} disabled={testing === "youtube" || !service.configured}><Youtube size={14}/>Connect channel</button>}
          {!service.testable && <span className="connect-manual"><Unplug size={13}/> Restricted / manual testnet setup</span>}
        </div>
        {service.check && <div className={"connect-check " + service.check.status}><span>{service.check.message}</span><time>{new Date(service.check.checked_at).toLocaleString()}</time></div>}
      </article>)}
    </div>}
    <div className="connect-footnote"><LockKeyhole size={14}/><span>Credential values are encrypted on the server and are never returned to this page. Never place API keys in chat, source code, frontend environment variables or screenshots. Trading credentials remain restricted; this page does not enable live trading.</span></div>
  </div>;
}
