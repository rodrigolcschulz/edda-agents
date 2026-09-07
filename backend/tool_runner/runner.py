import json
import sys


def echo(argument: str) -> str:
    return f"Tool result: {argument}"


def main() -> None:
    tool_name = sys.argv[1] if len(sys.argv) == 2 else ""
    tools = {"echo": echo}
    if tool_name not in tools:
        raise SystemExit(f"Tool '{tool_name}' is not available.")
    payload = json.load(sys.stdin)
    print(tools[tool_name](payload["argument"]))


if __name__ == "__main__":
    main()