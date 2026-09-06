from collections import defaultdict


class InMemoryStore:
    """Development adapter; replace with Postgres/pgvector in production."""

    def __init__(self) -> None:
        self._threads: dict[str, list[str]] = defaultdict(list)
        self._facts: dict[str, list[str]] = defaultdict(list)

    def recall(self, thread_id: str, user_id: str) -> list[str]:
        return [*self._threads[thread_id][-5:], *self._facts[user_id][-5:]]

    def remember_message(self, thread_id: str, message: str) -> None:
        self._threads[thread_id].append(message)

    def remember_fact(self, user_id: str, fact: str) -> None:
        if fact not in self._facts[user_id]:
            self._facts[user_id].append(fact)
