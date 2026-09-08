import re
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


def _normalize_tokens(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    normalized: list[str] = []
    for token in tokens:
        token = token.strip()
        if len(token) <= 2:
            continue
        token = re.sub(r"(ing|ed|es|s)$", "", token)
        if token:
            normalized.append(token)
    return normalized


@dataclass
class MemoryFact:
    fact: str
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class DocumentRecord:
    source: str
    text: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryStore:
    """Development adapter; replace with Postgres/pgvector in production."""

    def __init__(self) -> None:
        self._threads: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._facts: dict[str, list[MemoryFact]] = defaultdict(list)
        self._documents: list[DocumentRecord] = []

    def recall(self, thread_id: str, user_id: str, query: str | None = None, limit: int = 5) -> list[str]:
        recent_messages = self._threads[(user_id, thread_id)][-limit:]
        recent_facts = self.search_facts(user_id, query or "", limit=limit)
        return [*recent_messages, *recent_facts]

    def remember_message(self, thread_id: str, user_id: str, message: str) -> None:
        self._threads[(user_id, thread_id)].append(message)

    def remember_fact(self, user_id: str, fact: str, ttl_seconds: float | None = None) -> None:
        if not fact:
            return
        expiry = None if ttl_seconds is None else time.time() + ttl_seconds
        if not any(existing.fact == fact and (existing.expires_at is None or existing.expires_at > time.time()) for existing in self._facts[user_id]):
            self._facts[user_id].append(MemoryFact(fact=fact, expires_at=expiry))

    def ingest_document(self, source: str, text: str, metadata: dict[str, Any] | None = None) -> DocumentRecord:
        document = DocumentRecord(source=source, text=text, metadata=metadata or {})
        self._documents.append(document)
        return document

    def search_documents(self, query: str, limit: int = 5) -> list[DocumentRecord]:
        if not query:
            return []
        scored: list[tuple[float, DocumentRecord]] = []
        query_tokens = _normalize_tokens(query)
        for document in self._documents:
            score = self._score_text(document.text, query_tokens)
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in scored[:limit]]

    def search_facts(self, user_id: str, query: str, limit: int = 5) -> list[str]:
        now = time.time()
        active_facts = [
            fact
            for fact in self._facts.get(user_id, [])
            if fact.expires_at is None or fact.expires_at > now
        ]
        if not active_facts:
            return []

        query_tokens = _normalize_tokens(query)
        scored = [
            (self._score_text(fact.fact, query_tokens), fact.fact)
            for fact in active_facts
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [fact_text for _, fact_text in scored if _ > 0][:limit]

    @staticmethod
    def _score_text(text: str, query_tokens: Sequence[str]) -> float:
        if not query_tokens:
            return 0.0
        document_tokens = _normalize_tokens(text)
        if not document_tokens:
            return 0.0
        document_set = set(document_tokens)
        overlap = sum(1 for token in query_tokens if token in document_set)
        if overlap == 0:
            return 0.0
        return overlap + (sum(1 for token in query_tokens if any(token in candidate for candidate in document_tokens)) * 0.1)
