"""Small local embedding helpers for matching MVP.

The default implementation is deterministic hash embedding for offline tests
and local experiments. It is not meant to be a semantic model replacement, but
it keeps the scoring interface ready for a real embedding provider later.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


FAKE_EMBEDDING_MODEL = "fake-hash-v1"


@dataclass
class EmbeddingCacheStats:
    hit_count: int = 0
    miss_count: int = 0


class EmbeddingCache:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self.stats = EmbeddingCacheStats()
        self._records: dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._records = dict(payload.get("records", {}))
            except (OSError, json.JSONDecodeError, TypeError):
                self._records = {}

    @staticmethod
    def key(mentor_id: str, record_hash: str, embedding_model: str) -> str:
        return f"{mentor_id}|{record_hash}|{embedding_model}"

    def get(self, mentor_id: str, record_hash: str, embedding_model: str) -> list[float] | None:
        record = self._records.get(self.key(mentor_id, record_hash, embedding_model))
        if not record:
            self.stats.miss_count += 1
            return None
        embedding = record.get("embedding")
        if not isinstance(embedding, list):
            self.stats.miss_count += 1
            return None
        self.stats.hit_count += 1
        return [float(value) for value in embedding]

    def set(self, mentor_id: str, record_hash: str, embedding_model: str, embedding: list[float]) -> None:
        self._records[self.key(mentor_id, record_hash, embedding_model)] = {
            "mentor_id": mentor_id,
            "record_hash": record_hash,
            "embedding_model": embedding_model,
            "embedding": embedding,
        }

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": self._records}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fake_hash_embedding(text: str, *, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    tokens = [token for token in text.lower().split() if token.strip()]
    if not tokens:
        tokens = [text.lower()]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def get_embedding(text: str, *, method: str = "fake", embedding_model: str | None = None) -> list[float]:
    if method == "fake":
        return fake_hash_embedding(text)
    if method == "real":
        raise NotImplementedError("real embedding provider is not configured")
    raise ValueError(f"unsupported embedding method: {method}")


__all__ = [
    "EmbeddingCache",
    "EmbeddingCacheStats",
    "FAKE_EMBEDDING_MODEL",
    "cosine_similarity",
    "fake_hash_embedding",
    "get_embedding",
]
