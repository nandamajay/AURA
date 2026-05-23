# AURA Boundary Charter

Date: 2026-05-18
Purpose: permanent separation contract across layers

## Layer Contract Matrix

### Layer 1: Core runtime layer
Allowed responsibilities:
- Service bootstrapping, configuration loading, shared primitives, deterministic process lifecycle.
Forbidden responsibilities:
- Domain-specific business logic, plugin-specific policy, external side-effect logic without governance.
Allowed dependencies:
- Standard libs, shared SDK internals, deterministic infrastructure primitives.
Forbidden dependencies:
- Domain application modules, UI modules, ad-hoc external connectors.

### Layer 2: Orchestration layer
Allowed responsibilities:
- Queue scheduling, agent lifecycle control, retry scheduling, watchdog enforcement, event routing.
Forbidden responsibilities:
- Governance policy authoring, business workflow decisions, plugin trust policy changes.
Allowed dependencies:
- Core runtime, replay/governance service interfaces.
Forbidden dependencies:
- Domain workflow implementations, operator UI code.

### Layer 3: Replay/governance layer
Allowed responsibilities:
- Replay recording/finalization, governance gate checks, approval transition enforcement, audit ledger integrity.
Forbidden responsibilities:
- Scheduling policy ownership, domain-specific workflow branching, UI presentation logic.
Allowed dependencies:
- Core runtime storage/transaction interfaces.
Forbidden dependencies:
- Plugin-specific business logic, frontend concerns.

### Layer 4: Plugin runtime layer
Allowed responsibilities:
- Plugin registration, capability declaration, bounded plugin execution hooks, domain tagging.
Forbidden responsibilities:
- Core governance transition mutation, direct queue ownership, direct replay finalization mutation.
Allowed dependencies:
- Orchestration extension interfaces, replay/governance APIs via controlled contracts.
Forbidden dependencies:
- Direct DB mutation bypassing core services, direct audit-chain manipulation.

### Layer 5: Domain workflow layer
Allowed responsibilities:
- Domain tasks, policy translation, domain-specific execution plans, domain evidence generation.
Forbidden responsibilities:
- Global retry policy, global queue policy, global governance semantics.
Allowed dependencies:
- Plugin runtime interfaces, application layer contracts.
Forbidden dependencies:
- Direct core internals or transport internals.

### Layer 6: Application layer
Allowed responsibilities:
- Product-level use-case composition, API-level user workflows, operator action surfaces.
Forbidden responsibilities:
- Deterministic kernel mutation, replay hash semantics, governance core rewrite.
Allowed dependencies:
- Domain workflow and operator layer contracts.
Forbidden dependencies:
- Direct low-level DB writes bypassing governance/replay services.

### Layer 7: Operator layer
Allowed responsibilities:
- Runtime visibility, replay inspection, governance timeline inspection, intervention and override workflows.
Forbidden responsibilities:
- Hidden state mutation, bypassing audit/governance controls, implicit policy changes.
Allowed dependencies:
- Application API surfaces.
Forbidden dependencies:
- Direct state mutation channels that bypass API governance.

### Layer 8: External integration edge
Allowed responsibilities:
- Explicitly governed provider calls (LLM and future external systems), adapter-level normalization.
Forbidden responsibilities:
- Inbound control-plane ownership, autonomous policy mutation, hidden retries without audit visibility.
Allowed dependencies:
- Application/orchestration integration interfaces with governance gating.
Forbidden dependencies:
- Direct writes into replay/audit/governance storage.

## Cross-Layer Dependency Rules
Allowed dependency direction:
- Top-down only (Operator -> ... -> Core runtime).
- No upward calls from lower layers into higher-level domain/application/UI logic.

Forbidden patterns:
- Circular dependencies across layers.
- Plugin runtime directly importing operator/application modules.
- Domain workflow directly importing core persistence internals.
- UI client defining or mutating governance policy logic.

## AI Agency / Business Logic Exclusion Policy for `aura-core`
The following MUST NEVER enter `aura-core`:
- Commercial pipeline logic (deal stages, pricing logic, revenue forecasting).
- CRM-like orchestration (lead scoring, account prioritization, campaign planning).
- Business-specific decision policy not tied to runtime correctness.
- Organization-specific workflow semantics that do not impact deterministic runtime safety.

Reason:
`aura-core` is a correctness kernel, not a business application container.
