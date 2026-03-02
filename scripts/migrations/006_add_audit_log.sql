-- BrainC v1.0 — Security audit log table

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    action      TEXT     NOT NULL,
    details     TEXT     NOT NULL DEFAULT '{}',
    ip_address  TEXT,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
