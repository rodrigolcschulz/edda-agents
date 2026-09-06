from app.models.agent import AgentRule, RuleStage


class RuleViolation(ValueError):
    pass


def enforce_rules(text: str, rules: list[AgentRule], stage: RuleStage) -> None:
    normalized = text.casefold()
    for rule in rules:
        if rule.stage != stage:
            continue
        if any(term.casefold() in normalized for term in rule.blocked_terms):
            raise RuleViolation(f"Rule '{rule.name}' blocked the {stage}.")
