"""Deterministic hashed n-gram encoder for the neighbor bench only.

Production encoding is VectorPrism (PSM 1024d). This 384-d hasher is a
stand-in so local tests can retrieve without downloading weights.
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 384
_TOKEN = re.compile(r"[a-z0-9_]+")


def embed(text: str) -> list[float]:
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


def lexical_overlap(query: str, text: str) -> float:
    qtoks = set(_TOKEN.findall(query.lower()))
    dtoks = set(_TOKEN.findall(text.lower()))
    if not qtoks:
        return 0.0
    return len(qtoks & dtoks) / len(qtoks)


def hybrid_rank(query: str, blob: str, cosine_score: float) -> float:
    lexical = lexical_overlap(query, blob)
    return max(0.0, min(1.0, 0.55 * cosine_score + 0.45 * lexical))


def _accumulate(vec: list[float], key: str, weight: float) -> None:
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    index = int.from_bytes(digest[:4], "little") % DIM
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    vec[index] += weight * sign
