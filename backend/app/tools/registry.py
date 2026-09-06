from collections.abc import Callable


ToolHandler = Callable[[str], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def execute(self, name: str, argument: str) -> str:
        try:
            return self._handlers[name](argument)
        except KeyError as error:
            raise ValueError(f"Tool '{name}' is not registered.") from error
