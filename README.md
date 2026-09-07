# Edda Agents — Plataforma de Criação de Agentes de IA

> Plataforma self-service onde usuários criam, testam e publicam agentes de IA (LLM + tools + RAG + memória) através de um builder visual, com observabilidade e governança de nível de produção.

Projeto de portfólio focado em demonstrar competência de **AI Engineering** (não só "chamar uma API de LLM"): orquestração de agentes, RAG, memória, roteamento de modelos, observabilidade/tracing, avaliação e segurança multi-tenant.

---

## 1. Visão do produto

Um usuário entra na plataforma, monta um agente num canvas visual (system prompt, tools disponíveis, fontes de RAG, modelo/roteamento, regras de guardrail), testa numa sandbox de chat, e publica. O agente publicado vira um endpoint (API/chat widget) que qualquer app pode consumir.

**Analogia de mercado:** o que Dify/Flowise/Langflow fazem — mas construído do zero, para mostrar domínio da engine por baixo do builder, não só a configuração de uma ferramenta pronta.

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Agent Builder │  │ Chat Sandbox │  │ Dashboard/Traces   │  │
│  │ (canvas nós)  │  │  (teste)     │  │ (Langfuse embed)   │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└───────────────────────────┬───────────────────────────────────┘
                             │ REST / WebSocket (streaming)
┌───────────────────────────▼───────────────────────────────────┐
│                    BACKEND API (FastAPI)                       │
│  - Auth (JWT/OAuth) + multi-tenancy (RLS)                      │
│  - CRUD de definições de agente (versionado)                   │
│  - Publica definição → LangGraph runtime                       │
└───────────────────────────┬───────────────────────────────────┘
                             │
┌───────────────────────────▼───────────────────────────────────┐
│                 AGENT RUNTIME (LangGraph)                      │
│  - Interpreta a definição declarativa do agente                │
│  - Nó: router de modelo (custo/latência/capacidade)             │
│  - Nó: plan → act → reflect (loop com condição de saída)        │
│  - Nó: rules/guardrails (pré e pós execução)                    │
│  - Nó: tool calling (sandboxed)                                 │
│  - Checkpointer Postgres = memória de curto prazo (thread)      │
│  - Store Postgres = memória de longo prazo (cross-thread)       │
└───────┬───────────────────────────────────┬────────────────────┘
        │                                   │
┌───────▼────────────┐          ┌───────────▼───────────────────┐
│  Postgres + pgvector │          │        Langfuse (self-host)    │
│  - agents (config)   │          │  - tracing de cada execução    │
│  - documents/chunks   │          │  - custo/latência por passo    │
│  - checkpoints        │          │  - avaliação/scores            │
│  - long-term memory   │          └────────────────────────────────┘
└───────────────────────┘
```

---

## 3. Stack (100% open-source)

| Camada | Ferramenta | Papel |
|---|---|---|
| Orquestração de agente | **LangGraph** | grafo de estado, loops plan-reflect, checkpointing, roteamento condicional |
| Integrações LLM | **LangChain** | wrappers de provedores, retrievers, loaders |
| API backend | **FastAPI** | CRUD, auth, streaming (SSE/WebSocket) |
| Banco | **PostgreSQL + pgvector** | dados relacionais, checkpoints, embeddings/RAG |
| Observabilidade/tracing | **Langfuse** (self-host, MIT) | tracing, custo, avaliação, dataset de testes |
| Frontend | **React + React Flow** | canvas de construção do agente (nós e arestas) |
| Fila (opcional, fase 2) | **Redis / RQ** | execução assíncrona de agentes de longa duração |
| Sandbox de execução de tools | **Docker / gVisor / Firecracker** | isolar execução de código/tools de terceiros |

> **Nota sobre LangSmith:** ele NÃO é open-source (plataforma fechada, self-host só em plano Enterprise). Por isso o tracing fica com Langfuse, que é MIT e self-hostável em todos os planos.

> **Política de custos:** o ambiente local usa Ollama para inferência e Langfuse self-hosted para observabilidade. Não dependemos de APIs pagas ou do Langfuse Cloud. O core do Langfuse é MIT; componentes Enterprise (`ee/`) possuem licença própria e não são necessários para este projeto.

---

## 4. Modelo de dados (núcleo)

- `agents` — definição declarativa (JSON): nome, system prompt, modelo(s), tools habilitadas, fontes de RAG, regras/guardrails, versão.
- `agent_versions` — histórico versionado (nunca sobrescreve, cria nova versão).
- `documents` / `chunks` — RAG: texto + embedding (pgvector) + metadata + `tenant_id`.
- `threads` — conversas (mapeiam para `thread_id` do checkpointer do LangGraph).
- `long_term_memory` — fatos extraídos por usuário/agente, com embedding para busca semântica.
- `runs` — cada execução do agente (status, custo, duração, trace_id do Langfuse).

Todas as tabelas com `tenant_id` + Row Level Security (RLS) no Postgres.

---

## 5. Roadmap (por fases)

### Fase 0 — Fundação
- [x] Setup inicial do monorepo (backend, frontend React/Vite e infra)
- [x] Postgres + pgvector rodando no Docker Compose, com schema inicial, pgvector e RLS por tenant
- [x] LangGraph "hello world": grafo com 1 nó de modelo, incluindo teste real com Ollama `qwen3:14b`
- [x] Cliente de ingestão Langfuse integrado ao grafo e stack self-hosted local iniciado via Docker Compose

### Fase 1 — Engine de agente (o core técnico)
- [x] Definição declarativa de agente (schema JSON/Pydantic)
- [x] Interpretador: definição → grafo LangGraph dinâmico
- [x] Nó de roteamento de modelo (ex: pergunta simples → modelo barato, complexa → modelo forte)
- [x] Loop **plan → act → reflect**: o agente planeja, executa tool, reflete se resolveu, decide continuar ou responder
- [x] Checkpointer Postgres (memória de curto prazo por thread)
- [x] Tool calling com sandbox (nunca `eval()` direto do input do usuário)

### Fase 2 — RAG e memória de longo prazo
- [ ] Ingestão de documentos → chunking → embeddings → pgvector
- [ ] Nó de retrieval no grafo (RAG condicional: só busca se precisar)
- [ ] Extração de memória de longo prazo (fatos relevantes por usuário, com embedding)
- [ ] Estratégia de "esquecimento"/TTL de memória

### Fase 3 — Builder visual (React)
- [ ] Canvas com React Flow: nós = (prompt, tool, condição, RAG, guardrail)
- [ ] Serialização do canvas → definição declarativa do agente
- [ ] Chat sandbox para testar o agente antes de publicar
- [ ] Preview de trace em tempo real (embed do Langfuse ou dashboard próprio)

### Fase 4 — Observabilidade e avaliação (o que separa hobby de produção)
- [ ] Todo run instrumentado no Langfuse: input, output, custo, latência, tokens
- [ ] Dataset de avaliação (casos de teste com resultado esperado)
- [ ] Avaliadores automáticos (LLM-as-judge + regras determinísticas)
- [ ] Alertas de regressão (agente ficou pior após mudança de prompt)

### Fase 5 — Multi-tenancy, segurança e produção
- [ ] Auth (JWT) + isolamento por tenant (RLS no Postgres)
- [ ] Rate limiting por agente/tenant
- [ ] Guardrails: validação de input/output (PII, prompt injection, conteúdo proibido)
- [ ] Sandbox real de execução de tools (container efêmero, sem acesso à rede por padrão)
- [ ] Deploy (Docker Compose → depois Kubernetes, se quiser ir além)

### Fase 6 — Polimento de portfólio
- [ ] README com GIF/vídeo demo
- [ ] Agente de exemplo pronto (ex: assistente de suporte com RAG sobre uma FAQ)
- [ ] Documentação de arquitetura (diagramas, decisões técnicas — ADRs)
- [ ] Post/artigo explicando as decisões técnicas (ótimo pra portfólio)

---

## 6. Boas práticas de AI Engineering a aplicar (e citar no repo)

1. **Prompts versionados, não hardcoded** — trate prompt como código: versão, changelog, testes de regressão.
2. **Avaliação contínua (evals)** — todo agente precisa de um dataset mínimo de casos de teste antes de "publicar". Sem eval, você não sabe se uma mudança de prompt melhorou ou piorou.
3. **Observabilidade desde o dia 1** — cada execução rastreável: input, output, tokens, custo, latência, decisões do roteador. Sem isso, debugar agente é adivinhação.
4. **Guardrails em duas pontas** — valide input (prompt injection, PII) e output (formato, conteúdo, alucinação óbvia) antes de devolver ao usuário.
5. **Least privilege em tools** — cada agente só tem acesso às tools que precisa; nunca execução de código arbitrário sem sandbox isolado.
6. **Custo como métrica de primeira classe** — trackear tokens/custo por run, não só depois que a fatura chegar.
7. **Determinismo onde dá** — regras/validações simples resolvidas com código (não LLM) sempre que possível; use o LLM só onde há ambiguidade real.
8. **Memória com limites explícitos** — defina o que entra na memória de longo prazo e por quanto tempo; memória sem curadoria vira ruído (e risco de vazamento entre sessões).
9. **Human-in-the-loop nos pontos certos** — ações irreversíveis (enviar email, deletar dado) passam por confirmação, usando os *interrupts* do LangGraph.
10. **Testes de regressão de agente** — trate o comportamento do agente como testável: dado input X, o agente deve (ou não deve) chamar a tool Y.

---

## 7. Estrutura sugerida do repositório

```
agentforge/
├── backend/
│   ├── app/
│   │   ├── api/            # rotas FastAPI
│   │   ├── graph/          # definição e interpretador do LangGraph
│   │   ├── models/         # schemas Pydantic + SQLAlchemy
│   │   ├── rag/            # ingestão, chunking, retrieval
│   │   ├── memory/         # short/long term memory
│   │   └── guardrails/     # validação input/output
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── builder/        # canvas React Flow
│   │   ├── chat/           # sandbox de teste
│   │   └── dashboard/      # traces/custos
├── infra/
│   ├── docker-compose.yml  # postgres, langfuse, backend, frontend
│   └── migrations/
└── docs/
    ├── architecture.md
    └── adr/                 # Architecture Decision Records
```

---

## 8. Próximo passo imediato

Concluir a **Fase 0** adicionando o stack Langfuse ao ambiente local, configurando as variáveis de ambiente de `.env.example` e capturando o primeiro trace do fluxo `LangGraph -> Ollama`. O cliente de tracing já está integrado, mas o Docker daemon precisa estar ativo para validar a ingestão. Depois, avançar para o interpretador de definições declarativas e o roteamento de modelos da Fase 1.

---

## 9. Fundação implementada

O esqueleto executável em `backend/` inclui schema declarativo Pydantic, runtime com o fluxo `memory -> plan -> act -> reflect`, regras de entrada e saída, registro controlado de tools, gateway MCP com allowlist, uma API FastAPI e um grafo LangGraph mínimo com adaptador para Ollama.

Também foram incluídos testes do fluxo, bloqueio por regra, confirmação de tools sensíveis, isolamento de memória por usuário, execução do grafo com modelo local e instrumentação opcional para Langfuse. O PostgreSQL com pgvector está configurado em `infra/docker-compose.yml`.

Legenda do roadmap: `[x]` concluído, `[~]` parcialmente concluído, `[ ]` pendente.

### Executar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
docker compose -f infra/docker-compose.yml up -d
uvicorn app.main:app --app-dir backend --reload
```

Para habilitar o tracing, copie `.env.example` para `.env` e preencha as chaves do Langfuse. Sem as duas chaves, o cliente permanece desabilitado. O painel local do Langfuse fica em `http://localhost:3001`.

Para aplicar o schema inicial no Postgres da Edda Agents:

```bash
docker compose -f infra/docker-compose.yml exec -T postgres psql -U agentforge -d agentforge -f - < infra/migrations/001_initial.sql
```

Para iniciar a sandbox React em desenvolvimento:

```bash
cd frontend
npm install
npm run dev
```

A sandbox fica em `http://localhost:5173` e consome a API em `http://localhost:8000`.

Para subir o ambiente completo containerizado, incluindo backend e frontend:

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

O projeto Docker usa o nome `agent-forge`, então os containers aparecem como `agent-forge-backend-1`, `agent-forge-frontend-1` e assim por diante. URLs locais: frontend em `http://localhost:5173`, API em `http://localhost:8000` e Langfuse em `http://localhost:3001`.

API: `GET /health` e `POST /v1/agents/run`.

```bash
pytest
```