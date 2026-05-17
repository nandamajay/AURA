# AURA P2 — Dashboard UX, Navigation & Engineering Workflow
## Artifacts: 1, 2, 3 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Dashboard structure, React+Vite+TS stack)

---

## ARTIFACT 1: DASHBOARD UX SPECIFICATION

### 1.1 Design Philosophy

```
PRINCIPLE: Engineering Mission Control
  - Information density over minimalism
  - Real-time updates over static displays
  - Action-oriented: every page enables decisions
  - Context-preserving: navigation doesn't lose state

ANTI-PATTERNS AVOIDED:
  - No marketing-style whitespace excess
  - No animation for decoration
  - No hidden navigation
  - No modal-only interactions
  - No data without context

INSPIRATION: Grafana, Kubernetes Dashboard, GitLab CI
```

### 1.2 12-Page Specification

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AURA                                                                      ≡ │  ← Header (always visible)
├──────────┬───────────────────────────────────────────────────────────────────┤
│          │                                                                   │
│ Global   │  [Page Title]                              [Filters] [Refresh]   │
│ Command  │                                                                   │
│ Center   │  ┌─────────────────────────────────────────────────────────┐    │
│          │  │  Content Area (responsive grid)                         │    │
│ Driver   │  │                                                         │    │
│ Migration│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐              │    │
│          │  │  │ Widget   │ │ Widget   │ │ Widget   │              │    │
│ Knowledge│  │  │          │ │          │ │          │              │    │
│ Graph    │  │  └──────────┘ └──────────┘ └──────────┘              │    │
│          │  │                                                         │    │
│ Maintainer│  │  ┌─────────────────────────────────────────────┐     │    │
│ Intel    │  │  │ Full-width visualization                     │     │    │
│          │  │  │                                              │     │    │
│ Learning │  │  └─────────────────────────────────────────────┘     │    │
│          │  │                                                         │    │
│ Agent    │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐              │    │
│ Observ.  │  │  │ Table    │ │ Chart    │ │ Details  │              │    │
│          │  │  └──────────┘ └──────────┘ └──────────┘              │    │
│ Arch.    │  └─────────────────────────────────────────────────────────┘    │
│ Lab      │                                                                   │
│          │  Status: Connected  |  12 agents active  |  Last updated: 10:30 │  ← Footer
│ Patch    │                                                                   │
│ Review   │
│          │
│ Debug    │
│          │
│ Sim.     │
│ Control  │
│          │
│ Approval │
│ Ops      │
│          │
│ Govern.  │
│ Command  │
│          │
└──────────┘
```

### 1.3 Page Specifications

**Page 1: Global Command Center**
```
Purpose:      System-wide status, health, and control
Widgets:
  - System health card (green/yellow/red)
  - Active agent count by type (bar chart)
  - Task queue depth by priority (stacked bar)
  - LLM token usage today (progress bar + $)
  - Recent events feed (scrollable list)
  - Quick actions: pause/resume, emergency stop
Refresh:      5 seconds (WebSocket)
Layout:       3-column grid on desktop, single column on mobile
```

**Page 2: Driver Migration Center**
```
Purpose:      Track migration of individual drivers
Widgets:
  - Driver list table (sortable, filterable)
  - Per-driver status pipeline (visual)
  - Confidence score per driver (gauge)
  - Dependency tree preview (collapsible)
  - Action: submit driver for migration
  - Action: view migration history
Refresh:      10 seconds
Layout:       Table primary, detail sidebar
```

**Page 3: Knowledge Graph Center**
```
Purpose:      Browse migration rules and evidence
Widgets:
  - Search bar with FTS (full-text search)
  - Rule list with confidence indicators
  - Evidence links with source references
  - Tag cloud of categories
  - Action: export rules to JSON/CSV
  - Action: add manual rule (admin only)
Refresh:      On search/query (no auto-refresh)
Layout:       Search top, results in grid
```

**Page 4: Maintainer Intelligence Center**
```
Purpose:      Understand upstream maintainer preferences
Widgets:
  - Maintainer profile cards
  - Acceptance rate charts
  - Common NAK reasons (word cloud)
  - Patch history with outcomes
Refresh:      Weekly (data changes slowly)
Layout:       Cards grid, detail on click
```

**Page 5: Learning Center**
```
Purpose:      View what AURA has learned
Widgets:
  - Learning event timeline
  - Pattern discovery cards
  - Confidence evolution graphs
  - Tier breakdown (4-tier learning)
  - Action: trigger manual learning
Refresh:      On demand + after learning events
Layout:       Timeline primary, cards secondary
```

**Page 6: Live Agent Observability**
```
Purpose:      Real-time agent monitoring
Widgets:
  - Agent grid (status cards, color-coded)
  - Live log stream (tail -f style)
  - Resource usage (CPU/MEM per agent)
  - Circuit breaker states
  - Action: kill agent, restart agent
Refresh:      2 seconds (WebSocket)
Layout:       Grid of agents + log panel
```

**Page 7: Architecture Lab**
```
Purpose:      Interactive architecture exploration
Widgets:
  - DAPM topology diagram (Canvas)
  - SoundWire bus diagram (Canvas)
  - Component relationship graph (D3.js)
  - Action: run simulation
  - Action: view probe flow
Refresh:      On interaction (no auto-refresh)
Layout:       Canvas primary, controls sidebar
```

**Page 8: Patch Review War Room**
```
Purpose:      Review generated patches
Widgets:
  - Diff viewer (CodeMirror, side-by-side)
  - Inline maintainer simulation comments
  - Approval status (3-dim matrix)
  - Evidence panel (linked to rules)
  - Action: approve, reject, request rework
  - Action: submit for upstream
Refresh:      On navigation (static page)
Layout:       Diff primary, panels on sides
```

**Page 9: Debugging Center**
```
Purpose:      Troubleshoot failures
Widgets:
  - Error log viewer (filterable, searchable)
  - Agent output inspector
  - Task replay viewer
  - Stack trace analyzer
  - Action: replay task, view raw output
Refresh:      On demand
Layout:       Log viewer primary, inspector sidebar
```

**Page 10: Simulation Control Center**
```
Purpose:      Run and monitor simulations
Widgets:
  - Simulation list (type, status, fidelity)
  - Results panel (findings, confidence impact)
  - Toggle: state-machine vs QEMU
  - Scenario selector (dropdown)
  - Action: start simulation
  - Action: view detailed results
Refresh:      5 seconds during simulation, static after
Layout:       List + results split
```

**Page 11: Approval Operations Center**
```
Purpose:      Manage approval workflow
Widgets:
  - Pending approvals queue
  - Approval matrix (3-dim visual)
  - Escalation alerts
  - Approval history
  - Action: approve, reject, escalate
  - Action: assign reviewer
Refresh:      10 seconds
Layout:       Queue primary, matrix secondary
```

**Page 12: Governance Command Center**
```
Purpose:      Admin governance view
Widgets:
  - User management table
  - RBAC role assignment
  - Audit log viewer (paginated, filterable)
  - System configuration
  - Action: add user, change role
  - Action: export audit log
Refresh:      On interaction (admin actions)
Layout:       Tabs: Users, Roles, Audit, Config
```

---

## ARTIFACT 2: MULTI-PAGE NAVIGATION ARCHITECTURE

### 2.1 Navigation Model

```
PERSISTENT ELEMENTS (all pages):
  ├─ Header: Logo + Global Search + Notifications + User Menu
  ├─ Sidebar: Page navigation (12 links)
  ├─ Breadcrumbs: Context trail
  └─ Footer: Connection status + Agent count + Last refresh

PAGE STATE:
  - Filters persist across navigation (stored in URL query params)
  - Selected items persist in session storage
  - Scroll position NOT preserved (pages scroll to top)
  - Real-time connections (WS) re-established on navigation

MOBILE (< 768px):
  - Sidebar becomes hamburger menu
  - Content single column
  - Footer becomes bottom nav (3 items)
```

### 2.2 Route Structure

```typescript
// React Router configuration
const routes = [
  { path: "/", element: <GlobalCommandCenter />, label: "Command Center" },
  { path: "/migration", element: <DriverMigrationCenter />, label: "Migration" },
  { path: "/knowledge", element: <KnowledgeGraphCenter />, label: "Knowledge" },
  { path: "/maintainers", element: <MaintainerIntelligenceCenter />, label: "Maintainers" },
  { path: "/learning", element: <LearningCenter />, label: "Learning" },
  { path: "/agents", element: <LiveAgentObservability />, label: "Agents" },
  { path: "/architecture", element: <ArchitectureLab />, label: "Architecture" },
  { path: "/patches", element: <PatchReviewWarRoom />, label: "Patches" },
  { path: "/debug", element: <DebuggingCenter />, label: "Debug" },
  { path: "/simulation", element: <SimulationControlCenter />, label: "Simulation" },
  { path: "/approvals", element: <ApprovalOperationsCenter />, label: "Approvals" },
  { path: "/governance", element: <GovernanceCommandCenter />, label: "Governance" },
];
```

### 2.3 State Management

```typescript
// Zustand store (lightweight, no Redux boilerplate)
interface DashboardState {
  // Persistent (localStorage)
  theme: 'light' | 'dark';
  sidebarCollapsed: boolean;
  
  // Session (sessionStorage)
  activeFilters: Record<string, string>;
  selectedItems: string[];
  
  // Ephemeral (memory only)
  wsConnected: boolean;
  notifications: Notification[];
  globalError: string | null;
}
```

---

## ARTIFACT 3: ENGINEERING WORKFLOW UX

### 3.1 Core Workflow: Submit → Migrate → Review → Approve

```
STEP 1: SUBMIT DRIVER
  Actor: Human engineer
  UI: Driver Migration Center → "New Migration" button
  Input: Kernel source path (downstream driver)
  Action: POST /api/v1/tasks (creates migration task)
  Feedback: Task queued toast, appears in queue

STEP 2: ORCHESTRATOR SCHEDULES
  Actor: System (orchestrator)
  UI: Live Agent Observability shows agent spawning
  Visible: Agent status → "running", progress bar starts
  Feedback: Real-time WebSocket updates

STEP 3: AGENTS EXECUTE
  Actor: System (agents)
  UI: Progress updates, partial results appear
  Visible: Learning → Dependency → Refactor → Validation
  Feedback: Per-agent progress, confidence scores

STEP 4: SIMULATION (optional)
  Actor: System (simulation engine)
  UI: Simulation Control Center
  Visible: Probe flow, DAPM state changes
  Feedback: Pass/fail with findings

STEP 5: REVIEW PATCH
  Actor: Human engineer
  UI: Patch Review War Room
  Input: Diff viewer, maintainer comments, evidence
  Action: Approve, reject, or request rework
  Feedback: Approval matrix updates

STEP 6: APPROVE FOR UPSTREAM
  Actor: Human approver/architect
  UI: Approval Operations Center
  Input: Final approval with comments
  Action: POST /api/v1/approvals/{id}/grant
  Output: Patch marked "upstream-ready"
```

### 3.2 Chat Panel (Persistent)

```
Position:    Bottom-right corner (collapsible)
Purpose:     Quick actions, status queries, notifications
Features:
  - System messages (events, alerts)
  - Quick commands: /status, /agents, /queue
  - Context-aware: shows relevant info for current page
  - NOT a general chatbot (avoids complexity)
Height:      400px expanded, 48px collapsed
```

---

## SELF-VALIDATION (AOG)

| Question | Answer |
|----------|--------|
| Are 12 pages too many? | **No.** Each page maps to a distinct workflow from original specs. |
| Is the design over-engineered? | **No.** Standard dashboard pattern, no custom frameworks. |
| Does this add operational burden? | **No.** Static React app, served by nginx. |
| Is WebSocket justified? | **Yes.** Real-time agent status is core value proposition. |
| Are the pages actionable? | **Yes.** Every page has clear actions, not just data display. |
