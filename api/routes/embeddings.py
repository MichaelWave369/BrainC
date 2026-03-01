"""Local embedding utilities — all-MiniLM-L6-v2 via sentence-transformers."""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from api.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    """Load and cache the embedding model (runs only once)."""
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_text(text: str) -> bytes:
    """Return a normalized float32 embedding as raw bytes for SQLite BLOB storage."""
    model = _load_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32).tobytes()


def cosine_similarity(a_bytes: bytes, b_bytes: bytes) -> float:
    """Cosine similarity between two normalized embeddings stored as raw bytes."""
    a = np.frombuffer(a_bytes, dtype=np.float32)
    b = np.frombuffer(b_bytes, dtype=np.float32)
    return float(np.dot(a, b))
