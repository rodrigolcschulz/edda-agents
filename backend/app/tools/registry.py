from collections.abc import Callable

from app.models.agent import ToolDescriptor
from app.tools.sandbox import DockerToolSandbox, SandboxedTool


ToolHandler = Callable[[str], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._sandboxed_tools: dict[str, SandboxedTool] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._sandbox = DockerToolSandbox()

    def register(self, name: str, handler: ToolHandler, descriptor: ToolDescriptor | None = None) -> None:
        self._handlers[name] = handler
        self._descriptors[name] = descriptor or ToolDescriptor(
            name=name,
            display_name=name.replace("_", " ").title(),
            description="Registered native tool",
            source="native",
            output_type="text",
        )

    def register_sandboxed(self, name: str, tool: SandboxedTool, descriptor: ToolDescriptor | None = None) -> None:
        self._sandboxed_tools[name] = tool
        self._descriptors[name] = descriptor or ToolDescriptor(
            name=name,
            display_name=name.replace("_", " ").title(),
            description="Registered sandboxed tool",
            source="sandbox",
            output_type="text",
        )

    def list_descriptors(self) -> list[ToolDescriptor]:
        return sorted(self._descriptors.values(), key=lambda descriptor: descriptor.name)

    def execute(self, name: str, argument: str) -> str:
        try:
            if name in self._sandboxed_tools:
                return self._sandbox.execute(self._sandboxed_tools[name], argument)
            return self._handlers[name](argument)
        except KeyError as error:
            raise ValueError(f"Tool '{name}' is not registered.") from error
