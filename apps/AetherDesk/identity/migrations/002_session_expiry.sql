ALTER TABLE sessions ADD COLUMN expires_at TEXT;
CREATE INDEX sessions_expiry ON sessions(expires_at);
