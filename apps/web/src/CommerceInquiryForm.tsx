import { useState } from "react";
import { API, apiFetch } from "./api";
import { ArrowLeft, CheckCircle2, LoaderCircle, Mail, MessageCircle, ShieldCheck, ShoppingBag } from "lucide-react";
import "./commerce-agent.css";

export default function CommerceInquiryForm() {
  const params = new URLSearchParams(window.location.search);
  const productTitle = (params.get("product") || "").slice(0, 180);
  const [values, setValues] = useState({ name: "", email: "", phone: "", product_title: productTitle, message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [received, setReceived] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const response = await apiFetch(API + "/api/v1/commerce/public/inquiries", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Your inquiry could not be sent. Try again later.");
      setReceived(true);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not send your inquiry."); }
    finally { setBusy(false); }
  }
  return <main className="commerce-public-page">
    <section className="commerce-public-card">
      <a className="commerce-public-back" href="/"><ArrowLeft size={15}/> AgentForge</a>
      <div className="commerce-hero-icon"><ShoppingBag size={24}/></div>
      <span className="commerce-eyebrow">CUSTOMER INQUIRY</span>
      <h1>Ask us about a product</h1>
      <p>Send a question or let us know you’d like to buy. We’ll review it and reply to your email.</p>
      {received ? <div className="commerce-public-success"><CheckCircle2 size={22}/><b>Thanks, we received your inquiry.</b><span>This is not an order confirmation. The store owner will review your message and reply.</span></div> : <form className="commerce-public-form" onSubmit={submit}>
        <label>Your name<input required minLength={2} maxLength={120} autoComplete="name" value={values.name} onChange={e=>setValues({...values,name:e.target.value})}/></label>
        <label>Email for our reply<input required type="email" maxLength={254} autoComplete="email" value={values.email} onChange={e=>setValues({...values,email:e.target.value})}/></label>
        <label>Phone (optional)<input type="tel" maxLength={40} autoComplete="tel" value={values.phone} onChange={e=>setValues({...values,phone:e.target.value})}/></label>
        <label>Product you’re asking about<input maxLength={180} value={values.product_title} onChange={e=>setValues({...values,product_title:e.target.value})} placeholder="Product name or link"/></label>
        <label>Your question or buying request<textarea required minLength={5} maxLength={2500} rows={5} value={values.message} onChange={e=>setValues({...values,message:e.target.value})} placeholder="Tell us what you would like to know…"/></label>
        <label className="commerce-honeypot" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={values.website} onChange={e=>setValues({...values,website:e.target.value})}/></label>
        {error && <div className="commerce-error">{error}</div>}
        <button className="primary" disabled={busy}>{busy?<LoaderCircle size={16} className="commerce-spin"/>:<Mail size={16}/>} Send inquiry</button>
        <small><ShieldCheck size={13}/> We use your contact details to respond to this inquiry. Don’t send payment or password details.</small>
      </form>}
      <div className="commerce-public-footer"><MessageCircle size={14}/> Replies are sent by the store after review.</div>
    </section>
  </main>;
}
