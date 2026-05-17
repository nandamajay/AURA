-- Identity & access management
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,        -- bcrypt, 12 rounds
    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('viewer','reviewer','approver','architect','admin')),
    display_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    last_login_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- System actor used by seeded governance and memory ledgers.
INSERT OR IGNORE INTO users (id, email, password_hash, role, display_name, is_active)
VALUES ('system', 'system@aura.local', '!', 'admin', 'AURA System', 0);
