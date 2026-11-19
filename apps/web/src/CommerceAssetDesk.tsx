import { useCallback, useEffect, useState } from "react";
import { apiFetch, API } from "./api";
import { AlertCircle, CarFront, Copy, ExternalLink, House, LoaderCircle, RefreshCw, Search, ShieldCheck, Sparkles, Trash2 } from "lucide-react";

type AssetType = "vehicle" | "property";
type Source = { title:string; url:string; domain:string; snippet:string; price_text_found:string[] };
type CopyDraft = { headline:string; description:string; short_caption:string; facts_to_confirm:string };
type Listing = { id:string; asset_type:AssetType; title:string; location:string; asking_price:number; currency:string; details:Record<string,string>; source_url:string; authorized_to_market:boolean; marketing_copy:CopyDraft|null; status:string };
const parseFacts=(raw:string)=>Object.fromEntries(raw.split("\n").map(line=>line.split(":" )).filter(parts=>parts.length>1).map(([key,...value])=>[key.trim().toLowerCase().replace(/\s+/g,"_"),value.join(":").trim()]).filter(([key,value])=>key&&value));
const money=(amount:number,currency:string)=>new Intl.NumberFormat("en-NG",{style:"currency",currency,maximumFractionDigits:0}).format(amount);

export default function CommerceAssetDesk({onNotice}:{onNotice?:(message:string)=>void}) {
  const [assetType,setAssetType]=useState<AssetType>("vehicle");
  const [query,setQuery]=useState("");
  const [location,setLocation]=useState("Lagos, Nigeria");
  const [currency,setCurrency]=useState("NGN");
  const [sources,setSources]=useState<Source[]>([]);
  const [researchNote,setResearchNote]=useState("");
  const [listings,setListings]=useState<Listing[]>([]);
  const [title,setTitle]=useState("");
  const [askingPrice,setAskingPrice]=useState("");
  const [facts,setFacts]=useState("");
  const [sourceUrl,setSourceUrl]=useState("");
  const [authorized,setAuthorized]=useState(false);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");

  const load=useCallback(async()=>{
    try { const r=await apiFetch(API+"/api/v1/commerce/assets/listings"); const d=await r.json(); if(!r.ok)throw new Error(d.detail||"Could not load vehicle and property drafts."); setListings(d||[]); }
    catch(e){setError(e instanceof Error?e.message:"Could not load listing drafts.");}
  },[]);
  useEffect(()=>{void load();},[load]);

  const research=async(e:React.FormEvent)=>{e.preventDefault();setBusy("research");setError("");setSources([]);setResearchNote("");try{const r=await apiFetch(API+"/api/v1/commerce/assets/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_type:assetType,query,location,currency})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Market research failed.");setSources(d.sources||[]);setResearchNote(d.message||"");onNotice?.(`Collected ${d.sources?.length||0} public comparable listings.`);}catch(e){setError(e instanceof Error?e.message:"Market research failed.");}finally{setBusy("");}};
  const save=async(e:React.FormEvent)=>{e.preventDefault();setBusy("save");setError("");try{const r=await apiFetch(API+"/api/v1/commerce/assets/listings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_type:assetType,title,location,asking_price:Number(askingPrice),currency,details:parseFacts(facts),source_url:sourceUrl,authorized_to_market:authorized})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Listing draft could not be saved.");setTitle("");setAskingPrice("");setFacts("");setSourceUrl("");setAuthorized(false);onNotice?.(d.message||"Private listing draft saved.");await load();}catch(e){setError(e instanceof Error?e.message:"Listing draft could not be saved.");}finally{setBusy("");}};
  const draftCopy=async(id:string)=>{setBusy("copy-"+id);setError("");try{const r=await apiFetch(API+`/api/v1/commerce/assets/listings/${id}/copy`,{method:"POST"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Marketing copy could not be drafted.");onNotice?.(d.message||"Private marketing copy drafted.");await load();}catch(e){setError(e instanceof Error?e.message:"Marketing copy could not be drafted.");}finally{setBusy("");}};
  const remove=async(id:string)=>{if(!window.confirm("Delete this private listing draft?"))return;setBusy("delete-"+id);try{const r=await apiFetch(API+`/api/v1/commerce/assets/listings/${id}`,{method:"DELETE"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Draft could not be deleted.");await load();}catch(e){setError(e instanceof Error?e.message:"Draft could not be deleted.");}finally{setBusy("");}};
  const copyText=async(copy:CopyDraft)=>{await navigator.clipboard.writeText(`${copy.headline}\n\n${copy.description}\n\n${copy.short_caption}`);onNotice?.("Marketing draft copied. Review it before posting.");};
  const typeName=assetType==="vehicle"?"vehicle":"property";

  return <section className="panel commerce-panel commerce-asset-desk">
    <div className="commerce-panel-head"><div><span className="commerce-eyebrow">VEHICLE & PROPERTY MARKET DESK</span><h3>Research comparables and prepare listings</h3></div><div className="commerce-inbox-toolbar"><button className="secondary" onClick={()=>setAssetType("vehicle")} aria-pressed={assetType==="vehicle"}><CarFront size={14}/> Cars</button><button className="secondary" onClick={()=>setAssetType("property")} aria-pressed={assetType==="property"}><House size={14}/> Houses</button></div></div>
    <div className="commerce-safety"><ShieldCheck size={16}/><span>Research results are public asking-price examples, not verified sale prices or an appraisal. Only market a vehicle or property you own or have the owner’s permission to represent.</span></div>
    {error&&<div className="commerce-error"><AlertCircle size={15}/>{error}</div>}
    <div className="commerce-grid commerce-create-grid">
      <section className="panel commerce-panel"><div className="commerce-panel-head"><div><span className="commerce-eyebrow">COMPARABLE LISTING RESEARCH</span><h3>Study local {assetType==="vehicle"?"car prices":"property prices"}</h3></div><Search size={18}/></div>
        <form className="commerce-form" onSubmit={research}><label>{assetType==="vehicle"?"Car make, model, year and condition":"Property type, bedrooms and key features"}<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={assetType==="vehicle"?"e.g. 2018 Toyota Corolla, used":"e.g. 3-bedroom detached house"} minLength={2} maxLength={180} required/></label><div className="commerce-two"><label>Market location<input value={location} onChange={e=>setLocation(e.target.value)} maxLength={120} required/></label><label>Price currency<select value={currency} onChange={e=>setCurrency(e.target.value)}><option>NGN</option><option>USD</option><option>GBP</option><option>EUR</option></select></label></div><button className="primary" disabled={busy==="research"}>{busy==="research"?<LoaderCircle size={15} className="commerce-spin"/>:<Search size={15}/>} Search three times</button></form>
        {researchNote&&<div className="commerce-hint">{researchNote}</div>}
        {sources.length>0&&<div className="commerce-event-list">{sources.map((s,i)=><article className="commerce-event" key={s.url}><i/><span><b>{s.title}</b><small>{s.domain}{s.price_text_found.length?` · price text: ${s.price_text_found.join(", ")}`:" · no price text found in snippet"}</small><small>{s.snippet}</small><a href={s.url} target="_blank" rel="noreferrer">Open source listing <ExternalLink size={11}/></a></span></article>)}</div>}
      </section>
      <section className="panel commerce-panel"><div className="commerce-panel-head"><div><span className="commerce-eyebrow">YOUR AUTHORIZED LISTING</span><h3>Save a car or property draft</h3></div>{assetType==="vehicle"?<CarFront size={18}/>:<House size={18}/>}</div>
        <form className="commerce-form" onSubmit={save}><label>Listing headline<input value={title} onChange={e=>setTitle(e.target.value)} minLength={3} maxLength={180} required placeholder={assetType==="vehicle"?"2018 Toyota Corolla LE":"Three-bedroom detached house"}/></label><div className="commerce-two"><label>Location<input value={location} onChange={e=>setLocation(e.target.value)} maxLength={180} required/></label><label>Asking price ({currency})<input type="number" min="1" step="0.01" value={askingPrice} onChange={e=>setAskingPrice(e.target.value)} required/></label></div><label>Verified facts <small>One per line, formatted as “fact: value”. Don’t add details you haven’t confirmed.</small><textarea rows={5} value={facts} onChange={e=>setFacts(e.target.value)} placeholder={assetType==="vehicle"?"make: Toyota\nmodel: Corolla\nyear: 2018\nmileage: 82,000 km\ncondition: used\ntransmission: automatic":"property_type: detached house\nbedrooms: 3\nbathrooms: 4\nplot_size: 600 sqm\ntitle: verify before publishing"} required/></label><label>Source or owner authorization URL<input type="url" value={sourceUrl} onChange={e=>setSourceUrl(e.target.value)} placeholder="https://..."/></label><label className="commerce-check"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/><span><b>I own this asset or have the owner's permission to market it</b><small>Required before AI marketing copy can be generated.</small></span></label><button className="primary" disabled={busy==="save"}>{busy==="save"?<LoaderCircle size={15} className="commerce-spin"/>:<Copy size={15}/>} Save private draft</button></form>
      </section>
    </div>
    <section className="panel commerce-panel"><div className="commerce-panel-head"><div><span className="commerce-eyebrow">SAVED INVENTORY</span><h3>Vehicle and property drafts</h3></div><button className="secondary" onClick={()=>void load()} disabled={Boolean(busy)}><RefreshCw size={14}/> Refresh</button></div>
      {listings.length===0?<div className="commerce-empty"><House/><b>No car or property drafts yet</b><span>Research comparable public listings or enter an asset you’re authorized to market.</span></div>:<div className="commerce-product-list">{listings.map(item=><article className="commerce-product" key={item.id}><div className="commerce-product-main"><div className="commerce-product-title"><h4>{item.title}</h4><span className="commerce-product-status candidate">{item.asset_type} draft</span></div><p>{item.location} · {money(item.asking_price,item.currency)} · {Object.entries(item.details).slice(0,5).map(([k,v])=>`${k.replace(/_/g," ")}: ${v}`).join(" · ")}</p>{item.marketing_copy&&<div className="commerce-caption"><b>{item.marketing_copy.headline}</b><p>{item.marketing_copy.description}</p>{item.marketing_copy.facts_to_confirm&&<small>Confirm before posting: {item.marketing_copy.facts_to_confirm}</small>}</div>}{item.source_url&&<a href={item.source_url} target="_blank" rel="noreferrer">Open source <ExternalLink size={11}/></a>}{!item.authorized_to_market&&<small>Authorization needed before copy can be drafted</small>}</div><div className="commerce-product-actions">{item.marketing_copy?<button className="secondary" onClick={()=>void copyText(item.marketing_copy!)}><Copy size={14}/> Copy marketing text</button>:<button className="primary" onClick={()=>void draftCopy(item.id)} disabled={Boolean(busy)||!item.authorized_to_market}>{busy==="copy-"+item.id?<LoaderCircle size={14} className="commerce-spin"/>:<Sparkles size={14}/>} Draft marketing copy</button>}<button className="commerce-icon-button" title="Delete private draft" onClick={()=>void remove(item.id)} disabled={Boolean(busy)}><Trash2 size={15}/></button></div></article>)}</div>}
    </section>
    <div className="commerce-footer-note"><ShieldCheck size={14}/> AgentForge can research public listings and prepare private copy. It does not estimate a certified valuation or publish cars and houses to Jiji, Facebook Marketplace, or other channels yet.</div>
  </section>;
}
