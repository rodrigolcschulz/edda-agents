from app.models.agent import ToolDescriptor
from app.tools.registry import ToolRegistry


def test_registry_lists_registered_tools_with_metadata() -> None:
    registry = ToolRegistry()
    registry.register(
        "transcribe",
        lambda _argument: "transcript",
        ToolDescriptor(
            name="transcribe",
            display_name="Audio transcription",
            description="Transcribes audio.",
            source="native",
            output_type="transcript",
        ),
    )

    descriptors = registry.list_descriptors()

    assert [descriptor.name for descriptor in descriptors] == ["transcribe"]
    assert descriptors[0].source == "native"
    assert descriptors[0].output_type == "transcript"