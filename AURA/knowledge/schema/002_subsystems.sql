-- Plugin registry
CREATE TABLE IF NOT EXISTS subsystems (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,           -- e.g. "audio-qualcomm"
    display_name TEXT NOT NULL,          -- e.g. "Qualcomm Audio"
    plugin_path TEXT NOT NULL,           -- path to plugin module
    version TEXT NOT NULL DEFAULT '0.1.0',
    is_active INTEGER NOT NULL DEFAULT 1,
    config_json TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Seed data: Qualcomm Audio (P0)
INSERT OR IGNORE INTO subsystems (name, display_name, plugin_path, version)
VALUES ('audio-qualcomm', 'Qualcomm Audio', 'plugins.audio_qualcomm.plugin', '0.1.0');
