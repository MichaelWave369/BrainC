-- BrainC v0.5 — Session management

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT     PRIMARY KEY,
    user_id      INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active  DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address   TEXT,
    user_agent   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
