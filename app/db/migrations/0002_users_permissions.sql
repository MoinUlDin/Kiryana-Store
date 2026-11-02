-- Phase 1: users, permission overrides, Owner approval PINs.

CREATE TABLE users (
    id              INTEGER PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('superadmin', 'owner', 'cashier')),
    password_hash   TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    last_login_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
-- Exactly one Super Admin can ever exist.
CREATE UNIQUE INDEX idx_one_superadmin ON users(role) WHERE role = 'superadmin';

-- Layer 1 (allowed) and layer 2 (ask_password) per role. Super Admin is implicit: always allowed.
CREATE TABLE role_permissions (
    role         TEXT NOT NULL CHECK (role IN ('owner', 'cashier')),
    perm_key     TEXT NOT NULL,
    allowed      INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    ask_password INTEGER NOT NULL DEFAULT 0 CHECK (ask_password IN (0, 1)),
    PRIMARY KEY (role, perm_key)
);

-- Owner-issued approval codes. Only hashes are stored.
CREATE TABLE approval_pins (
    id              INTEGER PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES users(id),
    label           TEXT NOT NULL,
    pin_hash        TEXT NOT NULL,
    allowed_actions TEXT NOT NULL DEFAULT '*',   -- '*' or a JSON list of permission keys
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    revoked_at      TEXT
);
