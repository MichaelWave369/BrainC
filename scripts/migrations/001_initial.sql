-- BrainC v0.1 — Initial schema
-- Messages table for conversation history

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role            TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    conversation_id TEXT    NOT NULL DEFAULT 'default',
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_id ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT     PRIMARY KEY,
    title      TEXT     NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    tags       TEXT     NOT NULL DEFAULT '[]'
);
