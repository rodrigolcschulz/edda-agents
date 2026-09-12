# Blueprint de historico, metricas e observabilidade

## 1. Objetivo

Criar uma camada de historico e observabilidade que permita responder duas perguntas diferentes:

1. **Operacao do produto:** quantas vezes cada agente foi chamado, qual foi o status, qual modelo foi usado, quantos tokens foram consumidos e qual foi o custo estimado.
2. **Investigacao tecnica:** o que aconteceu dentro de uma execucao, quais nos e tools foram usados, quais prompts e respostas foram produzidos, onde houve lentidao ou falha e como o resultado pode ser melhorado.

A primeira pergunta deve ser atendida pelo backend e pelo frontend. A segunda deve ser atendida principalmente pelo Langfuse, com links a partir do frontend.

## 2. Trace nao e a mesma coisa que historico

Os conceitos devem ser separados:

```text
Workflow run ou Agent run
    Uma execucao de negocio do sistema.

Trace
    O registro tecnico completo de uma execucao, do inicio ao fim.

Span
    Uma etapa dentro do trace, como memoria, retrieval, tool ou agente.

Generation
    Uma chamada especifica a um modelo, com tokens, modelo, input e output.

Metricas agregadas
    Contagens e somas calculadas sobre muitos runs, como chamadas por agente e custo mensal.
```

Exemplo para um agente individual:

```text
Agent run: run-123
└── Trace: trace-abc
    ├── Span: input_guardrail
    ├── Span: memory
    ├── Generation: qwen3:14b
    ├── Span: tool echo
    └── Generation: qwen3:14b
```

Exemplo para um workflow multiagente:

```text
Workflow run: workflow-run-456
└── Trace: trace-workflow-xyz
    ├── Span: transcription node
    │   └── Generation ou tool execution
    ├── Span: project manager node
    │   └── Generation: qwen3:14b
    ├── Span: developer node
    │   └── Generation: qwen3:14b
    └── Span: test node
        └── Tool execution
```

O trace explica uma execucao. O historico permite consultar muitas execucoes. O frontend nao deve tentar substituir o trace detalhado do Langfuse.

## 3. Decisao arquitetural

### Postgres: fonte de historico do produto

O Postgres deve armazenar dados estaveis, filtraveis e necessarios para a experiencia do produto:

- identificador do run;
- agente e versao;
- workflow e versao, quando aplicavel;
- status;
- modelo principal usado;
- tokens de entrada e saida;
- custo estimado;
- duracao;
- usuario e tenant;
- referencia do trace no Langfuse;
- timestamps;
- erro resumido, sem armazenar secrets.

Esses dados permitem montar dashboards mesmo quando o Langfuse estiver desabilitado, indisponivel ou com politica de retencao diferente.

### Langfuse: fonte de observabilidade detalhada

O Langfuse deve armazenar e exibir:

- trace completo;
- spans por etapa;
- generations por chamada de modelo;
- prompts e respostas, conforme politica de privacidade;
- tokens por generation;
- latencia por etapa;
- tools utilizadas;
- metadados de modelo;
- scores e avaliacao;
- erros e contexto tecnico.

O backend deve enviar links ou IDs do Langfuse para que o frontend abra a investigacao detalhada sem replicar toda a interface do Langfuse.

## 4. Modelo de dados recomendado

### `runs`

Representa uma execucao de produto de um agente ou workflow.

```text
id
kind: agent | workflow
agent_id nullable
agent_version nullable
workflow_id nullable
workflow_version nullable
thread_id
user_id nullable
tenant_id nullable
status: running | completed | failed | blocked | cancelled
model_name nullable
input_tokens integer default 0
output_tokens integer default 0
total_tokens integer default 0
estimated_cost numeric default 0
duration_ms integer nullable
trace_id nullable
error_code nullable
error_message nullable
started_at
finished_at nullable
created_at
```

### `run_generations`

Representa cada chamada individual a um modelo.

```text
id
run_id
node_id nullable
agent_id nullable
model_name
input_tokens
output_tokens
total_tokens
estimated_cost
latency_ms
provider
created_at
```

### `run_steps`

Representa etapas que nao sao necessariamente chamadas de modelo.

```text
id
run_id
node_id nullable
kind: guardrail | memory | retrieval | tool | transform | approval | generation
name
status
duration_ms
metadata jsonb
started_at
finished_at
```

Para workflows, `run_steps` pode apontar para `agent_id`, `tool_name` e artefatos de entrada e saida.

## 5. Contrato de identificacao

Todo run deve carregar identificadores consistentes:

```json
{
  "run_id": "run-123",
  "trace_id": "trace-abc",
  "agent_id": "project-manager",
  "agent_version": 1,
  "workflow_id": "issue-resolution",
  "workflow_version": 1,
  "node_id": "project-manager-node",
  "thread_id": "thread-456"
}
```

Regras:

- `run_id` identifica a execucao no produto.
- `trace_id` identifica a investigacao tecnica no Langfuse.
- `agent_id` nunca deve depender apenas do nome exibido.
- `agent_version` deve ser preservada para reproducibilidade.
- Um workflow deve ter um trace pai.
- Cada agente, tool e generation deve ser relacionado ao run pai.

## 6. Estado atual do repositorio

O repositorio ja possui uma integracao inicial com Langfuse em [backend/app/observability/langfuse.py](../backend/app/observability/langfuse.py) e o runtime registra uma generation em [backend/app/graph/runtime.py](../backend/app/graph/runtime.py).

Antes de considerar a observabilidade pronta, ainda e necessario corrigir ou evoluir estes pontos:

- enviar `agent_id` e `agent_version` nos metadados;
- criar e reutilizar um `run_id` explicito;
- manter um `trace_id` consistente durante o run;
- registrar cada generation, nao somente o resultado final do ciclo;
- acumular tokens de todos os ciclos;
- registrar tools, retrieval, guardrails e erros;
- calcular custo por modelo e provedor;
- persistir um resumo em Postgres;
- criar endpoints para historico e agregacoes;
- criar links do frontend para o trace detalhado.

Atualmente, o custo enviado ao Langfuse esta zerado para o ambiente local. Isso e aceitavel para Ollama, mas nao deve ser tratado como calculo geral de custo para provedores pagos.

## 7. API proposta

### Listar runs

```http
GET /v1/runs?agent_id=project-manager&status=completed&from=2026-09-01&to=2026-09-12
```

Resposta resumida:

```json
{
  "items": [
    {
      "id": "run-123",
      "kind": "agent",
      "agent_id": "project-manager",
      "agent_version": 1,
      "status": "completed",
      "model_name": "qwen3:14b",
      "total_tokens": 1820,
      "estimated_cost": 0,
      "duration_ms": 4200,
      "trace_id": "trace-abc",
      "started_at": "2026-09-12T10:00:00Z"
    }
  ],
  "next_cursor": null
}
```

### Detalhar um run

```http
GET /v1/runs/{run_id}
```

Deve retornar o resumo, as etapas, as generations, os erros e o link ou identificador do trace no Langfuse.

### Agregacoes por agente

```http
GET /v1/analytics/agents?from=2026-09-01&to=2026-09-12
```

Resposta esperada:

```json
{
  "items": [
    {
      "agent_id": "project-manager",
      "calls": 42,
      "successful_calls": 39,
      "failed_calls": 3,
      "total_tokens": 78400,
      "estimated_cost": 1.24,
      "average_duration_ms": 3100,
      "models": ["qwen3:14b"]
    }
  ]
}
```

As agregacoes devem ser calculadas no backend, com filtros por tenant e paginacao quando necessario. O frontend nao deve consultar diretamente o banco nem depender de parsing da interface do Langfuse.

## 8. Frontend recomendado

Criar uma secao `History` ou `Analytics` com tres niveis:

### Visao geral

- total de runs;
- runs por agente;
- taxa de sucesso;
- tokens consumidos;
- custo estimado;
- latencia media;
- distribuicao por modelo.

### Lista de execucoes

- data e hora;
- agente ou workflow;
- versao;
- status;
- modelo;
- tokens;
- custo;
- duracao;
- link `Open trace`.

### Detalhe do run

- entrada resumida;
- saida resumida;
- etapas executadas;
- tools chamadas;
- generations;
- erros;
- artefatos;
- link para o trace completo no Langfuse.

O frontend deve evitar mostrar prompts e respostas sensiveis por padrao. O detalhe completo deve respeitar permissoes, tenant e politicas de retencao.

## 9. Tokens e custo

Cada chamada de modelo deve registrar separadamente:

```text
input_tokens
output_tokens
total_tokens
model_name
provider
latency_ms
estimated_cost
```

O custo deve ser calculado por uma tabela de precos versionada:

```text
Pricing
- provider
- model
- input_price_per_1k
- output_price_per_1k
- currency
- effective_from
- effective_to
```

Para modelos locais:

- custo financeiro pode ser `0`;
- tokens continuam sendo registrados;
- latencia e consumo de recursos continuam relevantes;
- opcionalmente, pode ser calculado custo operacional estimado de CPU/GPU.

Nao se deve somar tokens de um run usando somente o ultimo resultado de um loop. Cada generation deve contribuir para o acumulado do run.

## 10. Privacidade e seguranca

Observabilidade pode conter dados sensiveis. As regras minimas sao:

- nao registrar tokens, chaves ou secrets;
- aplicar redacao de PII antes de enviar prompts ao Langfuse quando necessario;
- definir politica de retencao para input e output;
- separar metadados de produto de conteudo sensivel;
- aplicar autorizacao por tenant;
- limitar quem pode abrir traces completos;
- registrar auditoria de acesso a traces sensiveis;
- evitar colocar audio bruto em logs ou traces;
- armazenar somente referencias seguras aos arquivos.

## 11. Roadmap de implementacao

### Fase O1 - Fundacao de identificadores

- [x] Criar `run_id` no inicio de cada execucao.
- [x] Criar contexto de observabilidade com `run_id`, `trace_id`, `agent_id` e versao.
- [x] Propagar o contexto para runtime, tools e Langfuse.
- [x] Corrigir o trace para usar um identificador consistente.
- [x] Adicionar testes de propagacao dos identificadores.

### Fase O2 - Instrumentacao completa

- [~] Registrar cada generation individual. O run agora envia o uso agregado; o detalhamento de cada generation ainda falta.
- [x] Acumular tokens de todos os ciclos.
- [ ] Registrar tools, retrieval, memoria, guardrails e erros.
- [ ] Medir duracao por etapa.
- [ ] Adicionar metadata de workflow e node para o futuro runtime multiagente.

### Fase O3 - Historico persistido

- [~] Criar migration para `runs`, `run_generations` e `run_steps`. A migration incremental e o setup compativel ja existem.
- [x] Persistir inicio, sucesso e falha. Cancelamento ainda falta.
- [ ] Implementar idempotencia para nao duplicar finalizacao de run.
- [x] Criar indices por agente, status e data.
- [x] Manter `trace_id` como referencia externa.

### Fase O4 - API e agregacoes

- [ ] Criar endpoint de listagem de runs.
- [ ] Criar endpoint de detalhe.
- [ ] Criar agregacoes por agente, modelo e periodo.
- [ ] Adicionar filtros por tenant e autorizacao.
- [ ] Criar calculo de custo por tabela de precos.

### Fase O5 - Frontend

- [ ] Criar tela de historico.
- [ ] Criar cards de metricas agregadas.
- [ ] Criar filtros de agente, modelo, status e periodo.
- [ ] Criar detalhe de run.
- [ ] Adicionar link para abrir o trace no Langfuse.
- [ ] Mostrar aviso quando custo ou tokens estiverem indisponiveis.

### Fase O6 - Workflows multiagente

- [ ] Criar trace pai para cada workflow.
- [ ] Criar spans por node.
- [ ] Relacionar cada node agent/tool ao run pai.
- [ ] Agregar tokens e custo do workflow e por agente.
- [ ] Mostrar timeline de etapas no frontend.
- [ ] Permitir abrir o trace detalhado de cada etapa no Langfuse.

## 12. Criterios de sucesso

A implementacao pode ser considerada suficiente quando:

- cada run possui `run_id`, agente, versao, status e duracao;
- cada generation possui modelo e tokens de entrada e saida;
- o acumulado de tokens inclui todos os ciclos;
- o custo e calculado de forma explicita ou marcado como indisponivel;
- o frontend lista historico e agregacoes sem acessar diretamente o Langfuse;
- cada item do historico possui link para investigacao detalhada;
- traces respeitam autorizacao e politica de dados;
- workflows multiagente aparecem como trace pai com etapas filhas.

## 13. Recomendacao final

Usar uma arquitetura hibrida:

```text
Postgres + API + frontend
    Historico, metricas de produto e dashboards resumidos

Langfuse
    Traces detalhados, generations, debugging e avaliacao
```

O trace e uma parte da observabilidade de uma execucao. Ele nao substitui o historico persistido nem as metricas agregadas do produto. Para o projeto, a ordem recomendada e: primeiro padronizar identificadores e instrumentacao, depois persistir runs, em seguida criar a API e o frontend de historico, e por fim integrar essa estrutura aos workflows multiagente.
