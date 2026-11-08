import {FormEvent,useEffect,useRef,useState} from "react";
import {Mic,MicOff,Send,Volume2,VolumeX} from "lucide-react";
import {API,apiFetch} from "./api";

const GREETING="Hello! I'm Omonux, your AgentForge assistant. Ask me anything about your workspace.";
type SpeechWindow=Window & {SpeechRecognition?:any;webkitSpeechRecognition?:any};

export default function OmonuxVoiceAssistant(){
 const [question,Q]=useState(""),[answer,A]=useState(GREETING),[busy,B]=useState(false),[speaking,S]=useState(false),[listening,L]=useState(false),[error,E]=useState(""),[muted,M]=useState(false);
 const recognition=useRef<any>(null),speech=useRef<SpeechSynthesisUtterance|null>(null);
 const supported=typeof window!=="undefined" && "speechSynthesis" in window;
 useEffect(()=>()=>{recognition.current?.abort();if("speechSynthesis" in window)window.speechSynthesis.cancel()},[]);
 function stop(){if(supported)window.speechSynthesis.cancel();speech.current=null;S(false)}
 function speak(text:string,force=false){
  if(!supported){E("This browser cannot speak. Try Chrome or Edge.");return}
  if(muted&&!force)return;
  stop();
  const u=new SpeechSynthesisUtterance(text.slice(0,3000));
  u.lang="en-US";u.rate=0.96;u.pitch=1;
  const voices=window.speechSynthesis.getVoices();
  const english=voices.find(v=>v.lang.toLowerCase().startsWith("en"));
  if(english)u.voice=english;
  u.onstart=()=>S(true);u.onend=()=>{S(false);speech.current=null};
  u.onerror=(event)=>{S(false);speech.current=null;if(event.error!=="interrupted"&&event.error!=="canceled")E("Voice playback failed. Check browser sound and try Speak again.")};
  speech.current=u;window.speechSynthesis.speak(u);
 }
 async function ask(value:string){
  const prompt=value.trim();if(!prompt||busy)return;
  Q("");E("");stop();recognition.current?.stop();L(false);B(true);A("Omonux is thinking...");
  try{
   const response=await apiFetch(API+"/api/v1/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({agent:"research",title:"Omonux assistant: "+prompt.slice(0,90),prompt:"Respond conversationally and concisely as Omonux, the AgentForge AI assistant. Do not claim you have executed any action or placed trades. User: "+prompt})});
   const data=await response.json();
   if(response.status===401){A("Your secure workspace session has expired. Sign in again to continue talking with Omonux.");E("Sign in required. Please refresh the page and sign in to AgentForge again.");return} 
   if(response.status===403){A("Your security token needs refreshing.");E("Refresh the page to renew your security token, then try again.");return} 
   if(!response.ok){const detail=typeof data.detail==="string"?data.detail:typeof data.error==="string"?data.error:"The AI request failed.";throw Error(detail)}
   if(data.status!=="completed"||!data.result)throw Error("AI did not return a completed answer.");
   const reply=typeof data.result==="string"?data.result:typeof data.result?.content==="string"?data.result.content:JSON.stringify(data.result,null,2);
   if(!reply||reply==="null")throw Error("AI returned an empty answer.");
   A(reply);speak(reply);
  }catch(e){const message=e instanceof Error?e.message:"AI connection failed.";A("I couldn't answer that request.");E(message)}
  finally{B(false)}
 }
 function submit(e:FormEvent){e.preventDefault();void ask(question)}
 function listen(){
  if(listening){recognition.current?.stop();L(false);return}
  const w=window as SpeechWindow;const SR=w.SpeechRecognition||w.webkitSpeechRecognition;
  if(!SR){E("Microphone speech recognition is not available here. Use Chrome or Edge, or type your question.");return}
  stop();E("");
  try{
   const r=new SR();recognition.current=r;r.lang="en-US";r.continuous=false;r.interimResults=false;
   r.onstart=()=>L(true);
   r.onresult=(event:any)=>{const text=Array.from(event.results).map((item:any)=>item[0]?.transcript||"").join(" ").trim();if(text){Q(text);void ask(text)}};
   r.onerror=(event:any)=>{L(false);E(event.error==="not-allowed"?"Allow microphone access in your browser settings.":"Microphone recognition failed. Try typing instead.")};
   r.onend=()=>L(false);r.start();
  }catch{E("Unable to start the microphone.");L(false)}
 }
 return <section aria-label="Omonux conversational voice assistant" style={{display:"flex",alignItems:"center",gap:18,flexWrap:"wrap",padding:20,border:"1px solid rgba(196,155,73,.35)",borderRadius:18,margin:"20px 0",background:"linear-gradient(120deg,rgba(19,27,48,.95),rgba(9,13,27,.95))"}}>
 <style>{`@keyframes omonux-orbit{to{transform:rotate(360deg)}} @keyframes omonux-glow{50%{box-shadow:0 0 35px rgba(245,188,77,.75)}} .omonux-orb{width:94px;height:94px;border-radius:50%;border:3px solid #d7a94d;display:grid;place-items:center;color:#f6ca70;box-shadow:0 0 15px rgba(245,188,77,.3);animation:omonux-orbit 7s linear infinite,omonux-glow 2s ease-in-out infinite} @media(prefers-reduced-motion:reduce){.omonux-orb{animation:none}}`}</style>
 <div className="omonux-orb" aria-hidden="true"><Mic size={38}/></div>
 <div style={{flex:"1 1 280px",minWidth:0}}>
 <strong style={{color:"#f6ca70",fontSize:18}}>OMONUX · Talking AI Assistant</strong>
 <p aria-live="polite" style={{margin:"8px 0",color:"#e5e7eb",whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{answer}</p>
 <small style={{color:"#a9b2c5"}}>{busy?"Thinking…":listening?"Listening…":speaking?"Speaking…":"Ask a question by voice or text"}</small>
 {error&&<p role="alert" style={{color:"#ffb4a8"}}>{error} {error.includes("Sign in required")&&<button type="button" className="secondary" onClick={()=>window.location.reload()}>Return to sign in</button>}</p>}
 <form onSubmit={submit} style={{display:"flex",gap:8,marginTop:12,flexWrap:"wrap"}}>
 <input aria-label="Ask Omonux" placeholder="Ask Omonux a question..." value={question} onChange={e=>Q(e.target.value)} style={{flex:"1 1 180px",minWidth:0,padding:10,borderRadius:8}}/>
 <button type="submit" className="primary" disabled={busy||!question.trim()}><Send size={15}/> Ask</button>
 </form>
 </div>
 <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
 <button type="button" className="primary" onClick={listen} disabled={busy}>{listening?<MicOff size={16}/>:<Mic size={16}/>} {listening?"Stop listening":"Talk"}</button>
 <button type="button" className="secondary" onClick={()=>{M(false);speak(answer,true)}} disabled={!supported||busy}><Volume2 size={16}/> Speak</button>
 <button type="button" className="secondary" onClick={()=>{M(true);stop()}} disabled={!speaking}><VolumeX size={16}/> Stop</button>
 </div>
 {!supported&&<small role="status">Speech playback requires a supported browser.</small>}
 </section>;
}
