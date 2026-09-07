from collections.abc import Sequence
from dataclasses import dataclass
import json
import subprocess


@dataclass(frozen=True)
class SandboxedTool:
    image: str
    command: tuple[str, ...]
    timeout_seconds: float = 10.0
    memory: str = "128m"
    cpus: str = "0.5"


class DockerToolSandbox:
    def execute(self, tool: SandboxedTool, argument: str) -> str:
        command: Sequence[str] = (
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            tool.memory,
            "--cpus",
            tool.cpus,
            "--user",
            "65534:65534",
            tool.image,
            *tool.command,
        )
        try:
            completed = subprocess.run(
                command,
                input=json.dumps({"argument": argument}),
                text=True,
                capture_output=True,
                check=True,
                timeout=tool.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"Tool exceeded its {tool.timeout_seconds:g}-second limit.") from error
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or "Tool container exited with an error."
            raise RuntimeError(detail) from error

        return completed.stdout.strip()