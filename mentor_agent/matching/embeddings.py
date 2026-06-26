"""Small local embedding helpers for matching MVP.

The default implementation is deterministic hash embedding for offline tests
and local experiments. It is not meant to be a semantic model replacement, but
it keeps the scoring interface ready for a real embedding provider later.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import requests


FAKE_EMBEDDING_MODEL = "fake-hash-v1"
DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_REAL_EMBEDDING_TIMEOUT = 30
_LOCAL_MODELS: dict[str, object] = {}


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


def safe_model_name(model_name: str | None) -> str:
    text = str(model_name or DEFAULT_LOCAL_EMBEDDING_MODEL).strip()
    safe = []
    for char in text:
        safe.append(char if char.isalnum() else "_")
    return "_".join(part for part in "".join(safe).split("_") if part).lower()


def default_local_embedding_cache_path(model_name: str | None) -> Path:
    return Path("outputs") / "matching_embeddings" / f"mentor_embeddings_{safe_model_name(model_name)}.json"


def local_embedding(text: str, *, embedding_model: str | None = None) -> list[float]:
    model_name = embedding_model or DEFAULT_LOCAL_EMBEDDING_MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "semantic local requires sentence-transformers. "
            "Install it with: python -m pip install sentence-transformers"
        ) from exc

    model = _LOCAL_MODELS.get(model_name)
    if model is None:
        try:
            model = SentenceTransformer(model_name)
        except Exception as exc:
            raise RuntimeError(f"semantic local embedding model unavailable: {model_name}") from exc
        _LOCAL_MODELS[model_name] = model

    try:
        vector = model.encode(text, normalize_embeddings=True)
    except TypeError:
        vector = model.encode(text)
    except Exception as exc:
        raise RuntimeError(f"semantic local embedding failed for model: {model_name}") from exc
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    if vector and isinstance(vector[0], list):
        vector = vector[0]
    if not isinstance(vector, list) or not vector:
        raise RuntimeError(f"semantic local embedding failed for model: {model_name}")
    return [float(value) for value in vector]


def _embedding_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/embeddings"):
        return base
    return f"{base}/embeddings"


def real_embedding(text: str, *, embedding_model: str | None = None) -> list[float]:
    model = embedding_model or os.getenv("EMBEDDING_MODEL")
    base_url = (
        os.getenv("EMBEDDING_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
    )
    if not model or not base_url:
        raise RuntimeError("real embedding provider not available")
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
    timeout = float(os.getenv("EMBEDDING_TIMEOUT", str(DEFAULT_REAL_EMBEDDING_TIMEOUT)))
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.post(
            _embedding_endpoint(base_url),
            headers=headers,
            json={"model": model, "input": text},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload["data"][0]["embedding"]
    except Exception as exc:
        raise RuntimeError("real embedding provider not available") from exc
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("real embedding provider not available")
    return [float(value) for value in embedding]


def get_embedding(text: str, *, method: str = "fake", embedding_model: str | None = None) -> list[float]:
    if method == "fake":
        return fake_hash_embedding(text)
    if method == "local":
        return local_embedding(text, embedding_model=embedding_model)
    if method == "real":
        return real_embedding(text, embedding_model=embedding_model)
    raise ValueError(f"unsupported embedding method: {method}")


__all__ = [
    "EmbeddingCache",
    "EmbeddingCacheStats",
    "DEFAULT_LOCAL_EMBEDDING_MODEL",
    "FAKE_EMBEDDING_MODEL",
    "cosine_similarity",
    "default_local_embedding_cache_path",
    "fake_hash_embedding",
    "get_embedding",
    "local_embedding",
    "real_embedding",
    "safe_model_name",
]
