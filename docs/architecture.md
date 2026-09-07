# Arquitetura inicial

## Fluxo de execucao

1. A API recebe uma definicao declarativa do agente e uma mensagem.
2. O runtime aplica regras de entrada e recupera memoria da thread e do usuario.
3. O planejador escolhe uma tool permitida ou uma resposta direta.
4. A acao executa somente uma tool registrada; as tools de producao rodam em containers efemeros sem rede, com filesystem somente leitura e limites de recursos. MCP passa pela allowlist do gateway.
5. A reflexao forma a resposta final e aplica regras de saida.
6. O estado da execucao e persistido pelo checkpointer do LangGraph, separado por `thread_id`.

## Limites atuais

- `InMemoryStore` e um adaptador de desenvolvimento para memoria de longo prazo. O estado de curto prazo da execucao usa `PostgresSaver` quando `DATABASE_URL` esta configurada.
- `McpGateway` define a fronteira de autorizacao; o cliente de transporte MCP sera conectado depois.
- O planejador deterministico permite testes sem provedor de LLM. Um adaptador LangGraph/LLM pode preservar o contrato `AgentRuntime`.
- O Compose local monta o socket Docker no backend para criar containers de tools. Em producao, esse acesso deve ser substituido por um executor remoto com permissao restrita para criar somente imagens de tools aprovadas.
