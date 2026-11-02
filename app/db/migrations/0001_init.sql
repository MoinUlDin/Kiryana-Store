-- Phase 0 baseline: settings and the append-only audit log.

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- No foreign key to users on purpose: audit history must survive any user change,
-- so the username is stored as a snapshot next to the id.
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY,
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    user_id         INTEGER,
    username        TEXT,
    action          TEXT NOT NULL,
    entity          TEXT,
    entity_id       INTEGER,
    old_json        TEXT,
    new_json        TEXT,
    reason          TEXT,
    approved_by     TEXT,
    approval_method TEXT
);
CREATE INDEX idx_audit_at     ON audit_log(at);
CREATE INDEX idx_audit_user   ON audit_log(user_id);
CREATE INDEX idx_audit_action ON audit_log(action);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
