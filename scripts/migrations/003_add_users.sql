-- BrainC v0.5 — Multi-user: users + preferences tables

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    username      TEXT     NOT NULL UNIQUE,
    password_hash TEXT     NOT NULL,
    display_name  TEXT     NOT NULL,
    role          TEXT     NOT NULL DEFAULT 'user',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login    DATETIME
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id                INTEGER  PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme                  TEXT     NOT NULL DEFAULT 'dark',
    model                  TEXT     NOT NULL DEFAULT 'braincbrain',
    tools_enabled          INTEGER  NOT NULL DEFAULT 1,
    system_prompt_override TEXT,
    context_length         INTEGER  NOT NULL DEFAULT 8192
);

ALTER TABLE messages ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token      TEXT     PRIMARY KEY,
    user_id    INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT     NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
