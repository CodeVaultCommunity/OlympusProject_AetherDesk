CREATE TABLE accounts (
    id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','member')),
    state TEXT NOT NULL CHECK(state IN ('active','disabled','deleted')),
    environment_id TEXT NOT NULL UNIQUE, permissions_version INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
    token_hash TEXT NOT NULL UNIQUE, revoked_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE permission_overrides (
    account_id TEXT NOT NULL REFERENCES accounts(id), capability TEXT NOT NULL,
    allowed INTEGER NOT NULL CHECK(allowed IN (0,1)),
    PRIMARY KEY(account_id,capability)
);
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY, actor_id TEXT, operation TEXT NOT NULL,
    target_id TEXT, at TEXT NOT NULL, result TEXT NOT NULL
);
CREATE TABLE account_events (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, event TEXT NOT NULL,
    at TEXT NOT NULL, consumed_at TEXT
);
