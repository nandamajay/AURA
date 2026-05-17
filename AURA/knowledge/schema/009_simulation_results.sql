-- Simulation results
CREATE TABLE IF NOT EXISTS simulation_results (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT REFERENCES patches(id) ON DELETE CASCADE,
    simulation_type TEXT NOT NULL
        CHECK (simulation_type IN (
            'probe_flow','dapm','pcm','soundwire','runtime_pm','dsp','dma_irq'
        )),
    fidelity_mode TEXT NOT NULL DEFAULT 'state_machine'
        CHECK (fidelity_mode IN ('state_machine','qemu')),
    status TEXT NOT NULL
        CHECK (status IN ('pending','running','passed','failed','inconclusive')),
    findings_json TEXT DEFAULT '{}',     -- structured results
    failure_predictions TEXT DEFAULT '[]',
    confidence_impact REAL DEFAULT 0.0,  -- delta to patch confidence
    duration_ms INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_sim_patch ON simulation_results(patch_id);
CREATE INDEX IF NOT EXISTS idx_sim_type ON simulation_results(simulation_type);
CREATE INDEX IF NOT EXISTS idx_sim_status ON simulation_results(status);
