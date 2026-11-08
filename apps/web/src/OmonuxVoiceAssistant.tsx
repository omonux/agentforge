import { useEffect, useState } from "react";
import { Mic, Volume2, VolumeX } from "lucide-react";

const GREETING = "Hello! My name is Omonux. Let's make a lot of money today! I'm your AgentForge AI assistant. How can I help you?";

export default function OmonuxVoiceAssistant() {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    return () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); };
  }, []);
  const speak = () => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(GREETING);
    utterance.rate = 0.94;
    utterance.pitch = 1.05;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setEnabled(true);
  };
  const stop = () => {
    window.speechSynthesis.cancel();
    setSpeaking(false);
    setEnabled(false);
  };
  return <section aria-label="Omonux speaking assistant" style={{display:"flex",alignItems:"center",gap:20,flexWrap:"wrap",padding:20,border:"1px solid rgba(196,155,73,.35)",borderRadius:18,margin:"20px 0",background:"linear-gradient(120deg,rgba(19,27,48,.95),rgba(9,13,27,.95))"}}>
    <style>{`@keyframes omonux-orbit {to {transform:rotate(360deg)}} @keyframes omonux-glow {50% {box-shadow:0 0 35px rgba(245,188,77,.75)}} .omonux-orb {width:94px;height:94px;border-radius:50%;border:3px solid #d7a94d;display:grid;place-items:center;color:#f6ca70;box-shadow:0 0 15px rgba(245,188,77,.3);animation:omonux-orbit 7s linear infinite,omonux-glow 2s ease-in-out infinite;} @media(prefers-reduced-motion:reduce){.omonux-orb{animation:none}}`}</style>
    <div className="omonux-orb" aria-hidden="true"><Mic size={38}/></div>
    <div style={{flex:"1 1 240px"}}>
      <strong style={{color:"#f6ca70",fontSize:18}}>OMONUX · Voice Assistant</strong>
      <p style={{margin:"8px 0",color:"#e5e7eb"}}>{GREETING}</p>
      <small style={{color:"#a9b2c5"}}>{speaking ? "Speaking now…" : enabled ? "Ready to speak again" : "Tap Speak to hear Omonux"}</small>
    </div>
    <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
      <button type="button" className="primary" onClick={speak} disabled={!supported}><Volume2 size={16}/> Speak</button>
      <button type="button" onClick={stop} disabled={!speaking} style={{padding:"9px 12px",borderRadius:9,border:"1px solid #667085",background:"transparent",color:"#fff",cursor:"pointer"}}><VolumeX size={16}/> Stop</button>
    </div>
    {!supported && <p role="status">This browser does not support speech synthesis.</p>}
  </section>;
}
