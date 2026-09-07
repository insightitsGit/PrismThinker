from __future__ import annotations

import hashlib
import math
import re

DIM = 384
_TOKEN = re.compile(r"[a-z0-9_]+")

__all__ = ["DIM", "embed", "cosine", "_TOKEN"]


def embed(text: str) -> list[float]:
    """Deterministic hashed n-gram encoder. Cosine-ready, no downloaded weights."""
    vec = [0.0] * DIM
    lowered = text.lower()
    tokens = _TOKEN.findall(lowered)
    for token in tokens:
        _accumulate(vec, token, 1.0)
        if len(token) >= 3:
            for i in range(len(token) - 2):
                _accumulate(vec, token[i : i + 3], 0.45)
    for left, right in zip(tokens, tokens[1:]):
        _accumulate(vec, f"{left}_{right}", 0.8)
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def cosine(left: list[float], right: list[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right)))


def _accumulate(vec: list[float], key: str, weight: float) -> None:
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    index = int.from_bytes(digest[:4], "little") % DIM
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    vec[index] += weight * sign
