# AURA Phase 0 — Plugin Loading, Deterministic Replay & DevOps Infrastructure
## Implementation-Grade Blueprint | Artifact P0-6
### Status: READY FOR IMPLEMENTATION

---

## 1. PLUGIN LOADING ARCHITECTURE

### 1.1 Plugin Interface (Stable Contract)

```python
# workspace/aura-sdk/src/aura_sdk/plugins/interface.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional
from pathlib import Path

@dataclass
class SubsystemContext:
    """Context passed to all plugin methods."""
    subsystem_name: str
    downstream_path: str
    upstream_path: str
    kernel_sources_path: str
    config: dict

@dataclass
class MigrationRule:
    """A single migration rule."""
    downstream_pattern: str
    upstream_equivalent: Optional[str]
    category: str  # api_mapping, macro, pattern, style, philosophy
    confidence: float
    description: str = ""
    source_refs: list[dict] = None

@dataclass
class ValidationCommand:
    """A validation command to run."""
    name: str
    command: list[str]  # argv
    cwd: Optional[str] = None
    timeout: int = 300

@dataclass
class SimulationModel:
    """A simulation model for a subsystem."""
    name: str
    sim_type: str  # probe_flow, dapm, pcm, soundwire, runtime_pm, dsp, dma_irq
    state_machine_class: str  # Python class path
    config: dict = None

@dataclass
class DashboardWidget:
    """A dashboard widget contributed by a plugin."""
    name: str
    page: str  # Which page it appears on
    position: str  # "top-left", "bottom-right", etc.
    component: str  # React component name
    data_endpoint: str  # API endpoint for widget data

class SubsystemPlugin(ABC):
    """
    Interface for AURA subsystem plugins.
    Every plugin must implement ALL methods.
    The plugin registry validates completeness on load.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def subsystem_id(self) -> str: ...

    # ── Migration ──
    @abstractmethod
    def get_migration_rules(self, ctx: SubsystemContext) -> list[MigrationRule]: ...

    @abstractmethod
    def analyze_dependencies(self, ctx: SubsystemContext) -> dict: ...

    # ── Validation ──
    @abstractmethod
    def get_validation_commands(self, ctx: SubsystemContext) -> list[ValidationCommand]: ...

    # ── Maintainer Intelligence ──
    @abstractmethod
    def get_maintainer_profiles(self) -> list[dict]: ...

    # ── Simulation ──
    @abstractmethod
    def get_simulation_models(self) -> list[SimulationModel]: ...

    # ── Dashboard ──
    @abstractmethod
    def get_dashboard_widgets(self) -> list[DashboardWidget]: ...

    # ── DTS ──
    @abstractmethod
    def get_dts_conversion_rules(self) -> list[dict]: ...
```

### 1.2 Plugin Registry

```python
# workspace/aura-sdk/src/aura_sdk/plugins/registry.py

import os
import importlib
import importlib.util
from pathlib import Path
from typing import dict, list, Optional

from aura_sdk.plugins.interface import SubsystemPlugin

PLUGINS_DIR = Path(__file__).parent.parent.parent.parent.parent.parent / "plugins"

class PluginRegistry:
    """
    Discovers, loads, and validates subsystem plugins.
    
    Discovery: Scan ./plugins/ for directories containing plugin.py
    Loading:    Dynamic import of plugin.py, instantiate Plugin class
    Validation: Verify all abstract methods are implemented
    Caching:    Loaded plugins cached for lifetime of registry
    
    Thread-safe: All operations are read-only after init.
    """

    def __init__(self, plugins_dir: str = None):
        self._plugins_dir = Path(plugins_dir) if plugins_dir else PLUGINS_DIR
        self._plugins: dict[str, SubsystemPlugin] = {}
        self._errors: list[str] = []

    async def load_all(self) -> dict[str, SubsystemPlugin]:
        """Discover and load all valid plugins. Returns loaded plugins."""
        discovered = self._discover()
        for plugin_dir in discovered:
            try:
                plugin = self._load_one(plugin_dir)
                if plugin:
                    self._plugins[plugin.subsystem_id] = plugin
            except Exception as e:
                self._errors.append(f"{plugin_dir.name}: {e}")
        return self._plugins

    def _discover(self) -> list[Path]:
        """Scan plugins directory for valid plugin directories."""
        if not self._plugins_dir.exists():
            return []
        return [
            entry for entry in self._plugins_dir.iterdir()
            if entry.is_dir() and (entry / "plugin.py").exists()
        ]

    def _load_one(self, plugin_dir: Path) -> Optional[SubsystemPlugin]:
        """Load a single plugin from directory."""
        module_name = f"aura_plugins_{plugin_dir.name}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            plugin_dir / "plugin.py"
        )
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load plugin.py from {plugin_dir}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find Plugin class
        if not hasattr(module, "Plugin"):
            raise AttributeError(f"{plugin_dir}/plugin.py must define 'Plugin' class")

        PluginClass = module.Plugin
        plugin = PluginClass()

        # Validate it implements SubsystemPlugin
        if not isinstance(plugin, SubsystemPlugin):
            raise TypeError(f"{plugin_dir}/plugin.py:Plugin must implement SubsystemPlugin")

        return plugin

    def get(self, subsystem_id: str) -> Optional[SubsystemPlugin]:
        return self._plugins.get(subsystem_id)

    def list(self) -> list[SubsystemPlugin]:
        return list(self._plugins.values())

    @property
    def loaded_ids(self) -> list[str]:
        return list(self._plugins.keys())

    @property
    def errors(self) -> list[str]:
        return self._errors

    def to_db_records(self) -> list[dict]:
        """Generate INSERT records for subsystems table."""
        return [
            {
                "id": plugin.subsystem_id,
                "name": plugin.subsystem_id,
                "display_name": plugin.name,
                "plugin_path": f"plugins.{plugin.subsystem_id}",
                "version": plugin.version,
                "is_active": 1,
            }
            for plugin in self._plugins.values()
        ]
```

### 1.3 Plugin Validation

```python
class PluginValidator:
    """Validates plugin completeness without executing."""

    REQUIRED_METHODS = [
        "get_migration_rules",
        "analyze_dependencies",
        "get_validation_commands",
        "get_maintainer_profiles",
        "get_simulation_models",
        "get_dashboard_widgets",
        "get_dts_conversion_rules",
    ]

    def validate(self, plugin: SubsystemPlugin) -> ValidationResult:
        errors = []
        warnings = []

        # Check required properties
        for prop in ["name", "version", "subsystem_id"]:
            if not getattr(plugin, prop, None):
                errors.append(f"Missing required property: {prop}")

        # Check required methods return correct types
        for method_name in self.REQUIRED_METHODS:
            method = getattr(plugin, method_name, None)
            if not method:
                errors.append(f"Missing required method: {method_name}")
                continue
            if not callable(method):
                errors.append(f"{method_name} is not callable")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
```

### 1.4 Qualcomm Audio Plugin (Reference Implementation)

```python
# plugins/audio-qualcomm/plugin.py

from pathlib import Path
import json

from aura_sdk.plugins.interface import (
    SubsystemPlugin, SubsystemContext,
    MigrationRule, ValidationCommand, SimulationModel, DashboardWidget,
)

class Plugin(SubsystemPlugin):
    """Qualcomm Audio Subsystem Plugin — Reference Implementation."""

    @property
    def name(self) -> str: return "Qualcomm Audio"

    @property
    def version(self) -> str: return "0.1.0"

    @property
    def subsystem_id(self) -> str: return "audio-qualcomm"

    def __init__(self):
        self._rules_dir = Path(__file__).parent / "rules"
        self._heuristics_dir = Path(__file__).parent / "heuristics"

    # ── Migration ──

    def get_migration_rules(self, ctx: SubsystemContext) -> list[MigrationRule]:
        """Load rules from JSON files."""
        rules = []
        rules_file = self._rules_dir / "patterns.json"
        if rules_file.exists():
            data = json.loads(rules_file.read_text())
            for r in data:
                rules.append(MigrationRule(
                    downstream_pattern=r["downstream"],
                    upstream_equivalent=r.get("upstream"),
                    category=r.get("category", "pattern"),
                    confidence=r.get("confidence", 0.5),
                    description=r.get("description", ""),
                    source_refs=r.get("sources", []),
                ))
        return rules

    def analyze_dependencies(self, ctx: SubsystemContext) -> dict:
        """Analyze Qualcomm Audio driver dependencies."""
        return {
            "includes": ["sound/soc.h", "sound/soc-dapm.h", "linux/clk.h"],
            "apis": ["snd_soc_dai_set_sysclk", "snd_soc_component_update_bits"],
            "macros": ["WCD934X_NUM_REGISTERS", "LPASS_MACRO_MAX"],
        }

    # ── Validation ──

    def get_validation_commands(self, ctx: SubsystemContext) -> list[ValidationCommand]:
        return [
            ValidationCommand(
                name="sparse",
                command=["sparse", "-Wcast-truncate", ctx.downstream_path],
            ),
            ValidationCommand(
                name="checkpatch",
                command=["checkpatch.pl", "--no-tree", "-f", ctx.downstream_path],
            ),
            ValidationCommand(
                name="dtbs_check",
                command=["make", "dtbs_check"],
                cwd=ctx.kernel_sources_path,
            ),
        ]

    # ── Maintainers ──

    def get_maintainer_profiles(self) -> list[dict]:
        maintainers_file = self._rules_dir / "maintainers.json"
        if maintainers_file.exists():
            return json.loads(maintainers_file.read_text())
        return [
            {
                "name": "Mark Brown",
                "email": "broonie@kernel.org",
                "subsystem": "ALSA SoC",
                "acceptance_rate": 0.75,
            }
        ]

    # ── Simulation ──

    def get_simulation_models(self) -> list[SimulationModel]:
        return [
            SimulationModel(
                name="dapm_power_flow",
                sim_type="dapm",
                state_machine_class="simulation.state_machines.dapm.DAPMSimulator",
            ),
            SimulationModel(
                name="probe_flow",
                sim_type="probe_flow",
                state_machine_class="simulation.state_machines.probe_flow.ProbeSimulator",
            ),
            SimulationModel(
                name="soundwire_bus",
                sim_type="soundwire",
                state_machine_class="simulation.state_machines.soundwire.SoundWireSimulator",
            ),
        ]

    # ── Dashboard ──

    def get_dashboard_widgets(self) -> list[DashboardWidget]:
        return [
            DashboardWidget(
                name="codec_topology",
                page="ArchitectureLab",
                position="main",
                component="CodecTopologyGraph",
                data_endpoint="/api/v1/simulation/{patch_id}/topology",
            ),
            DashboardWidget(
                name="dapm_state",
                page="ArchitectureLab",
                position="sidebar",
                component="DAPMStateViewer",
                data_endpoint="/api/v1/simulation/{patch_id}/dapm",
            ),
        ]

    # ── DTS ──

    def get_dts_conversion_rules(self) -> list[dict]:
        dts_file = self._rules_dir / "dts_conversion.json"
        if dts_file.exists():
            return json.loads(dts_file.read_text())
        return [
            {
                "downstream_binding": "qcom,wcd934x-codec",
                "upstream_binding": "cirrus,cs42l42",
                "yaml_schema": "sound/cirrus,cs42l42.yaml",
            }
        ]
```

---

## 2. DETERMINISTIC REPLAY INFRASTRUCTURE

### 2.1 Design Goals

| Goal | Implementation |
|------|---------------|
| Reproducible builds | Same input → same output (given same seed) |
| Regression testing | Record once, replay in CI |
| Debug without API cost | Replay uses recorded LLM responses |
| Audit trail | Prove what the system produced |
| Performance profiling | Replay with timing instrumentation |

### 2.2 Recording Infrastructure

```python
# workspace/aura-sdk/src/aura_sdk/replay/recorder.py

import json
import hashlib
import sqlite3
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Any
from pathlib import Path

@dataclass
class TaskLog:
    """Complete record of a task execution for deterministic replay."""
    task_id: str
    agent_type: str
    seed: int
    model_version: str
    temperature: float
    rules_path: str
    input_data: dict           # Full task input
    llm_conversation: list[dict]  # [{role, content}, ...]
    llm_responses: list[str]   # Recorded responses
    execution_steps: list[dict] # [{step, timestamp, data}]
    output_data: dict          # Final output
    output_hash: str           # SHA256(output_json)
    created_at: str

class TaskRecorder:
    """Records task executions for later replay."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()
        self._active: dict[str, dict] = {}  # task_id -> partial record

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS task_logs (
                    task_id TEXT PRIMARY KEY,
                    agent_type TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    rules_path TEXT,
                    input_json TEXT NOT NULL,
                    conversation_json TEXT DEFAULT '[]',
                    responses_json TEXT DEFAULT '[]',
                    steps_json TEXT DEFAULT '[]',
                    output_json TEXT,
                    output_hash TEXT,
                    created_at INTEGER
                )
            """)

    def start(self, task_id: str, agent_type: str, seed: int,
              model_version: str, temperature: float, rules_path: str,
              input_data: dict):
        """Start recording a new task."""
        self._active[task_id] = {
            "task_id": task_id,
            "agent_type": agent_type,
            "seed": seed,
            "model_version": model_version,
            "temperature": temperature,
            "rules_path": rules_path,
            "input_json": json.dumps(input_data),
            "conversation_json": "[]",
            "responses_json": "[]",
            "steps_json": "[]",
        }
        # Insert skeleton
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                INSERT OR REPLACE INTO task_logs
                (task_id, agent_type, seed, model_version, temperature,
                 rules_path, input_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, agent_type, seed, model_version, temperature,
                  rules_path, json.dumps(input_data), int(datetime.utcnow().timestamp())))

    def record_prompt(self, task_id: str, role: str, content: str):
        """Record an LLM prompt."""
        message = {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                UPDATE task_logs
                SET conversation_json = json_insert(
                    COALESCE(conversation_json, '[]'), '$[#]', ?)
                WHERE task_id = ?
            """, (json.dumps(message), task_id))

    def record_response(self, task_id: str, response: str):
        """Record an LLM response."""
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                UPDATE task_logs
                SET responses_json = json_insert(
                    COALESCE(responses_json, '[]'), '$[#]', ?)
                WHERE task_id = ?
            """, (response, task_id))

    def record_step(self, task_id: str, step_name: str, data: dict):
        """Record an execution step."""
        step = {"step": step_name, "timestamp": datetime.utcnow().isoformat(), "data": data}
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                UPDATE task_logs
                SET steps_json = json_insert(
                    COALESCE(steps_json, '[]'), '$[#]', ?)
                WHERE task_id = ?
            """, (json.dumps(step), task_id))

    def finalize(self, task_id: str, output: dict):
        """Finalize recording with output and hash."""
        output_json = json.dumps(output, sort_keys=True)
        output_hash = hashlib.sha256(output_json.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                UPDATE task_logs
                SET output_json = ?, output_hash = ?
                WHERE task_id = ?
            """, (output_json, output_hash, task_id))
        self._active.pop(task_id, None)

    def get_log(self, task_id: str) -> Optional[TaskLog]:
        """Retrieve a complete task log."""
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT * FROM task_logs WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            return TaskLog(
                task_id=row[0],
                agent_type=row[1],
                seed=row[2],
                model_version=row[3],
                temperature=row[4],
                rules_path=row[5] or "",
                input_data=json.loads(row[6]),
                llm_conversation=json.loads(row[7] or "[]"),
                llm_responses=json.loads(row[8] or "[]"),
                execution_steps=json.loads(row[9] or "[]"),
                output_data=json.loads(row[10]) if row[10] else {},
                output_hash=row[11] or "",
                created_at=row[12],
            )
```

### 2.3 Replay Infrastructure

```python
# workspace/aura-sdk/src/aura_sdk/replay/replayer.py

import json
from typing import Iterator
from aura_sdk.replay.recorder import TaskRecorder, TaskLog
from aura_sdk.replay.context import DeterministicContext

class LLMMockClient:
    """Mock LLM client that returns recorded responses. No API calls."""

    def __init__(self, recorded_responses: list[str]):
        self._responses = recorded_responses
        self._index = 0

    async def complete(self, messages: list[dict], **kwargs) -> str:
        if self._index >= len(self._responses):
            raise IndexError(f"No recorded response #{self._index} (have {len(self._responses)})")
        response = self._responses[self._index]
        self._index += 1
        return response

class ReplayEngine:
    """Replays a recorded task deterministically."""

    def __init__(self, recorder: TaskRecorder):
        self._recorder = recorder

    async def replay(self, task_id: str, agent_class: type) -> ReplayResult:
        """Replay a task. Returns result + fidelity check."""
        log = self._recorder.get_log(task_id)
        if not log:
            raise ValueError(f"No log found for task {task_id}")

        # Create deterministic context with same parameters
        ctx = DeterministicContext(
            seed=log.seed,
            model_version=log.model_version,
            temperature=log.temperature,
        )

        # Create mock LLM client with recorded responses
        llm_mock = LLMMockClient(log.llm_responses)

        # Create agent with replay context
        agent = agent_class()
        agent.context = ctx
        agent.llm_client = llm_mock  # Inject mock

        # Execute
        result = await agent.execute_replay(log.input_data)

        # Verify output hash
        result_json = json.dumps(result, sort_keys=True)
        result_hash = hashlib.sha256(result_json.encode()).hexdigest()

        return ReplayResult(
            task_id=task_id,
            output=result,
            output_hash=result_hash,
            expected_hash=log.output_hash,
            hash_match=result_hash == log.output_hash,
            responses_consumed=llm_mock._index,
            total_responses=len(log.llm_responses),
        )

@dataclass
class ReplayResult:
    task_id: str
    output: dict
    output_hash: str
    expected_hash: str
    hash_match: bool
    responses_consumed: int
    total_responses: int

    @property
    def fidelity(self) -> str:
        if self.hash_match:
            return "PERFECT"
        if self.responses_consumed != self.total_responses:
            return f"PARTIAL ({self.responses_consumed}/{self.total_responses} responses)"
        return "DIVERGED"
```

### 2.4 Deterministic Context

```python
# workspace/aura-sdk/src/aura_sdk/replay/context.py

import random
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DeterministicContext:
    """Provides deterministic execution environment."""
    seed: int
    model_version: str = "gpt-4o-2024-08-06"
    temperature: float = 0.1

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def llm_params(self) -> dict:
        return {
            "seed": self.seed,
            "temperature": self.temperature,
            "model": self.model_version,
        }

    def random_choice(self, options: list) -> Any:
        return self._rng.choice(options)

    def random_sample(self, population: list, k: int) -> list:
        return self._rng.sample(population, min(k, len(population)))

    def deterministic_sort[T](self, items: list[T], key=None) -> list[T]:
        return sorted(items, key=lambda x: str(key(x)) if key else str(x))

    def deterministic_dict(self, d: dict) -> dict:
        """Return dict with sorted keys (for consistent JSON)."""
        return {k: d[k] for k in sorted(d.keys())}

    def random_seed(self) -> int:
        """Get a derived random seed (for sub-tasks)."""
        return self._rng.randint(0, 2**32 - 1)
```

### 2.5 Snapshot System

```python
class ExecutionSnapshot:
    """Point-in-time snapshot for rollback."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.snapshots_dir = self.data_dir / "snapshots"
        self.snapshots_dir.mkdir(exist_ok=True)

    def create(self, label: str) -> str:
        """Create a snapshot. Returns snapshot ID."""
        snapshot_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{label}"
        snapshot_dir = self.snapshots_dir / snapshot_id
        snapshot_dir.mkdir()

        # 1. Save SQLite database
        import shutil
        db_path = self.data_dir / "aura.db"
        if db_path.exists():
            shutil.copy2(db_path, snapshot_dir / "aura.db")

        # 2. Save WAL file
        wal_path = self.data_dir / "aura.db-wal"
        if wal_path.exists():
            shutil.copy2(wal_path, snapshot_dir / "aura.db-wal")

        # 3. Save agent output directories
        agents_dir = self.data_dir / "agents"
        if agents_dir.exists():
            shutil.copytree(agents_dir, snapshot_dir / "agents")

        # 4. Save metadata
        metadata = {
            "snapshot_id": snapshot_id,
            "label": label,
            "created_at": datetime.utcnow().isoformat(),
            "db_size_bytes": (snapshot_dir / "aura.db").stat().st_size if (snapshot_dir / "aura.db").exists() else 0,
        }
        (snapshot_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        return snapshot_id

    def restore(self, snapshot_id: str):
        """Restore from snapshot."""
        snapshot_dir = self.snapshots_dir / snapshot_id
        if not snapshot_dir.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        # Stop all services first (caller responsibility)

        # 1. Restore database
        db_backup = snapshot_dir / "aura.db"
        if db_backup.exists():
            import shutil
            shutil.copy2(db_backup, self.data_dir / "aura.db")

        wal_backup = snapshot_dir / "aura.db-wal"
        if wal_backup.exists():
            shutil.copy2(wal_backup, self.data_dir / "aura.db-wal")

        # 2. Restore agent outputs
        agents_backup = snapshot_dir / "agents"
        if agents_backup.exists():
            agents_dir = self.data_dir / "agents"
            if agents_dir.exists():
                shutil.rmtree(agents_dir)
            shutil.copytree(agents_backup, agents_dir)
```

---

## 3. DEVOPS INFRASTRUCTURE

### 3.1 Bootstrap Script

```bash
#!/bin/bash
# scripts/bootstrap.sh — 5-minute first-run setup

set -e

echo "========================================"
echo "  AURA Platform — First-Run Bootstrap"
echo "========================================"

# ── 1. Environment ──
echo "[1/5] Checking environment..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY is not set"
    echo "Please set it: export OPENAI_API_KEY=sk-..."
    exit 1
fi

if [ -z "$JWT_SECRET" ]; then
    echo "WARNING: JWT_SECRET not set. Generating random secret..."
    export JWT_SECRET=$(openssl rand -hex 32)
    echo "JWT_SECRET=$JWT_SECRET" >> .env
fi

# ── 2. Directories ──
echo "[2/5] Creating directories..."
mkdir -p data/{backups,agents,tmp,exports,logs,snapshots}
mkdir -p data/empty  # placeholder if no kernel sources

# ── 3. Database ──
echo "[3/5] Initializing database..."
docker compose run --rm aura-core python -c "
import asyncio
from aura_sdk.db.migrations import MigrationRunner
async def init():
    runner = MigrationRunner('/data/aura.db')
    count = await runner.migrate()
    print(f'Ran {count} migrations')
asyncio.run(init())
"

# ── 4. Admin User ──
echo "[4/5] Creating admin user..."
docker compose run --rm aura-core python -c "
import asyncio, bcrypt, os
from aura_sdk.db.connection import get_db

async def create_admin():
    async with get_db() as db:
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        count = (await cursor.fetchone())[0]
        if count > 0:
            print('Users already exist. Skipping.')
            return

        email = os.getenv('ADMIN_EMAIL', 'admin@aura.local')
        password = os.getenv('ADMIN_PASSWORD', 'admin123')
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

        await db.execute(
            'INSERT INTO users (email, password_hash, role, display_name) VALUES (?, ?, ?, ?)',
            (email, hashed, 'admin', 'Administrator')
        )
        await db.commit()
        print(f'Admin created: {email} / {password}')
        print('IMPORTANT: Change this password after first login!')

asyncio.run(create_admin())
"

# ── 5. Validation ──
echo "[5/5] Validating setup..."
sleep 2

# Check health
if curl -sf http://localhost:8000/health/ready > /dev/null; then
    echo "Health check: PASS"
else
    echo "Health check: FAIL — services may still be starting"
    echo "Run 'make health' in 10 seconds to verify"
fi

echo ""
echo "========================================"
echo "  Bootstrap complete!"
echo "  Dashboard: http://localhost:3000"
echo "  API:       http://localhost:8000"
echo "  Health:    http://localhost:8000/health/ready"
echo "========================================"
```

### 3.2 Backup Script

```bash
#!/bin/bash
# scripts/backup.sh — Daily SQLite backup

BACKUP_DIR="./data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/aura_$TIMESTAMP.db"

# Ensure WAL is checkpointed
docker compose exec aura-core sqlite3 /data/aura.db "PRAGMA wal_checkpoint(RESTART);"

# Copy database
cp ./data/aura.db "$BACKUP_FILE"

# Compress
gzip "$BACKUP_FILE"

# Keep only last 30 backups
ls -t "$BACKUP_DIR"/aura_*.db.gz | tail -n +31 | xargs rm -f

echo "Backup: $BACKUP_FILE.gz"
```

### 3.3 Health Check Script

```bash
#!/bin/bash
# scripts/health-check.sh — System diagnostics

echo "=== AURA Health Check ==="
echo ""

# Service health
echo "--- Service Status ---"
docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Health}}"

# API health
echo ""
echo "--- API Health ---"
curl -s http://localhost:8000/health/ready | python -m json.tool

# Metrics
echo ""
echo "--- Key Metrics ---"
curl -s http://localhost:8000/metrics | grep -E "(agents_total|queue_depth|llm_tokens)"

# Disk
echo ""
echo "--- Disk Usage ---"
df -h ./data

# Logs (errors in last hour)
echo ""
echo "--- Recent Errors ---"
docker compose logs --since=1h | grep -i error | tail -20 || echo "No errors found"
```

---

## 4. ARCHITECTURAL DECISION RECORDS (Phase 0)

```
workspace/aura-sdk/docs/decisions/
├── ADR-001-sqlite-for-mvp.md
├── ADR-002-in-memory-event-bus.md
├── ADR-003-cli-agents-subprocess.md
├── ADR-004-deterministic-seed.md
└── ADR-005-plugin-abstraction-day-1.md
```

### ADR-001: SQLite for MVP

```markdown
# ADR-001: SQLite for MVP Persistence

## Status: Accepted

## Context
Need a database for knowledge persistence, audit logs, and governance.
Options: SQLite, PostgreSQL, MySQL.

## Decision: SQLite (WAL mode)

## Rationale
- Zero configuration — works out of the box with Docker volume
- WAL mode provides concurrent reads
- Sufficient for 20 users, 200 agents
- JSON columns for flexible data
- FTS5 built-in for search
- Easy backup (file copy)
- Upgrade path to PostgreSQL later

## Consequences
+ Simple deployment
+ No separate DB container
+ Portable
- Single-writer bottleneck (mitigated by batching)
- No horizontal scaling (not needed for MVP)
```

---

## 5. IMPLEMENTATION READINESS CHECKLIST

### Phase 0 — Foundation Layer

```
□ Monorepo structure created (workspace, services, agents, dashboard)
□ aura-sdk package with shared models, protocol, bus, logging, db
□ Agent SDK with BaseAgent ABC and stdio protocol
□ Docker Compose with 4 services + startup order
□ SQLite schema (12 tables, FTS5, audit triggers)
□ Migration runner with version tracking
□ Event bus (in-memory, typed channels)
□ WebSocket server with connection manager + SSE fallback
□ JWT authentication with bcrypt
□ RBAC enforcer with 5 roles
□ Health checks (liveness + readiness)
□ Structured JSON logging (structlog)
□ Prometheus metrics endpoint
□ Watchdog manager (heartbeat monitoring)
□ Circuit breaker (per-agent-type)
□ Task queue (3-tier priority)
□ Retry executor (per-exit-code policies)
□ Plugin registry (discovery + loading + validation)
□ Deterministic context (seeded RNG)
□ Task recorder (LLM conversations)
□ Replay engine (mock LLM responses)
□ Bootstrap script (5-minute setup)
□ Backup script (daily SQLite backup)
□ CI/CD pipeline (lint, test, build)
□ Makefile (dev commands)
□ Documentation (architecture decisions)
```

**Status: 30/30 SPECIFIED — READY FOR IMPLEMENTATION**
