import { FormEvent, useEffect, useRef, useState } from "react";
import { AudioLines, Check, Mic, MicOff, Send, Volume2, VolumeX, X } from "lucide-react";
import { API, apiFetch } from "./api";
import "./agent-voice.css";

type TaskReply = { result?: unknown; status?: string; error?: unknown; detail?: unknown };
function readable(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const key of ["content", "message", "answer", "text", "detail", "error"]) {
      if (typeof obj[key] === "string") return obj[key] as string;
    }
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}
type Turn = { role: "assistant" | "user"; text: string };

export default function AgentVoiceWidget() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([{ role: "assistant", text: "Hello. I'm AgentForge. You can type or speak naturally. What would you like to work on?" }]);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [voiceName, setVoiceName] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const lastReply = [...turns].reverse().find(t => t.role === "assistant")?.text || "";

  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.onvoiceschanged = load;
    return () => { window.speechSynthesis.cancel(); window.speechSynthesis.onvoiceschanged = null; };
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns, busy]);

  function stopSpeaking() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }

  function speak(text: string) {
    if (!voiceEnabled || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const selected = voices.find(v => v.name === voiceName);
    if (selected) utterance.voice = selected;
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }

  function toggleListening() {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const w = window as any;
    const SpeechRecognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser. Try Chrome or Edge, or type your request.");
      return;
    }
    setError("");
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event: any) => {
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += transcript;
      }
      if (finalText) setQuestion(current => (current ? current + " " : "") + finalText.trim());
    };
    recognition.onerror = (event: any) => {
      setError(event.error === "not-allowed" ? "Microphone permission was blocked. Allow microphone access in your browser." : "I couldn't hear that clearly. Please try again or type your request.");
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
  }

  async function askAgent(promptValue: string) {
    const prompt = promptValue.trim();
    if (!prompt || busy) return;
    setQuestion("");
    setError("");
    stopSpeaking();
    recognitionRef.current?.stop();
    setListening(false);
    setTurns(prev => [...prev, { role: "user", text: prompt }]);
    setBusy(true);
    try {
      const response = await apiFetch(API + "/api/v1/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: "research", title: prompt.slice(0, 110) || "Voice assistant request", prompt })
      });
      const data = await response.json() as TaskReply;
      if (!response.ok) throw new Error(readable(data.detail) || readable(data.error) || "The request could not be completed.");
      const reply = readable(data.result);
      if (data.status !== "completed" || !reply) throw new Error("The task was saved, but no completed answer was returned. Check your AgentForge task history.");
      setTurns(prev => [...prev, { role: "assistant", text: reply }]);
      speak(reply);
    } catch (e) {
      const message = e instanceof Error ? e.message : "AgentForge is temporarily unavailable.";
      setTurns(prev => [...prev, { role: "assistant", text: message }]);
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void askAgent(question);
  }

  return (
    <div className="af-voice-root">
      {open && <section className="af-companion" aria-label="AgentForge AI companion">
        <header className="af-companion-header">
          <div className="af-brand-lockup"><div className="af-brand-symbol"><img src="/agentforge-mark.svg" alt=""/></div><div><strong>AgentForge</strong><span>PERSONAL AI COMPANION</span></div></div>
          <div className="af-head-actions">
            <button className={"af-sound-toggle" + (voiceEnabled ? " enabled" : "")} onClick={() => { setVoiceEnabled(v => !v); if (voiceEnabled) stopSpeaking(); }} aria-label={voiceEnabled ? "Mute voice" : "Enable voice"}>{voiceEnabled ? <Volume2 size={16}/> : <VolumeX size={16}/>}</button>
            <button className="af-close" onClick={() => { stopSpeaking(); recognitionRef.current?.stop(); setOpen(false); }} aria-label="Close assistant"><X size={18}/></button>
          </div>
        </header>
        <div className="af-core-area">
          <div className={"af-intelligence-core" + (busy ? " thinking" : "") + (speaking ? " speaking" : "") + (listening ? " listening" : "")}>
            <div className="af-core-halo af-halo-a"/><div className="af-core-halo af-halo-b"/><div className="af-core-halo af-halo-c"/>
            <div className="af-core-disc"><img src="/agentforge-mark.svg" alt="AgentForge"/></div>
            <div className="af-core-glint"/>
          </div>
          <div className="af-core-caption">{busy ? "THINKING" : listening ? "LISTENING" : speaking ? "SPEAKING" : "READY TO ASSIST"}</div>
          <div className="af-core-subtitle">{busy ? "Working through your request" : listening ? "I'm listening. Go ahead." : speaking ? "I'm talking to you" : "Your ideas. Put into action."}</div>
          <div className="af-signal-bars" aria-hidden="true">{Array.from({length:17},(_,i)=><i key={i}/>)}</div>
        </div>
        <div className="af-conversation" ref={scrollRef} aria-live="polite">
          {turns.map((turn,i)=><div className={"af-turn " + turn.role} key={i}><span className="af-turn-label">{turn.role === "assistant" ? "AGENTFORGE" : "YOU"}</span><p>{turn.text}</p></div>)}
          {busy && <div className="af-turn assistant"><span className="af-turn-label">AGENTFORGE</span><p className="af-thinking-dots"><i/><i/><i/></p></div>}
        </div>
        {turns.length === 1 && <div className="af-suggestions"><span>TRY ASKING</span><div><button onClick={() => void askAgent("Help me plan my next project.")}>Plan a project</button><button onClick={() => void askAgent("Give me three practical ways to grow my business.")}>Grow my business</button><button onClick={() => void askAgent("Explain what my AgentForge workspace can do.")}>Explore AgentForge</button></div></div>}
        {error && <div className="af-inline-error" role="alert">{error}</div>}
        <form className="af-composer" onSubmit={submit}>
          <button type="button" className={"af-mic-button" + (listening ? " recording" : "")} onClick={toggleListening} aria-label={listening ? "Stop listening" : "Speak your request"}>{listening ? <MicOff size={18}/> : <Mic size={18}/>}</button>
          <input value={question} onChange={e => setQuestion(e.target.value)} placeholder={listening ? "Listening..." : "Message AgentForge..."} aria-label="Message AgentForge" />
          <button type="submit" className="af-send-button" disabled={busy || !question.trim()} aria-label="Send message">{busy ? <span className="af-mini-loader"/> : <Send size={17}/>}</button>
        </form>
        <footer className="af-companion-footer">
          <label>VOICE <select value={voiceName} onChange={e => setVoiceName(e.target.value)}><option value="">System default</option>{voices.filter(v => v.lang.toLowerCase().startsWith("en")).map(v => <option value={v.name} key={v.name}>{v.name}</option>)}</select></label>
          <button onClick={() => speak(lastReply)} disabled={!lastReply || !voiceEnabled}><AudioLines size={13}/> Replay answer</button>
        </footer>
        <div className="af-privacy-note"><Check size={11}/> Your AI provider key stays in AgentForge's secure backend vault.</div>
      </section>}
      <button className={"af-voice-launch" + (busy || speaking || listening ? " active" : "")} onClick={() => setOpen(v => !v)} aria-label={open ? "Close AgentForge" : "Talk to AgentForge"}>
        <span className="af-launch-aura"/><span className="af-launch-symbol"><img src="/agentforge-mark.svg" alt=""/></span><span className="af-launch-pulse"/>
      </button>
    </div>
  );
}
