import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  Check,
  CircleAlert,
  Clock3,
  Database,
  Layers3,
  LoaderCircle,
  MessageSquareText,
  Send,
  Shield,
  Sparkles,
  Wand2,
  Plus,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import brandLogo from "../assets/Gemini_Generated_Image_gcutwjgcutwjgcut.jpg";
import agentIcon from "../assets/Gemini_Generated_Image_3tesah3tesah3tes.jpg";

type RunStep = { name: string; detail: string };
type RunResponse = {
  answer: string;
  status: string;
  steps: RunStep[];
  memories_used: string[];
};
type DraftResponse = { agent: typeof defaultAgent; version: number };

type BuilderNode = {
  id: string;
  title: string;
  kind: "prompt" | "tool" | "rag" | "guardrail";
  description: string;
  enabled: boolean;
};

type WorkspaceSection = "builder" | "definition" | "memory" | "agents";
type AgentSummary = { id: string; name: string; version: number };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const defaultNodes: BuilderNode[] = [
  { id: "prompt", title: "System prompt", kind: "prompt", description: "Define the agent persona and safety posture.", enabled: true },
  { id: "tool", title: "Tool calling", kind: "tool", description: "Enables the sandboxed tool router.", enabled: true },
  { id: "rag", title: "Retrieval", kind: "rag", description: "Search relevant knowledge before answering.", enabled: true },
  { id: "guardrail", title: "Guardrails", kind: "guardrail", description: "Validate input and output before execution.", enabled: true },
];

const defaultAgent = {
  id: "atlas-support",
  name: "Atlas Support",
  system_prompt: "Aid users with accurate answers, grounded policy references, and safe tool usage.",
  model: "qwen3:14b",
  retrieval_enabled: true,
  retrieval_top_k: 3,
  tools: [{ name: "echo", description: "Returns a result for local testing", requires_confirmation: false }],
  rules: [
    { name: "no-private-data", stage: "input", blocked_terms: ["senha", "token", "secret"] },
    { name: "confidential-policy", stage: "output", blocked_terms: ["ignorar regras"] },
  ],
};

export default function App() {
  const [agentName, setAgentName] = useState(defaultAgent.name);
  const [systemPrompt, setSystemPrompt] = useState(defaultAgent.system_prompt);
  const [model, setModel] = useState(defaultAgent.model);
  const [retrievalEnabled, setRetrievalEnabled] = useState(defaultAgent.retrieval_enabled);
  const [message, setMessage] = useState("Qual é a política de reembolso para clientes do plano Gold?");
  const [response, setResponse] = useState<RunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [nodes, setNodes] = useState<BuilderNode[]>(defaultNodes);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("builder");
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [selectedAgentId, setSelectedAgentId] = useState(defaultAgent.id);
  const [agents, setAgents] = useState<AgentSummary[]>([]);

  const generatedAgent = useMemo(
    () => ({
      id: selectedAgentId,
      name: agentName,
      system_prompt: systemPrompt,
      model,
      retrieval_enabled: retrievalEnabled,
      retrieval_top_k: 3,
      tools: defaultAgent.tools,
      rules: defaultAgent.rules,
    }),
    [agentName, model, retrievalEnabled, systemPrompt, selectedAgentId],
  );

  useEffect(() => {
    fetch(`${API_URL}/v1/agents/drafts`)
      .then((result) => result.ok ? result.json() as Promise<AgentSummary[]> : [])
      .then((savedAgents) => {
        setAgents(savedAgents);
        const firstAgent = savedAgents.find((agent) => agent.id === defaultAgent.id) ?? savedAgents[0];
        if (firstAgent) loadAgent(firstAgent.id);
      })
      .catch(() => undefined);
  }, []);

  async function loadAgent(agentId: string) {
    const result = await fetch(`${API_URL}/v1/agents/drafts/${agentId}`);
    if (!result.ok) return;
    const draft = await result.json() as DraftResponse;
    setSelectedAgentId(draft.agent.id);
    setAgentName(draft.agent.name);
    setSystemPrompt(draft.agent.system_prompt);
    setModel(draft.agent.model);
    setRetrievalEnabled(draft.agent.retrieval_enabled);
    setDraftVersion(draft.version);
    setResponse(null);
    setSaveState("idle");
    setActiveSection("builder");
  }

  function createAgent() {
    const id = `agent-${Date.now()}`;
    setSelectedAgentId(id);
    setAgentName("New agent");
    setSystemPrompt(defaultAgent.system_prompt);
    setModel(defaultAgent.model);
    setRetrievalEnabled(defaultAgent.retrieval_enabled);
    setDraftVersion(null);
    setResponse(null);
    setSaveState("idle");
    setActiveSection("builder");
  }

  function toggleNode(nodeId: string) {
    setNodes((current) =>
      current.map((node) =>
        node.id === nodeId ? { ...node, enabled: !node.enabled } : node,
      ),
    );
  }

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
          agent: generatedAgent,
          request: { thread_id: "builder-thread", user_id: "local-user", message },
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

  async function saveDraft() {
    if (saveState === "saving") return;
    setSaveState("saving");
    try {
      const result = await fetch(`${API_URL}/v1/agents/drafts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(generatedAgent),
      });
      if (!result.ok) throw new Error(`Não foi possível salvar o draft (HTTP ${result.status}).`);
      const saved = await result.json() as DraftResponse;
      setSelectedAgentId(saved.agent.id);
      setDraftVersion(saved.version);
      setAgents((current) => {
        const summary = { id: saved.agent.id, name: saved.agent.name, version: saved.version };
        return current.some((agent) => agent.id === summary.id)
          ? current.map((agent) => agent.id === summary.id ? summary : agent)
          : [summary, ...current];
      });
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><img src={brandLogo} alt="Edda Agents" /></span>
          <span>Edda Agents</span>
          <span className="env-pill">PHASE 3</span>
        </div>
        <div className="topbar-meta">
          <span className="status-dot" /> Runtime online
          <span className="divider" />
          <span>Builder / Sandbox</span>
        </div>
      </header>

      <section className="workspace">
        <aside className="sidebar">
          <div className="eyebrow">Agent workspace</div>
          <h1>{agentName}</h1>
          <p className="muted">Visual builder and local sandbox for prototyping a multi-step LLM agent before publishing.</p>

          <div className="agent-card">
            <div className="agent-card-header">
              <span className="avatar"><img src={agentIcon} alt="" /></span>
              <div>
                <strong>{agentName}</strong>
                <small>Draft · v0.2</small>
              </div>
              <ArrowUpRight size={15} />
            </div>
            <div className="card-line"><span>Model</span><b>{model}</b></div>
            <div className="card-line"><span>Mode</span><b className="green">Visual builder</b></div>
          </div>

          <nav className="nav-list" aria-label="Agent sections">
            <button className={`nav-item ${activeSection === "builder" ? "active" : ""}`} onClick={() => setActiveSection("builder")}><Activity size={16} /> Builder canvas</button>
            <button className={`nav-item ${activeSection === "definition" ? "active" : ""}`} onClick={() => setActiveSection("definition")}><Layers3 size={16} /> Definition</button>
            <button className={`nav-item ${activeSection === "memory" ? "active" : ""}`} onClick={() => setActiveSection("memory")}><Database size={16} /> Memory</button>
            <button className={`nav-item ${activeSection === "agents" ? "active" : ""}`} onClick={() => setActiveSection("agents")}><Bot size={16} /> Agents</button>
          </nav>

          {activeSection === "agents" && (
            <div className="agent-list">
              <div className="agent-list-heading">
                <div className="eyebrow">Saved agents</div>
                <button type="button" className="agent-list-add" onClick={createAgent} title="Create agent">
                  <Plus size={14} />
                  <span>New agent</span>
                </button>
              </div>
              {agents.length ? agents.map((agent) => (
                <button
                  type="button"
                  key={agent.id}
                  className={`agent-list-item ${selectedAgentId === agent.id ? "active" : ""}`}
                  onClick={() => loadAgent(agent.id)}
                >
                  <span>{agent.name}</span>
                  <small>v{agent.version}</small>
                </button>
              )) : <p className="agent-list-empty">No saved agents yet.</p>}
            </div>
          )}

          <div className="sidebar-footer">
            <span className="status-dot" /> Local runtime ready
            <small>Ollama + LangGraph + FastAPI</small>
          </div>
        </aside>

        <section className="main-panel main-panel--builder">
          {activeSection === "builder" && <>
            <div className="panel-heading">
              <div>
                <div className="eyebrow">Flow builder</div>
                <h2>Agent graph</h2>
              </div>
              <div className="run-count"><span className="pulse" /> Editable</div>
            </div>

          <div className="builder-surface">
            <div className="builder-header-row">
              <div className="field-group field-group--wide">
                <label>Agent name</label>
                <input value={agentName} onChange={(event) => setAgentName(event.target.value)} />
              </div>
              <div className="field-group">
                <label>Model</label>
                <select value={model} onChange={(event) => setModel(event.target.value)}>
                  <option value="qwen3:14b">qwen3:14b</option>
                  <option value="local-deterministic">local-deterministic</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                </select>
              </div>
            </div>

            <div className="builder-canvas">
              {nodes.map((node) => (
                <button
                  type="button"
                  key={node.id}
                  className={`builder-node builder-node--${node.kind} ${node.enabled ? "is-enabled" : "is-disabled"}`}
                  onClick={() => toggleNode(node.id)}
                >
                  <div className="builder-node__topline">
                    <span className="builder-node__badge">{node.kind}</span>
                    <span className={`toggle-indicator ${node.enabled ? "on" : "off"}`} />
                  </div>
                  <strong>{node.title}</strong>
                  <small>{node.description}</small>
                </button>
              ))}
            </div>

            <div className="field-group field-group--full">
              <label>System prompt</label>
              <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={5} />
            </div>

            <div className="builder-actions">
              <label className="toggle-row">
                <input type="checkbox" checked={retrievalEnabled} onChange={() => setRetrievalEnabled((current) => !current)} />
                <span>Enable retrieval / RAG</span>
              </label>
              <button type="button" className="secondary-btn" onClick={saveDraft} disabled={saveState === "saving"}>
                <Sparkles size={16} />
                {saveState === "saving" ? "Saving..." : saveState === "saved" ? `Saved v${draftVersion}` : saveState === "error" ? "Save failed" : "Save draft"}
              </button>
            </div>
            </div>
          </>}

          {activeSection === "definition" && (
            <div className="definition-panel definition-panel--section">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">Definition</div>
                  <h2>Agent config</h2>
                </div>
                <Wand2 size={18} />
              </div>
              <pre>{JSON.stringify(generatedAgent, null, 2)}</pre>
            </div>
          )}

          {activeSection === "memory" && (
            <div className="definition-panel definition-panel--section">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">Memory</div>
                  <h2>Thread context</h2>
                </div>
                <Database size={18} />
              </div>
              {response ? (
                <div className="memory-detail">
                  <p>Context recalled during the latest sandbox run.</p>
                  {response.memories_used.length ? (
                    <ul>{response.memories_used.map((memory, index) => <li key={`${memory}-${index}`}>{memory}</li>)}</ul>
                  ) : (
                    <div className="inspector-empty">No previous context in this thread.</div>
                  )}
                </div>
              ) : (
                <div className="inspector-empty">Run the sandbox to populate thread memory.</div>
              )}
            </div>
          )}

          {activeSection === "agents" && (
            <div className="definition-panel definition-panel--section">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">Agents</div>
                  <h2>Choose an agent</h2>
                </div>
                <Bot size={18} />
              </div>
              <p className="agent-picker-copy">Select a saved agent from the sidebar to continue editing its definition.</p>
            </div>
          )}
        </section>

        <aside className="inspector">
          <div className="inspector-heading">
            <div>
              <div className="eyebrow">Run inspector</div>
              <h2>Sandbox</h2>
            </div>
            <MessageSquareText size={18} />
          </div>

          <div className="sandbox-rules">
            <div className="mini-stat"><BrainCircuit size={14} /> Plan/act/reflect</div>
            <div className="mini-stat"><Shield size={14} /> Guardrails enabled</div>
            <div className="mini-stat"><Database size={14} /> {retrievalEnabled ? "RAG on" : "RAG off"}</div>
          </div>

          <div className="chat-surface chat-surface--compact">
            {response ? (
              <div className="answer">
                <div className="message-label">
                  <span className="avatar small"><img src={agentIcon} alt="" /></span>
                  {agentName}
                  <time>just now</time>
                </div>
                <div className="answer-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.answer}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <span>01</span>
                <p>Run the sandbox to see the agent output and trace.</p>
              </div>
            )}

            {error && (
              <div className="error-message"><CircleAlert size={16} /> {error}</div>
            )}

            <form className="composer" onSubmit={runAgent}>
              <textarea value={message} onChange={(event) => setMessage(event.target.value)} aria-label="Message" rows={4} />
              <button type="submit" disabled={loading} title="Run agent">
                {loading ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
                <span>{loading ? "Running" : "Run agent"}</span>
              </button>
            </form>
          </div>

          {response ? (
            <>
              <div className="trace-status"><Check size={15} /> {response.status}</div>
              <div className="trace-list">
                {response.steps.map((step, index) => (
                  <div className="trace-step" key={`${step.name}-${index}`}>
                    <span className="trace-index">0{index + 1}</span>
                    <div>
                      <strong>{step.name}</strong>
                      <p>{step.detail}</p>
                    </div>
                    <Check size={14} />
                  </div>
                ))}
              </div>
              <div className="memory-box">
                <div>
                  <Database size={15} />
                  <strong>Memory used</strong>
                </div>
                <p>{response.memories_used.length ? response.memories_used.join(" · ") : "No previous context in this thread."}</p>
              </div>
            </>
          ) : (
            <div className="inspector-empty">
              <Bot size={28} />
              <p>Execute a prompt to inspect memory, routing and reflection decisions.</p>
            </div>
          )}
        </aside>
      </section>

    </main>
  );
}
