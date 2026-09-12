from dataclasses import dataclass
from decimal import Decimal
import os


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    input_per_million: Decimal
    output_per_million: Decimal
    currency: str = "USD"


# Prices are deliberately kept in code/config so they can be reviewed and versioned.
DEFAULT_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing("openai", Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": ModelPricing("openai", Decimal("2.50"), Decimal("10.00")),
    "qwen3:14b": ModelPricing("ollama", Decimal("0"), Decimal("0")),
    "local-deterministic": ModelPricing("local", Decimal("0"), Decimal("0")),
}


def pricing_for(model: str) -> ModelPricing | None:
    return DEFAULT_PRICING.get(model.casefold())


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    pricing = pricing_for(model)
    if pricing is None:
        return None
    return (
        Decimal(input_tokens) * pricing.input_per_million
        + Decimal(output_tokens) * pricing.output_per_million
    ) / Decimal(1_000_000)


def pricing_version() -> str:
    return os.getenv("MODEL_PRICING_VERSION", "2026-09-local-1")
