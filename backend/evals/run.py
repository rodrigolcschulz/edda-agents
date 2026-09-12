import argparse
import json
from pathlib import Path

from app.graph.hello import OpenAIModel, OllamaModel, deterministic_model
from app.graph.runtime import AgentRuntime
from app.memory.store import InMemoryStore
from app.models.agent import AgentDefinition, RunRequest
from app.observability.langfuse import AgentEvaluator, load_eval_cases
from app.tools.registry import ToolRegistry


ROOT = Path(__file__).parents[2]
DEFAULT_DATASET = ROOT / "backend" / "evals" / "datasets" / "support.json"


def build_model(name: str):
    models = {
        "local-deterministic": deterministic_model,
        "qwen3:14b": OllamaModel("qwen3:14b"),
        "gpt-4o-mini": OpenAIModel("gpt-4o-mini"),
    }
    try:
        return models[name]
    except KeyError as error:
        raise ValueError(f"Unsupported evaluation model: {name}") from error


def evaluate(model_name: str, dataset_path: Path):
    runtime = AgentRuntime(
        tools=ToolRegistry(),
        memory=InMemoryStore(),
        models={model_name: build_model(model_name)},
    )
    agent = AgentDefinition(
        id="support-eval",
        name="Support evaluation",
        system_prompt="Answer support questions clearly and safely.",
        model=model_name,
    )
    cases = load_eval_cases(dataset_path)
    evaluator = AgentEvaluator(
        lambda message: runtime.run(
            agent,
            RunRequest(
                thread_id=f"eval-{message}",
                user_id="evaluation",
                message=message,
            ),
        ).answer
    )
    return cases, evaluator.evaluate(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the versioned agent evaluation dataset.")
    parser.add_argument("--model", default="local-deterministic")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()

    cases, results = evaluate(args.model, args.dataset)
    pass_rate = AgentEvaluator.pass_rate(results)
    print(json.dumps({
        "model": args.model,
        "dataset": str(args.dataset),
        "cases": len(cases),
        "pass_rate": pass_rate,
        "results": [
            {"name": result.name, "passed": result.passed, "score": result.score}
            for result in results
        ],
    }, indent=2))
    return 0 if pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
