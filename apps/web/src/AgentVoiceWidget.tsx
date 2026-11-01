import { FormEvent, useEffect, useRef, useState } from "react";
import { MessageCircle, Mic2, Send, Volume2, VolumeX, X } from "lucide-react";
import { API, apiFetch } from "./api";
import "./agent-voice.css";

type TaskReply = { result?: string; output?: string; response?: string; status?: string; detail?: string };

export default function AgentVoiceWidget() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [reply, setReply] = useState("Hello! I'm your AgentForge assistant. Ask me something and I'll help you get it done.");
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);

  function speak(text: string) {
    if (!voiceEnabled || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1.02;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeaking() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }

  async function askAgent(event: FormEvent) {
    event.preventDefault();
    const prompt = question.trim();
    if (!prompt || busy) return;
    setBusy(true);
    stopSpeaking();
    setReply("I'm thinking through that now...");
    try {
      const response = await apiFetch(API + "/api/v1/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: "research", title: prompt.slice(0, 110) || "Voice assistant request", prompt })
      });
      const data = await response.json() as TaskReply;
      if (!response.ok) throw new Error(data.detail || "I couldn't complete that request.");
      const answer = data.result || data.output || data.response || "Your request was accepted by AgentForge. Open the workspace task history to review its result.";
      setReply(answer);
      speak(answer);
      setQuestion("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "The assistant is unavailable right now.";
      setReply(message);
      speak(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="af-voice-root">
      {open && <section className="af-voice-panel" aria-label="AgentForge voice assistant">
        <div className="af-voice-head">
          <div className="af-voice-mini-orb"><img src="/agentforge-mark.svg" alt="" /></div>
          <div><strong>AgentForge</strong><small>{busy ? "THINKING" : speaking ? "SPEAKING" : "AI ASSISTANT"}</small></div>
          <button className="af-voice-iconbtn" onClick={() => { stopSpeaking(); setOpen(false); }} aria-label="Close assistant"><X size={17}/></button>
        </div>
        <div className="af-voice-stage">
          <div className={"af-voice-orb" + (busy || speaking ? " is-active" : "")}>
            <span className="af-voice-orbit af-orbit-one"/><span className="af-voice-orbit af-orbit-two"/>
            <div className="af-voice-core"><img src="/agentforge-mark.svg" alt="AgentForge symbol"/></div>
          </div>
          <span className="af-voice-status">{busy ? "Working on your request" : speaking ? "Speaking to you" : "Ready when you are"}</span>
        </div>
        <div className="af-voice-reply" aria-live="polite">{reply}</div>
        <form className="af-voice-form" onSubmit={askAgent}>
          <input value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask AgentForge anything..." aria-label="Ask AgentForge" />
          <button type="submit" disabled={busy || !question.trim()} aria-label="Send request">{busy ? <span className="af-voice-spinner"/> : <Send size={16}/>}</button>
        </form>
        <div className="af-voice-actions">
          <button onClick={() => speak(reply)} disabled={!reply}><Volume2 size={14}/> Speak reply</button>
          <button onClick={() => { setVoiceEnabled(v => !v); if (voiceEnabled) stopSpeaking(); }}><VolumeX size={14}/>{voiceEnabled ? "Mute voice" : "Enable voice"}</button>
        </div>
        <p className="af-voice-note">Voice uses your browser's available speech engine. AI answers require your connected provider.</p>
      </section>}
      <button className={"af-voice-launch" + (busy || speaking ? " is-active" : "")} onClick={() => setOpen(v => !v)} aria-label={open ? "Close AgentForge assistant" : "Open AgentForge assistant"}>
        <span className="af-launch-ring"/><span className="af-launch-mark"><img src="/agentforge-mark.svg" alt=""/></span>
        <span className="af-launch-label">{open ? <X size={19}/> : <MessageCircle size={18}/>}</span>
      </button>
    </div>
  );
}
