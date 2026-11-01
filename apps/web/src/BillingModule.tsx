import { useEffect, useState } from "react";
import { CreditCard, ShieldCheck, RefreshCw, ArrowUpRight } from "lucide-react";
import { API, apiFetch } from "./api";

type Plan = { id: string; name: string; amount_minor: number | null; recurring_available: boolean };
type BillingInfo = { paystack_configured: boolean; opay_configured: boolean; checkout_enabled: boolean; live_payments_enabled: boolean; customer_entitlements_enforced: boolean };

export default function BillingModule({ onNotice }: { onNotice: (message: string) => void }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [info, setInfo] = useState<BillingInfo | null>(null);
  const [email, setEmail] = useState("");
  const [selected, setSelected] = useState("pro_monthly");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [p, s] = await Promise.all([
        apiFetch(API + "/api/v1/billing/plans"),
        apiFetch(API + "/api/v1/billing/status"),
      ]);
      if (!p.ok || !s.ok) throw new Error("Unable to load billing settings.");
      const pd = await p.json();
      setPlans(pd.plans || []);
      setInfo(await s.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Billing API unavailable.");
    }
  }
  useEffect(() => { load(); }, []);

  async function checkout(provider: "paystack" | "opay") {
    setBusy(provider);
    setError("");
    try {
      const response = await apiFetch(API + "/api/v1/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, plan: selected, email }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not create checkout.");
      const target = new URL(data.checkout_url);
      if (target.protocol !== "https:" || !(target.hostname === "checkout.paystack.com" ||
          target.hostname === "cashier.opaycheckout.com" ||
          target.hostname === "sandboxcashier.opaycheckout.com")) {
        throw new Error("The provider returned an unexpected checkout address.");
      }
      window.location.assign(target.toString());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Checkout failed.");
    } finally {
      setBusy("");
    }
  }

  const plan = plans.find(p => p.id === selected);
  const price = plan?.amount_minor == null ? "Price not configured" :
    "₦" + (plan.amount_minor / 100).toLocaleString("en-NG", { maximumFractionDigits: 0 }) + " / month";

  return <div>
    <div className="sectiontitle"><div><h2>Plans & payments</h2><p>Configure paid access through secure hosted provider checkout.</p></div>
      <button className="secondary" onClick={load}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="notice warn">{error}</div>}
    <div className="notice warn"><ShieldCheck size={17}/> Billing is disabled until merchant credentials, prices and sandbox checks are complete. Customer entitlements are not yet enforced.</div>
    <div className="columns">
      <div className="panel">
        <h3>Subscription checkout</h3><p>Choose a plan and payment provider.</p>
        <label>Customer email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="customer@example.com" required/></label>
        <label>Plan<select value={selected} onChange={e=>setSelected(e.target.value)}>
          {plans.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
        <div className="roadmap"><b><CreditCard size={16}/></b><span>{plan?.name || "Plan"}<small>{price}</small></span><small>{plan?.recurring_available ? "PAYSTACK RECURRING" : "MONTHLY PLAN"}</small></div>
        <div className="twocol">
          <button className="primary" disabled={!email || !info?.checkout_enabled || busy!==""} onClick={()=>checkout("paystack")}>
            {busy==="paystack" ? "Opening..." : "Pay with Paystack"}
          </button>
          <button className="secondary" disabled={!email || !info?.live_payments_enabled || busy!==""} onClick={()=>checkout("opay")}>
            {busy==="opay" ? "Opening..." : "Pay with OPay"}
          </button>
        </div>
        <div className="guard"><ShieldCheck size={15}/> Card details are entered only on provider-hosted pages. AgentForge never stores card numbers or CVVs.</div>
      </div>
      <div className="panel">
        <h3>Provider readiness</h3><p>Connection status only; this does not prove live merchant approval.</p>
        <div className="roadmap"><b>1</b><span>Paystack API key<small>{info?.paystack_configured ? "Credential configured" : "Not configured"}</small></span><small>{info?.paystack_configured ? "SET" : "WAITING"}</small></div>
        <div className="roadmap"><b>2</b><span>OPay merchant access<small>{info?.opay_configured ? "Merchant credentials configured" : "Not configured"}</small></span><small>{info?.opay_configured ? "SET" : "WAITING"}</small></div>
        <div className="roadmap"><b>3</b><span>Live checkout<small>Must remain disabled until sandbox validation</small></span><small>{info?.live_payments_enabled ? "ENABLED" : "DISABLED"}</small></div>
        <div className="roadmap"><b>4</b><span>Customer access control<small>Multi-tenant accounts and entitlements still required</small></span><small>PLANNED</small></div>
        <p className="muted"><ArrowUpRight size={13}/> Paystack supports recurring card billing with configured plan codes. OPay is manual renewal in this release.</p>
      </div>
    </div>
  </div>;
}
