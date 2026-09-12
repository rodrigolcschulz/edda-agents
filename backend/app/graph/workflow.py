import json
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from app.graph.runtime import AgentRuntime
from app.models.agent import AgentDefinition, RunRequest
from app.models.workflow import (
    Artifact,
    NodeRun,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowRun,
    WorkflowRunResponse,
)
from app.observability.runs import RunStore


AgentResolver = Callable[[str], AgentDefinition]


class WorkflowRuntime:
    def __init__(self, agent_runtime: AgentRuntime, resolve_agent: AgentResolver, run_store: RunStore | None = None) -> None:
        self._agent_runtime = agent_runtime
        self._resolve_agent = resolve_agent
        self._run_store = run_store

    def run(self, workflow: WorkflowDefinition, input_data: Mapping[str, Any], user_id: str = "workflow-user") -> WorkflowRunResponse:
        workflow_run = WorkflowRun(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status="running",
            input=dict(input_data),
        )
        started_at = perf_counter()
        if self._run_store:
            self._run_store.start_workflow(workflow, workflow_run, user_id)
        try:
            ordered_nodes = self._linear_order(workflow)
            artifacts: dict[str, Artifact] = {}
            for node in ordered_nodes:
                workflow_run.current_node = node.id
                node_started_at = perf_counter()
                message = self._build_node_message(node, workflow_run.input, artifacts)
                agent = self._resolve_agent(node.agent_id)
                response = self._agent_runtime.run(
                    agent,
                    RunRequest(
                        thread_id=f"{workflow_run.id}:{node.id}",
                        user_id=user_id,
                        message=message,
                        metadata={
                            "workflow_id": workflow.id,
                            "parent_run_id": workflow_run.id,
                            "parent_trace_id": workflow_run.trace_id,
                        },
                    ),
                )
                if response.status != "completed":
                    raise RuntimeError(f"Workflow node '{node.id}' ended with status '{response.status}'.")

                input_artifact_ids = [artifact.id for artifact in artifacts.values()]
                artifact = Artifact(
                    type=f"{node.id}-output",
                    content=response.answer,
                    source_node_id=node.id,
                )
                artifacts[node.id] = artifact
                workflow_run.artifacts.append(artifact)
                workflow_run.node_runs.append(
                    NodeRun(
                        workflow_run_id=workflow_run.id,
                        node_id=node.id,
                        agent_run_id=response.run_id,
                        status=response.status,
                        model_name=response.model_name,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        total_tokens=response.total_tokens,
                        estimated_cost=response.estimated_cost,
                        cost_currency=response.cost_currency,
                        duration_ms=(perf_counter() - node_started_at) * 1000,
                        input_artifact_ids=input_artifact_ids,
                        output_artifact_ids=[artifact.id],
                        trace_id=response.trace_id,
                    )
                )
                self._accumulate_usage(workflow_run, response)

            output = artifacts[workflow.output_node]
            workflow_run.output_artifact_id = output.id
            workflow_run.current_node = None
            workflow_run.status = "completed"
            workflow_run.duration_ms = (perf_counter() - started_at) * 1000
            if self._run_store:
                self._run_store.finish_workflow(workflow_run, output.content)
            return WorkflowRunResponse(run=workflow_run, output=output)
        except Exception as error:
            workflow_run.status = "failed"
            workflow_run.error = str(error)
            workflow_run.duration_ms = (perf_counter() - started_at) * 1000
            if self._run_store:
                self._run_store.fail_workflow(workflow_run)
            raise

    @staticmethod
    def _accumulate_usage(workflow_run: WorkflowRun, response: Any) -> None:
        workflow_run.input_tokens += response.input_tokens
        workflow_run.output_tokens += response.output_tokens
        workflow_run.total_tokens += response.total_tokens
        if response.estimated_cost is not None:
            workflow_run.estimated_cost = (workflow_run.estimated_cost or 0) + response.estimated_cost
        if response.model_name and response.model_name not in workflow_run.models_used:
            workflow_run.models_used.append(response.model_name)

    @staticmethod
    def _linear_order(workflow: WorkflowDefinition) -> list[WorkflowNode]:
        nodes = {node.id: node for node in workflow.nodes}
        if workflow.entry_node not in nodes or workflow.output_node not in nodes:
            raise ValueError("Workflow entry_node and output_node must reference existing nodes.")

        outgoing: dict[str, str] = {}
        for edge in workflow.edges:
            if edge.source_node_id in outgoing:
                raise ValueError("Only linear workflows are supported in this version.")
            if edge.source_node_id not in nodes or edge.target_node_id not in nodes:
                raise ValueError("Workflow edges must reference existing nodes.")
            outgoing[edge.source_node_id] = edge.target_node_id

        ordered: list[WorkflowNode] = []
        visited: set[str] = set()
        current = workflow.entry_node
        while current not in visited:
            visited.add(current)
            ordered.append(nodes[current])
            if current == workflow.output_node:
                break
            if current not in outgoing:
                raise ValueError("Workflow has no edge from a non-terminal node.")
            current = outgoing[current]

        if ordered[-1].id != workflow.output_node or len(ordered) != len(nodes):
            raise ValueError("Workflow must be a single linear path from entry_node to output_node.")
        return ordered

    @staticmethod
    def _build_node_message(
        node: WorkflowNode,
        input_data: dict[str, Any],
        artifacts: dict[str, Artifact],
    ) -> str:
        context: dict[str, Any] = {}
        for output_name, source in node.input_mapping.items():
            if source == "input":
                context[output_name] = input_data
            elif source in artifacts:
                context[output_name] = artifacts[source].content
            else:
                raise ValueError(f"Workflow node '{node.id}' references unknown input '{source}'.")
        if not context:
            context = {"input": input_data, "artifacts": {key: value.content for key, value in artifacts.items()}}
        return json.dumps(context, ensure_ascii=False, indent=2, default=str)
