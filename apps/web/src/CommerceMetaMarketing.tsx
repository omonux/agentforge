import { useCallback, useEffect, useState } from "react";
import { API, apiFetch } from "./api";

type Product = {id:string;title:string;status:string;listing_copy?:{promo_caption?:string}|null};
type Post = {id:string;product_id:string;channel:string;caption:string;status:string;remote_id?:string};

export default function CommerceMetaMarketing({products}:{products:Product[]}) {
 const [product,setProduct]=useState("");
 const [channel,setChannel]=useState("facebook");
 const [caption,setCaption]=useState("");
 const [image,setImage]=useState("");
 const [posts,setPosts]=useState<Post[]>([]);
 const [busy,setBusy]=useState(false);
 const [message,setMessage]=useState("");
 const approved=products.filter(p=>p.status==="ready"||p.status==="shopify_draft");
 const load=useCallback(async()=>{try{const r=await apiFetch(API+"/api/v1/commerce/meta/drafts");if(r.ok)setPosts((await r.json()).posts||[]);}catch{/* Status remains unavailable */}},[]);
 useEffect(()=>{void load();},[load]);
 const submit=async(path:string,body?:object)=>{
  setBusy(true);setMessage("");
  try{
   const r=await apiFetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},...(body?{body:JSON.stringify(body)}:{})});
   const data=await r.json();
   if(!r.ok)throw new Error(data.detail||"Request failed");
   setMessage(data.message||("Campaign status: "+data.status));
   await load();
  }catch(e){setMessage(e instanceof Error?e.message:"Action failed");}
  finally{setBusy(false);}
 };
 return <section className="panel commerce-panel">
  <div className="commerce-panel-head"><div><span className="commerce-eyebrow">SOCIAL SALES</span><h3>Facebook & Instagram marketing</h3></div></div>
  <p>Prepare a product campaign, approve it, then publish it to your connected business account. No automatic posting or advertising spend.</p>
  <label>Approved product<select value={product} onChange={e=>{setProduct(e.target.value);const p=approved.find(p=>p.id===e.target.value);setCaption(p?.listing_copy?.promo_caption||"");}}><option value="">Choose product</option>{approved.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
  <label>Channel<select value={channel} onChange={e=>setChannel(e.target.value)}><option value="facebook">Facebook Page</option><option value="instagram">Instagram professional account</option></select></label>
  <label>Advertisement caption<textarea rows={4} value={caption} onChange={e=>setCaption(e.target.value)} placeholder="Describe verified product facts, price and how to inquire."/></label>
  <label>Public HTTPS image URL (required for Instagram)<input value={image} onChange={e=>setImage(e.target.value)} placeholder="https://example.com/product.jpg"/></label>
  <button className="primary" disabled={busy||!product||caption.trim().length<10||(channel==="instagram"&&!image)} onClick={()=>void submit("/api/v1/commerce/meta/drafts",{product_id:product,channel,caption,image_url:image||null})}>Save private campaign draft</button>
  {message&&<p role="status">{message}</p>}
  <h4>Approval and publishing queue</h4>
  {posts.length===0?<p>No campaigns yet.</p>:posts.map(p=><article key={p.id} className="commerce-event"><div><b>{p.channel} · {p.status}</b><p>{p.caption}</p>{p.status==="draft"&&<button disabled={busy} onClick={()=>void submit("/api/v1/commerce/meta/drafts/"+p.id+"/approve")}>Approve campaign</button>}{p.status==="approved"&&<button disabled={busy} onClick={()=>{if(window.confirm("Publish this approved campaign to your connected "+p.channel+" account?"))void submit("/api/v1/commerce/meta/drafts/"+p.id+"/publish");}}>Publish now</button>}{p.status==="processing"&&<button disabled={busy} onClick={()=>void submit("/api/v1/commerce/meta/drafts/"+p.id+"/resume")}>Check Instagram and publish</button>}{p.status==="uncertain"&&<p>Confirmation uncertain. Check Meta manually; do not repost.</p>}</div></article>)}
  <p className="commerce-muted">Connect Meta Page access token, Page ID and Instagram professional account ID in the encrypted integration vault. Meta permissions and professional account eligibility are required. Customer messages and paid ads are not automated.</p>
 </section>;
}
