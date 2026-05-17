# AURA P2 — Plugin Marketplace, Subsystem Extension & Multi-Subsystem Scaling
## Artifacts: 12, 13, 14 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Plugin Interface, Registry, Validation)

---

## ARTIFACT 12: PLUGIN MARKETPLACE ARCHITECTURE

### 12.1 P2 Reality: No Marketplace Yet

**AOG Assessment:**
- Is a marketplace required for MVP? **No.**
- Is a marketplace required for P2? **No.**
- What IS needed? **A plugin validation and loading system** (already in P0)

**P2 Deliverable: Marketplace Interface (Not Implementation)**

```python
# workspace/aura-sdk/src/aura_sdk/plugins/marketplace.py
# P2: Interface defined for future use. No marketplace implementation.

"""
PLUGIN MARKETPLACE — P3+ Feature

P2 Status: Interface only. Rationale:
  - P2 has exactly ONE plugin (audio-qualcomm)
  - Marketplace needs 3+ plugins to be useful
  - Marketplace adds distribution, versioning, trust complexity
  - Current in-repo plugin model is sufficient

P3 Activation Criteria:
  - 3+ subsystem plugins exist
  - Users request plugin sharing
  - Plugin trust model matures (VETTED level operational)
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class PluginPackage:
    """A distributable plugin package. P3+ concept."""
    name: str
    version: str
    subsystem_id: str
    author: str
    description: str
    # Distribution
    tarball_url: str           # URL to .tar.gz
    checksum: str              # SHA256 of tarball
    signature: Optional[str]   # GPG signature (VETTED level)
    # Metadata
    dependencies: list[str]    # Other plugin IDs required
    min_aura_version: str      # Minimum AURA platform version
    tested_kernels: list[str]  # Kernel versions tested against

class PluginMarketplace:
    """
    P3+ plugin discovery and distribution.
    P2: Interface stub. Not instantiated.
    """
    
    async def search(self, query: str) -> list[PluginPackage]:
        """Search available plugins."""
        raise NotImplementedError("Marketplace available in P3+")
    
    async def install(self, package: PluginPackage) -> bool:
        """Download, verify, and install plugin."""
        raise NotImplementedError("Marketplace available in P3+")
    
    async def verify(self, package: PluginPackage) -> bool:
        """Verify checksum and signature."""
        raise NotImplementedError("Marketplace available in P3+")
```

### 12.2 AOG Verdict

| Question | Answer |
|----------|--------|
| Marketplace in P2? | **No.** Interface only. |
| Why not? | One plugin, no users to share with, adds complexity. |
| When? | **P3+** when 3+ plugins exist. |
| What exists now? | Full plugin loading, validation, execution from P0. |

---

## ARTIFACT 13: SUBSYSTEM EXTENSION FRAMEWORK

### 13.1 Extension Points (Frozen from P0)

The plugin interface (P0 frozen) defines these extension points:

```python
class SubsystemPlugin(ABC):
    # Extension Point 1: Migration Rules
    @abstractmethod
    def get_migration_rules(self, ctx: SubsystemContext) -> list[MigrationRule]: ...
    
    # Extension Point 2: Dependency Analysis
    @abstractmethod
    def analyze_dependencies(self, ctx: SubsystemContext) -> dict: ...
    
    # Extension Point 3: Validation Commands
    @abstractmethod
    def get_validation_commands(self, ctx: SubsystemContext) -> list[ValidationCommand]: ...
    
    # Extension Point 4: Maintainer Profiles
    @abstractmethod
    def get_maintainer_profiles(self) -> list[dict]: ...
    
    # Extension Point 5: Simulation Models
    @abstractmethod
    def get_simulation_models(self) -> list[SimulationModel]: ...
    
    # Extension Point 6: Dashboard Widgets
    @abstractmethod
    def get_dashboard_widgets(self) -> list[DashboardWidget]: ...
    
    # Extension Point 7: DTS Conversion
    @abstractmethod
    def get_dts_conversion_rules(self) -> list[dict]: ...
```

### 13.2 Adding a New Subsystem (Procedure)

```
STEP 1: Create plugin directory
  $ mkdir plugins/{subsystem-name}

STEP 2: Implement SubsystemPlugin
  $ cat > plugins/{subsystem-name}/plugin.py << 'EOF'
  from aura_sdk.plugins.interface import SubsystemPlugin, ...
  class Plugin(SubsystemPlugin):
      @property
      def name(self): return "Display Name"
      @property
      def version(self): return "0.1.0"
      @property
      def subsystem_id(self): return "{subsystem-name}"
      # Implement all 7 methods...
  EOF

STEP 3: Add rules/heuristics
  $ mkdir plugins/{subsystem-name}/rules
  $ edit plugins/{subsystem-name}/rules/patterns.json

STEP 4: Register in database
  INSERT INTO subsystems (name, display_name, plugin_path, version)
  VALUES ('{subsystem-name}', 'Display Name', 'plugins.{subsystem_name}.plugin', '0.1.0');

STEP 5: Restart aura-core
  $ docker compose restart aura-core

STEP 6: Validate
  PluginValidator.validate(plugin) → must return valid=True
```

### 13.3 Cross-Pattern Transfer (Tier 3 Learning)

When a new plugin loads, Tier 3 learning transfers common patterns:

```python
class CrossSubsystemTransfer:
    """Transfer validated patterns from one subsystem to another."""
    
    COMMON_PATTERNS = [
        # Runtime PM (applies to ALL subsystems)
        {
            "category": "pattern",
            "downstream_pattern": "pm_runtime_get_sync",
            "upstream_equivalent": "pm_runtime_resume_and_get",
            "confidence_boost": 0.1,  # Add to base confidence
        },
        # Regmap (applies to codec/DSP subsystems)
        {
            "category": "api_mapping",
            "downstream_pattern": "regmap_write",
            "upstream_equivalent": "regmap_write",  # Same API
            "applies_to": ["audio", "dsp"],
        },
        # Managed resources (applies to ALL subsystems)
        {
            "category": "pattern",
            "downstream_pattern": "devm_kzalloc",
            "upstream_equivalent": "devm_kzalloc",  # Same API, verify usage
            "confidence_boost": 0.05,
        },
    ]
    
    async def transfer_to(self, new_subsystem_id: str) -> int:
        """Transfer common patterns to new subsystem. Returns count transferred."""
        count = 0
        for pattern in self.COMMON_PATTERNS:
            if self._applies_to(pattern, new_subsystem_id):
                await self._insert_rule(new_subsystem_id, pattern)
                count += 1
        return count
```

### 13.4 AOG Verdict

| Question | Answer |
|----------|--------|
| Extension framework complex? | **No.** 7 methods, clear interface. |
| Adding a subsystem hard? | **No.** 6 steps, well-documented. |
| Cross-transfer overengineered? | **No.** Simple confidence boost, not ML. |

---

## ARTIFACT 14: MULTI-SUBSYSTEM SCALING BLUEPRINT

### 14.1 Scaling Dimensions

```
Current (P2):   1 subsystem (audio-qualcomm)
Target (P3):    3 subsystems (audio + camera + DRM)
Target (P4):    5+ subsystems

Scaling Concerns:
  1. Agent pool: Same 50-agent limit, agents are per-task not per-subsystem
  2. Knowledge base: Rules tagged by subsystem_id, queries filtered
  3. Dashboard: Pages shared, widgets contributed by plugins
  4. Simulation: Models per plugin, loaded on demand
  5. Validation: Commands per plugin, queued independently

NOT a Concern (AOG):
  - No new services needed
  - No database schema changes
  - No infrastructure changes
  - Plugin architecture handles scaling naturally
```

### 14.2 Resource Impact per Additional Subsystem

| Resource | Per Subsystem | 3 Subsystems | 5 Subsystems |
|----------|--------------|-------------|-------------|
| Memory (rules) | ~10 MB | ~30 MB | ~50 MB |
| Disk (plugin code) | ~1 MB | ~3 MB | ~5 MB |
| Agent slots | Shared pool | Shared pool | Shared pool |
| Dashboard widgets | +2 per page | +6 per page | +10 per page |
| DB rows (rules) | ~500 | ~1500 | ~2500 |

**AOG: SQLite handles 2500 rows easily. No scaling concern.**

### 14.3 AOG Final Verdict

| Question | Answer |
|----------|--------|
| Multi-subsystem scaling requires new infrastructure? | **No.** Plugin architecture handles it. |
| Is there a real scaling bottleneck? | **No.** SQLite + plugin model scales to 10+ subsystems. |
| Should we plan for sharding/partitioning? | **No.** Not needed until 100K+ rules. |

---

## SELF-VALIDATION

| Artifact | P2 Status | AOG Pass | Complexity |
|----------|-----------|----------|------------|
| Plugin Marketplace | Interface only (P3+) | Yes | None in P2 |
| Subsystem Extension | Full (7 extension points) | Yes | Low |
| Multi-subsystem Scaling | Analysis: no changes needed | Yes | None |
