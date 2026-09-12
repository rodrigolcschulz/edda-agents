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
  GitBranch,
  Layers3,
  LoaderCircle,
  MessageSquareText,
  Send,
  Shield,
  Sparkles,
  Wand2,
  Plus,
  Workflow,
  Play,
  FileOutput,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import brandLogo from "../assets/Gemini_Generated_Image_gcutwjgcutwjgcut.jpg";
import agentIcon from "../assets/Gemini_Generated_Image_3tesah3tesah3tes.jpg";

type RunStep = { name: string; detail: string };
type RunResponse = {
  run_id: string;
  trace_id: string;
  model_name: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
  cost_currency: string | null;
  answer: string;
  status: string;
  steps: RunStep[];
  memories_used: string[];
};
type WorkflowArtifact = { id: string; type: string; content: string; source_node_id: string | null };
type WorkflowNodeRun = {
  node_id: string;
  agent_run_id: string;
  status: string;
  model_name: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number | null;
  duration_ms: number;
  trace_id: string;
};
type WorkflowRunResponse = {
  run: {
    id: string;
    workflow_id: string;
    workflow_version: number;
    status: string;
    trace_id: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost: number | null;
    cost_currency: string | null;
    models_used: string[];
    duration_ms: number;
    artifacts: WorkflowArtifact[];
    node_runs: WorkflowNodeRun[];
  };
  output: WorkflowArtifact;
};
type DraftResponse = { agent: typeof defaultAgent; version: number };

type BuilderNode = {
  id: string;
  title: string;
  kind: "prompt" | "tool" | "rag" | "guardrail";
  description: string;
  enabled: boolean;
};

type WorkspaceSection = "builder" | "workflow" | "definition" | "memory" | "trace" | "agents";
type AgentSummary = { id: string; name: string; version: number };
type WorkflowDraftNode = { id: string; agent_id: string };

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

const workflowDemoAgents = [
  {
    id: "project-manager",
    name: "Gerente de Projetos",
    system_prompt: "Transforme o problema recebido em um backlog estruturado de User Stories, com critérios de aceitação, prioridades, dependências, riscos, dúvidas e premissas. Não invente requisitos.",
    model: "qwen3:14b",
    retrieval_enabled: false,
    retrieval_top_k: 3,
    tools: [],
    rules: [],
  },
  {
    id: "data-architect",
    name: "Arquiteto de Dados e Software",
    system_prompt: "Receba o problema e o plano do gerente. Produza uma especificação técnica de arquitetura com contexto, escopo, requisitos, dados, integrações, fluxo, alternativas, riscos e decisões. Registre perguntas quando faltarem informações.",
    model: "qwen3:14b",
    retrieval_enabled: false,
    retrieval_top_k: 3,
    tools: [],
    rules: [],
  },
];

export default function App() {
  const [agentName, setAgentName] = useState(defaultAgent.name);
  const [systemPrompt, setSystemPrompt] = useState(defaultAgent.system_prompt);
  const [model, setModel] = useState(defaultAgent.model);
  const [retrievalEnabled, setRetrievalEnabled] = useState(defaultAgent.retrieval_enabled);
  const [message, setMessage] = useState("Qual é a política de reembolso para clientes do plano Gold?");
  const [response, setResponse] = useState<RunResponse | null>(null);
  const [runHistory, setRunHistory] = useState<RunResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [nodes, setNodes] = useState<BuilderNode[]>(defaultNodes);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("builder");
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [selectedAgentId, setSelectedAgentId] = useState(defaultAgent.id);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [workflowInput, setWorkflowInput] = useState("A empresa precisa criar um pipeline diário de dados de vendas a partir de arquivos CSV. O processo deve validar, deduplicar, enriquecer e disponibilizar os dados aprovados para relatórios.");
  const [workflowName, setWorkflowName] = useState("Planejamento do ETL de vendas");
  const [workflowNodes, setWorkflowNodes] = useState<WorkflowDraftNode[]>([
    { id: "node-1", agent_id: "project-manager" },
    { id: "node-2", agent_id: "data-architect" },
  ]);
  const [workflowResponse, setWorkflowResponse] = useState<WorkflowRunResponse | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState("");

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
    setRunHistory([]);
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
    setRunHistory([]);
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
      const nextResponse = (await result.json()) as RunResponse;
      setResponse(nextResponse);
      setRunHistory((current) => [nextResponse, ...current].slice(0, 10));
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

  async function ensureWorkflowAgents() {
    const savedIds = new Set(agents.map((agent) => agent.id));
    for (const demoAgent of workflowDemoAgents) {
      if (savedIds.has(demoAgent.id)) continue;
      const result = await fetch(`${API_URL}/v1/agents/drafts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(demoAgent),
      });
      if (!result.ok) throw new Error(`Não foi possível preparar o agente ${demoAgent.name}.`);
    }
    setAgents((current) => [
      ...workflowDemoAgents.map((agent) => ({ id: agent.id, name: agent.name, version: 1 })),
      ...current.filter((agent) => !workflowDemoAgents.some((demoAgent) => demoAgent.id === agent.id)),
    ]);
  }

  function addWorkflowNode() {
    const fallbackAgent = agents[0]?.id ?? workflowDemoAgents[0].id;
    setWorkflowNodes((current) => [...current, { id: `node-${Date.now()}`, agent_id: fallbackAgent }]);
  }

  function updateWorkflowNode(nodeId: string, agentId: string) {
    setWorkflowNodes((current) => current.map((node) => node.id === nodeId ? { ...node, agent_id: agentId } : node));
  }

  function removeWorkflowNode(nodeId: string) {
    setWorkflowNodes((current) => current.length > 1 ? current.filter((node) => node.id !== nodeId) : current);
  }

  function moveWorkflowNode(nodeIndex: number, direction: -1 | 1) {
    setWorkflowNodes((current) => {
      const targetIndex = nodeIndex + direction;
      if (targetIndex < 0 || targetIndex >= current.length) return current;
      const next = [...current];
      [next[nodeIndex], next[targetIndex]] = [next[targetIndex], next[nodeIndex]];
      return next;
    });
  }

  async function runWorkflow(event: React.FormEvent) {
    event.preventDefault();
    if (!workflowInput.trim() || workflowLoading) return;
    setWorkflowLoading(true);
    setWorkflowError("");
    try {
      await ensureWorkflowAgents();
      const result = await fetch(`${API_URL}/v1/workflows/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow: {
            id: "sales-etl-planning",
            name: workflowName,
            version: 1,
            nodes: workflowNodes.map((node, index) => ({
              id: node.id,
              kind: "agent",
              agent_id: node.agent_id,
              ...(index === 0 ? {} : { input_mapping: { previous_artifact: workflowNodes[index - 1].id, source_problem: "input" } }),
            })),
            edges: workflowNodes.slice(1).map((node, index) => ({ source_node_id: workflowNodes[index].id, target_node_id: node.id })),
            entry_node: workflowNodes[0].id,
            output_node: workflowNodes[workflowNodes.length - 1].id,
          },
          input: { problem: workflowInput },
          user_id: "local-user",
        }),
      });
      if (!result.ok) throw new Error(`Workflow respondeu com HTTP ${result.status}.`);
      setWorkflowResponse(await result.json() as WorkflowRunResponse);
    } catch (requestError) {
      setWorkflowError(requestError instanceof Error ? requestError.message : "Não foi possível executar o workflow.");
    } finally {
      setWorkflowLoading(false);
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
            <button className={`nav-item ${activeSection === "workflow" ? "active" : ""}`} onClick={() => setActiveSection("workflow")}><Workflow size={16} /> Workflows</button>
            <button className={`nav-item ${activeSection === "definition" ? "active" : ""}`} onClick={() => setActiveSection("definition")}><Layers3 size={16} /> Definition</button>
            <button className={`nav-item ${activeSection === "memory" ? "active" : ""}`} onClick={() => setActiveSection("memory")}><Database size={16} /> Memory</button>
            <button className={`nav-item ${activeSection === "trace" ? "active" : ""}`} onClick={() => setActiveSection("trace")}><GitBranch size={16} /> Trace</button>
            <button className={`nav-item ${activeSection === "agents" ? "active" : ""}`} onClick={() => setActiveSection("agents")}><Bot size={16} /> Agents</button>
          </nav>

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

          {activeSection === "workflow" && (
            <div className="workflow-page">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">Workflow demo</div>
                  <h2>{workflowName || "Novo workflow"}</h2>
                </div>
                <div className="run-count"><span className="pulse" /> {workflowNodes.length} nós · linear</div>
              </div>

              <div className="workflow-config">
                <div className="field-group">
                  <label>Nome do workflow</label>
                  <input value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} />
                </div>
                <div className="workflow-config__meta"><span>Composição atual</span><strong>{workflowNodes.length} agentes</strong></div>
              </div>

              <div className="workflow-canvas">
                {workflowNodes.map((node, index) => {
                  const selectedAgent = [...workflowDemoAgents, ...agents].find((agent) => agent.id === node.agent_id);
                  return (
                    <div className="workflow-node-row" key={node.id}>
                      <div className={`workflow-node ${index === 0 ? "workflow-node--pm" : "workflow-node--architect"}`}>
                        <div className="workflow-node__icon">{index === 0 ? <Bot size={18} /> : <Layers3 size={18} />}</div>
                        <div>
                          <span>AGENT · {String(index + 1).padStart(2, "0")}</span>
                          <select value={node.agent_id} onChange={(event) => updateWorkflowNode(node.id, event.target.value)} aria-label={`Agent node ${index + 1}`}>
                            {[...workflowDemoAgents, ...agents.filter((agent) => !workflowDemoAgents.some((demoAgent) => demoAgent.id === agent.id))].map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
                          </select>
                          <small>{selectedAgent?.id ?? "Selecione um agente salvo."}</small>
                        </div>
                        <div className="workflow-node__controls">
                          <button type="button" onClick={() => moveWorkflowNode(index, -1)} disabled={index === 0} aria-label="Move node up">↑</button>
                          <button type="button" onClick={() => moveWorkflowNode(index, 1)} disabled={index === workflowNodes.length - 1} aria-label="Move node down">↓</button>
                          <button type="button" onClick={() => removeWorkflowNode(node.id)} disabled={workflowNodes.length === 1} aria-label="Remove node">×</button>
                        </div>
                      </div>
                      {index < workflowNodes.length - 1 && <div className="workflow-connector"><span>artifact</span><div /></div>}
                    </div>
                  );
                })}
                <button type="button" className="workflow-add-node" onClick={addWorkflowNode}><Plus size={16} /> Add agent node</button>
              </div>

              <form className="workflow-input" onSubmit={runWorkflow}>
                <div className="field-group field-group--full">
                  <label>Problema de entrada</label>
                  <textarea value={workflowInput} onChange={(event) => setWorkflowInput(event.target.value)} rows={6} />
                </div>
                <div className="workflow-actions">
                  <span>Os agentes demo serão salvos como drafts automaticamente.</span>
                  <button type="submit" className="composer-button" disabled={workflowLoading}>
                    {workflowLoading ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />}
                    {workflowLoading ? "Executando workflow" : "Executar workflow"}
                  </button>
                </div>
              </form>

              {workflowError && <div className="error-message"><CircleAlert size={16} /> {workflowError}</div>}

              {workflowResponse ? (
                <div className="workflow-result">
                  <div className="workflow-result__heading">
                    <div><div className="eyebrow">Latest workflow run</div><h3>Resultado da execução</h3></div>
                    <span className="trace-status"><Check size={15} /> {workflowResponse.run.status}</span>
                  </div>
                  <div className="workflow-metrics">
                    <div><span>Agentes</span><strong>{workflowResponse.run.node_runs.length}</strong></div>
                    <div><span>Tokens</span><strong>{workflowResponse.run.total_tokens}</strong></div>
                    <div><span>Custo</span><strong>{workflowResponse.run.estimated_cost === null ? "N/D" : `${workflowResponse.run.cost_currency ?? "USD"} ${workflowResponse.run.estimated_cost.toFixed(4)}`}</strong></div>
                    <div><span>Duração</span><strong>{Math.round(workflowResponse.run.duration_ms)} ms</strong></div>
                  </div>
                  <div className="workflow-node-runs">
                    {workflowResponse.run.node_runs.map((nodeRun, index) => (
                      <div className="workflow-node-run" key={nodeRun.node_id}>
                        <span className="trace-index">0{index + 1}</span>
                        <div><strong>{nodeRun.node_id === "project-plan" ? "Gerente de Projetos" : "Arquiteto de Dados"}</strong><small>{nodeRun.status} · {nodeRun.total_tokens} tokens · {Math.round(nodeRun.duration_ms)} ms</small></div>
                        <Check size={15} />
                      </div>
                    ))}
                  </div>
                  <div className="workflow-artifact">
                    <div className="workflow-artifact__header"><FileOutput size={16} /><strong>Artefato final · arquitetura</strong><span>{workflowResponse.output.type}</span></div>
                    <div className="answer-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{workflowResponse.output.content}</ReactMarkdown></div>
                  </div>
                </div>
              ) : (
                <div className="inspector-empty workflow-empty"><Workflow size={28} /><p>Execute o fluxo para ver os artefatos, métricas e traces de cada agente.</p></div>
              )}
            </div>
          )}

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

          {activeSection === "trace" && (
            <div className="definition-panel definition-panel--section trace-panel">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow">Trace</div>
                  <h2>Latest execution</h2>
                </div>
                <GitBranch size={18} />
              </div>
              {response ? (
                <>
                  <div className="trace-summary-grid">
                    <div><span>Status</span><strong>{response.status}</strong></div>
                    <div><span>Model</span><strong>{response.model_name ?? model}</strong></div>
                    <div><span>Total tokens</span><strong>{response.total_tokens}</strong></div>
                    <div><span>Input / output</span><strong>{response.input_tokens} / {response.output_tokens}</strong></div>
                    <div><span>Estimated cost</span><strong>{response.estimated_cost === null ? "Not configured" : `${response.cost_currency ?? "USD"} ${response.estimated_cost.toFixed(2)}`}</strong></div>
                  </div>
                  <div className="trace-identifiers">
                    <div><span>Run ID</span><code>{response.run_id}</code></div>
                    <div><span>Trace ID</span><code>{response.trace_id}</code></div>
                  </div>
                  <div className="trace-list trace-list--panel">
                    {response.steps.map((step, index) => (
                      <div className="trace-step" key={`${step.name}-${index}`}>
                        <span className="trace-index">0{index + 1}</span>
                        <div><strong>{step.name}</strong><p>{step.detail}</p></div>
                        <Check size={14} />
                      </div>
                    ))}
                  </div>
                  {runHistory.length > 1 && (
                    <div className="run-history">
                      <div className="run-history-heading">
                        <div>
                          <div className="eyebrow">Trace history</div>
                          <h3>Previous executions</h3>
                        </div>
                        <span>{runHistory.length - 1} stored</span>
                      </div>
                      <div className="run-history-list">
                        {runHistory.slice(1).map((run) => (
                          <div className="run-history-item" key={run.run_id}>
                            <div>
                              <strong>{run.model_name ?? model}</strong>
                              <span>{run.status} · {run.total_tokens} tokens · {run.run_id}</span>
                            </div>
                            <b>{run.estimated_cost === null ? "Not configured" : `${run.cost_currency ?? "USD"} ${run.estimated_cost.toFixed(2)}`}</b>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="inspector-empty">Run the sandbox to generate a trace.</div>
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
              <div className="agent-list agent-list--main">
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
            </div>
          )}
        </section>

        <aside className="inspector">
          {activeSection === "workflow" ? (
            <div className="workflow-inspector">
              <div className="inspector-heading">
                <div><div className="eyebrow">Workflow inspector</div><h2>Run overview</h2></div>
                <Workflow size={18} />
              </div>
              <div className="sandbox-rules">
                <div className="mini-stat"><GitBranch size={14} /> PM → Architect</div>
                <div className="mini-stat"><Shield size={14} /> No tools</div>
              </div>
              {workflowResponse ? (
                <div className="trace-identifiers workflow-identifiers">
                  <div><span>Workflow run</span><code>{workflowResponse.run.id}</code></div>
                  <div><span>Parent trace</span><code>{workflowResponse.run.trace_id}</code></div>
                  <div><span>Models</span><code>{workflowResponse.run.models_used.join(" · ") || "local-deterministic"}</code></div>
                </div>
              ) : <div className="inspector-empty"><Workflow size={28} /><p>O trace pai aparecerá aqui depois da execução.</p></div>}
            </div>
          ) : (
          <>
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
          </>
          )}
        </aside>
      </section>

    </main>
  );
}
