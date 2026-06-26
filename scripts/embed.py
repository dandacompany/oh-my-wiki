"""Pluggable text-embedding providers for the `embedding`/`hybrid` recall strategies.

Config (recall.embedding.*): provider (none|openai|fake|fastembed), model, dim.
Secrets via config.read_secret (OPENAI_API_KEY). Returns None when unconfigured so
callers degrade to fts — embedding is opt-in (references/auto-recall-hook-design.md §10)."""
from __future__ import annotations

import hashlib
import struct

DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-small"
KNOWN_MODEL_DIMS = {
    "intfloat/multilingual-e5-small": 384,
    "intfloat/multilingual-e5-base": 768,
    "BAAI/bge-small-en-v1.5": 384,
}


class Embedder:
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class FakeEmbedder(Embedder):
    """Deterministic, offline embedder for tests + an `embedding`-without-network
    smoke path. Hashes text into a fixed-dim unit-ish vector."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.sha256((t or "").encode("utf-8")).digest()
            vals = []
            i = 0
            while len(vals) < self.dim:
                chunk = h[(i * 4) % len(h):(i * 4) % len(h) + 4].ljust(4, b"\0")
                vals.append(struct.unpack("<I", chunk)[0] / 2**32)
                i += 1
            out.append(vals[: self.dim])
        return out


class OpenAIEmbedder(Embedder):
    """text-embedding-3-small by default (1536 dims). Lazy import — only when used."""

    def __init__(self, model: str, dim: int, api_key: str):
        self.model, self.dim, self._key = model, dim, api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI  # optional dep; only imported when provider=openai
        client = OpenAI(api_key=self._key)
        resp = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


class FastEmbedEmbedder(Embedder):
    """Local ONNX embedder via fastembed (no torch). Lazy-imports fastembed and
    caches the model on first embed(). Model files download+cache on first use."""

    def __init__(self, model: str, dim: int):
        self.model, self.dim = model, int(dim)
        self._te = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._te is None:
            from fastembed import TextEmbedding  # optional dep; lazy
            self._te = TextEmbedding(model_name=self.model)
        return [list(map(float, v)) for v in self._te.embed(list(texts))]


def get_embedder(cfg: dict) -> Embedder | None:
    """Build an embedder from recall.embedding config, or None if not configured."""
    cfg = cfg or {}
    provider = (cfg.get("provider") or "none").lower()  # falsy/missing → "none"
    if provider == "none":
        return None
    if provider == "fake":
        return FakeEmbedder(dim=int(cfg.get("dim", 256)))
    if provider == "openai":
        from scripts import config
        key = config.read_secret("OPENAI_API_KEY")
        if not key:
            return None
        return OpenAIEmbedder(model=cfg.get("model", "text-embedding-3-small"),
                              dim=int(cfg.get("dim", 1536)), api_key=key)
    if provider == "fastembed":
        model = cfg.get("model") or DEFAULT_LOCAL_MODEL
        dim = int(cfg.get("dim") or KNOWN_MODEL_DIMS.get(model, 384))
        return FastEmbedEmbedder(model=model, dim=dim)
    return None
