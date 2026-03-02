-- BrainC v0.2 — Semantic memory: add embeddings column

ALTER TABLE messages ADD COLUMN embedding BLOB;
