import { useState } from "react";
import { Activity, ArrowUpRight, Bot, BrainCircuit, Check, CircleAlert, Clock3, Database, Layers3, LoaderCircle, Send } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type RunStep = { name: string; detail: string };
type RunResponse = {
  answer: string;
  status: string;
  steps: RunStep[];
  memories_used: string[];
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const agent = {
  id: "support",
  name: "Atlas Support",
  system_prompt: "Help the user clearly and safely.",
  model: "qwen3:14b",
};

export default function App() {
  const [message, setMessage] = useState("Explique como funciona a memória deste agente.");
  const [response, setResponse] = useState<RunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAgent(event: React.FormEvent) {
    event.preventDefault();
    if (!message.trim() || loading) return;

    setLoading(true);
    setError("");
    try {
      const result = await fetch(`${API_URL}/v1/agents/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent,
          request: { thread_id: "sandbox-thread", user_id: "local-user", message },
        }),
      });
      if (!result.ok) throw new Error(`API respondeu com HTTP ${result.status}`);
      setResponse((await result.json()) as RunResponse);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível executar o agente.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><Bot size={18} /></span><span>AgentForge</span><span className="env-pill">LOCAL</span></div>
        <div className="topbar-meta"><span className="status-dot" /> Runtime online <span className="divider" /> <span>Sandbox / Atlas Support</span></div>
      </header>

      <section className="workspace">
        <aside className="sidebar">
          <div className="eyebrow">Agent workspace</div>
          <h1>Atlas Support</h1>
          <p className="muted">Um agente local para testar memória, tools e comportamento antes da publicação.</p>
          <div className="agent-card">
            <div className="agent-card-header"><span className="avatar"><BrainCircuit size={17} /></span><div><strong>Atlas Support</strong><small>Draft · v0.1</small></div><ArrowUpRight size={15} /></div>
            <div className="card-line"><span>Model</span><b>{agent.model}</b></div>
            <div className="card-line"><span>Memory</span><b className="green">Thread enabled</b></div>
          </div>
          <nav className="nav-list" aria-label="Agent sections">
            <button className="nav-item active"><Activity size={16} /> Run sandbox <span>⌘</span></button>
            <button className="nav-item"><Layers3 size={16} /> Graph definition</button>
            <button className="nav-item"><Database size={16} /> Memory store</button>
          </nav>
          <div className="sidebar-footer"><span className="status-dot" /> Ollama connected <small>localhost:11434</small></div>
        </aside>

        <section className="main-panel">
          <div className="panel-heading"><div><div className="eyebrow">Execution lab</div><h2>Test your agent</h2></div><div className="run-count"><span className="pulse" /> Ready to run</div></div>
          <div className="chat-surface">
            <div className="chat-intro"><span className="intro-icon"><Bot size={22} /></span><div><strong>Atlas Support is ready</strong><p>Send a message to inspect the complete execution path.</p></div></div>
            {response ? <div className="answer"><div className="message-label"><span className="avatar small"><Bot size={13} /></span> Atlas Support <time>just now</time></div><div className="answer-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{response.answer}</ReactMarkdown></div></div> : <div className="empty-state"><span>01</span><p>Your response will appear here.<br /><small>Every run is recorded as an inspectable sequence.</small></p></div>}
            {error && <div className="error-message"><CircleAlert size={16} /> {error}</div>}
            <form className="composer" onSubmit={runAgent}><textarea value={message} onChange={(event) => setMessage(event.target.value)} aria-label="Message" /><button type="submit" disabled={loading} title="Run agent">{loading ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}<span>{loading ? "Running" : "Run agent"}</span></button></form>
          </div>
        </section>

        <aside className="inspector"><div className="inspector-heading"><div><div className="eyebrow">Run inspector</div><h2>Execution trace</h2></div><Clock3 size={18} /></div>{response ? <><div className="trace-status"><Check size={15} /> {response.status}</div><div className="trace-list">{response.steps.map((step, index) => <div className="trace-step" key={`${step.name}-${index}`}><span className="trace-index">0{index + 1}</span><div><strong>{step.name}</strong><p>{step.detail}</p></div><Check size={14} /></div>)}</div><div className="memory-box"><div><Database size={15} /><strong>Memory used</strong></div><p>{response.memories_used.length ? response.memories_used.join(" · ") : "No previous context in this thread."}</p></div></> : <div className="inspector-empty"><Activity size={28} /><p>Run the agent to inspect its memory, plan, action and reflection steps.</p></div>}</aside>
      </section>
    </main>
  );
}
