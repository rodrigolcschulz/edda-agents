from pathlib import Path

from app.artifacts.store import ArtifactStore
from app.graph.runtime import AgentRuntime
from app.graph.workflow import WorkflowRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition
from app.models.workflow import Artifact, WorkflowDefinition, WorkflowNode
from app.tools.registry import ToolRegistry


class FakeS3Client:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}

    def head_bucket(self, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise RuntimeError("Bucket does not exist")

    def create_bucket(self, Bucket: str) -> None:
        self.buckets.add(Bucket)

    def upload_fileobj(self, source, bucket: str, key: str, ExtraArgs: dict[str, str]) -> None:
        object_id = (bucket, key)
        self.objects[object_id] = source.read()
        self.content_types[object_id] = ExtraArgs["ContentType"]

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        object_id = (Bucket, Key)
        self.objects[object_id] = Body
        self.content_types[object_id] = ContentType


def test_persists_uploaded_file_metadata_and_checksum(tmp_path: Path) -> None:
    audio = tmp_path / "problem.wav"
    audio.write_bytes(b"audio-bytes")
    s3 = FakeS3Client()
    store = ArtifactStore(bucket="test-artifacts", s3_client=s3)

    record = store.store_file(audio, "folder/problem.wav", "audio/wav")

    assert record["kind"] == "input_file"
    assert record["filename"] == "problem.wav"
    assert record["size_bytes"] == len(b"audio-bytes")
    assert record["sha256"] == "15241589c52e7c4a511a160e040d12bab503cf5d0f586cba94889e554d8df241"
    assert s3.objects[("test-artifacts", record["object_key"])] == b"audio-bytes"
    assert store.get_metadata(record["id"]) == record


def test_persists_workflow_output_and_links_it_to_run() -> None:
    s3 = FakeS3Client()
    store = ArtifactStore(bucket="test-artifacts", s3_client=s3)
    artifact = Artifact(type="transcript", content={"text": "hello"}, source_node_id="transcribe")

    stored = store.store_content(artifact, "run-123")

    assert stored.bucket == "test-artifacts"
    assert stored.object_key == f"runs/run-123/artifacts/{artifact.id}.json"
    assert stored.size_bytes == len(b'{"text": "hello"}')
    assert s3.objects[(stored.bucket, stored.object_key)] == b'{"text": "hello"}'
    assert ("run-123", artifact.id, "output") in store._links


def test_workflow_persists_outputs_and_links_input_file(tmp_path: Path) -> None:
    s3 = FakeS3Client()
    store = ArtifactStore(bucket="test-artifacts", s3_client=s3)
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"audio")
    source = store.store_file(audio, audio.name, "audio/wav")
    agent = AgentDefinition(id="planner", name="Planner", system_prompt="Plan the work.")
    runtime = AgentRuntime(tools=ToolRegistry(), memory=InMemoryStore(), model=lambda _prompt: "plan")
    workflow = WorkflowDefinition(
        id="audio-plan",
        name="Audio plan",
        nodes=[WorkflowNode(id="plan", kind="agent", agent_id="planner")],
        entry_node="plan",
        output_node="plan",
    )

    result = WorkflowRuntime(runtime, lambda _: agent, artifact_store=store).run(
        workflow,
        {"problem": "Plan this", "source_artifact_id": source["id"]},
    )

    assert result.output.bucket == "test-artifacts"
    assert result.output.sha256
    assert (result.run.id, source["id"], "input") in store._links
    assert (result.run.id, result.output.id, "output") in store._links
    assert result.run.node_runs[0].input_artifact_ids == [source["id"]]