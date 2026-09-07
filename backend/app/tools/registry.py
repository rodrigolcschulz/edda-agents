from collections.abc import Callable

from app.tools.sandbox import DockerToolSandbox, SandboxedTool


ToolHandler = Callable[[str], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._sandboxed_tools: dict[str, SandboxedTool] = {}
        self._sandbox = DockerToolSandbox()

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def register_sandboxed(self, name: str, tool: SandboxedTool) -> None:
        self._sandboxed_tools[name] = tool

    def execute(self, name: str, argument: str) -> str:
        try:
            if name in self._sandboxed_tools:
                return self._sandbox.execute(self._sandboxed_tools[name], argument)
            return self._handlers[name](argument)
        except KeyError as error:
            raise ValueError(f"Tool '{name}' is not registered.") from error
