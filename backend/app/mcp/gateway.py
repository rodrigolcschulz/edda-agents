from app.models.agent import McpServerDefinition
from app.tools.registry import ToolRegistry


class McpGateway:
    """Allowlisted MCP tool facade; transport adapters belong behind this class."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, server: McpServerDefinition, tool_name: str, argument: str) -> str:
        if tool_name not in server.allowed_tools:
            raise PermissionError(f"Tool '{tool_name}' is not allowed by MCP server '{server.name}'.")
        return self._registry.execute(tool_name, argument)
