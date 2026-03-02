-- BrainC v1.0 — Migration tracking table (bootstrapped by migrations.py)

CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    name        TEXT     NOT NULL UNIQUE,
    applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
