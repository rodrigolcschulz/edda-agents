# Arquitetura inicial

## Fluxo de execucao

1. A API recebe uma definicao declarativa do agente e uma mensagem.
2. O runtime aplica regras de entrada e recupera memoria da thread e do usuario.
3. O planejador escolhe uma tool permitida ou uma resposta direta.
4. A acao executa somente uma tool registrada; MCP passa pela allowlist do gateway.
5. A reflexao forma a resposta final e aplica regras de saida.
6. A mensagem e adicionada a memoria de curto prazo da thread.

## Limites atuais

- `InMemoryStore` e um adaptador de desenvolvimento. Postgres e pgvector o substituirao em producao.
- `McpGateway` define a fronteira de autorizacao; o cliente de transporte MCP sera conectado depois.
- O planejador deterministico permite testes sem provedor de LLM. Um adaptador LangGraph/LLM pode preservar o contrato `AgentRuntime`.
