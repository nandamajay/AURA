# AURA P2 — Visualization Systems: Agent, Dependency, Replay, Timeline, Simulation, Knowledge Graph
## Artifacts: 4, 5, 6, 7, 8, 11 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Dashboard, Event Bus, Simulation Engine, Digital Twin)

---

## ARTIFACT 4: LIVE AGENT VISUALIZATION SYSTEM

### 4.1 Agent Grid Visualization

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT GRID (Live Agent Observability Page)                  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ learning-01  │  │ refactor-03  │  │ valid-02     │     │
│  │              │  │              │  │              │     │
│  │ [████████░░] │  │ [██████░░░░] │  │ [██████████] │     │
│  │ 80% complete │  │ 60% complete │  │ Done         │     │
│  │ CPU: 45%     │  │ CPU: 78%     │  │ Time: 45s    │     │
│  │ MEM: 512MB   │  │ MEM: 1.2GB   │  │ Rules: 15    │     │
│  │              │  │              │  │              │     │
│  │ [Kill] [Log] │  │ [Kill] [Log] │  │ [Output]     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  Color coding:                                               │
│  🟢 Green = Running normally                                 │
│  🟡 Yellow = Warning (high resource)                         │
│  🔴 Red = Failed / Timed out                                 │
│  ⚪ Gray = Queued / Not started                              │
│  🔵 Blue = Completed successfully                            │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Implementation

```typescript
// Agent card component
interface AgentCardProps {
  agentId: string;
  agentType: string;
  status: 'running' | 'queued' | 'completed' | 'failed' | 'timeout';
  progress: number;        // 0-100
  cpuPercent: number;
  memoryMb: number;
  duration: number;        // seconds
  taskId: string;
}

// Status colors (CSS)
const statusColors = {
  running:  '#22c55e',   // green-500
  queued:   '#9ca3af',   // gray-400
  completed:'#3b82f6',   // blue-500
  failed:   '#ef4444',   // red-500
  timeout:  '#f59e0b',   // amber-500
};

// WebSocket update (no polling)
useWebSocket({
  channels: ['agent.lifecycle'],
  onEvent: (event) => {
    if (event.event_type === 'agent.progress') {
      updateAgentProgress(event.payload.agent_id, event.payload.progress);
    }
  },
});
```

**AOG Check: Canvas/WebGL needed?** No. CSS grid + progress bars are sufficient. No WebGL complexity.

---

## ARTIFACT 5: DEPENDENCY GRAPH VISUALIZATION

### 5.1 D3.js Force-Directed Graph

```
┌─────────────────────────────────────────────────────────────┐
│  DEPENDENCY GRAPH                                            │
│                                                              │
│        ┌──────────┐                                         │
│        │ wcd934x.c │                                        │
│        └────┬─────┘                                        │
│             │ includes                                      │
│    ┌────────┼────────┐                                     │
│    ▼        ▼        ▼                                     │
│ ┌──────┐ ┌──────┐ ┌──────┐                                │
│ │soc.h │ │dapm.h│ │clk.h │                                │
│ └──┬───┘ └──┬───┘ └──┬───┘                                │
│    │ uses   │ uses   │                                     │
│    ▼        ▼        ▼                                     │
│ ┌──────────────────────────┐                                │
│ │ snd_soc_dai_set_sysclk() │                                │
│ └──────────────────────────┘                                │
│                                                              │
│  Legend:                                                     │
│  ─── solid = #include                                      │
│  - - dashed = API call                                      │
│  ··· dotted = macro dependency                             │
│                                                              │
│  Interaction:                                                │
│  - Click node: highlight connected paths                    │
│  - Double-click: navigate to source                         │
│  - Drag: rearrange layout                                   │
│  - Scroll: zoom                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Technical Implementation

```typescript
// D3.js force simulation (simpler than WebGL/Cytoscape)
import * as d3 from 'd3';

const width = 800, height = 600;

const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(100))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(width / 2, height / 2));

// SVG rendering (not Canvas — simpler, debuggable)
const svg = d3.select("#graph").append("svg")
  .attr("viewBox", [0, 0, width, height]);
```

**AOG Check: D3.js vs WebGL?** D3.js SVG is sufficient for < 1000 nodes. WebGL only needed for 10K+ nodes. Audio drivers have < 200 dependencies.

---

## ARTIFACT 6: REPLAY VISUALIZATION SYSTEM

### 6.1 Replay Timeline View

```
┌──────────────────────────────────────────────────────────────┐
│  REPLAY VIEWER                                               │
│                                                              │
│  Task: learning-driver-wcd934x                               │
│  Seed: 42 | Model: gpt-4o | Status: PERFECT MATCH          │
│  Hash: a1b2c3... == a1b2c3... ✅                           │
│                                                              │
│  Timeline:                                                   │
│  ├─ 00:00 Task started                                       │
│  ├─ 00:02 LLM Call #1 (system prompt)                       │
│  │         ├─ Prompt: "Analyze this driver..." [view]       │
│  │         └─ Response: "The driver uses..." [view]         │
│  ├─ 00:15 LLM Call #2 (pattern extraction)                  │
│  │         ├─ Prompt: "Extract patterns..." [view]          │
│  │         └─ Response: "[{"pattern":...}]" [view]         │
│  ├─ 00:45 Write findings.md                                 │
│  ├─ 00:45 Task completed                                     │
│  └─ Output hash: a1b2c3d4...                                │
│                                                              │
│  During replay:                                              │
│  ✅ All 12 LLM responses replayed                            │
│  ✅ Output hash matches                                      │
│  ✅ 45s duration (was 43s original — +2s logging overhead)  │
└──────────────────────────────────────────────────────────────┘
```

---

## ARTIFACT 7: TIMELINE + AUDIT VISUALIZATION

### 7.1 Audit Timeline

```
┌──────────────────────────────────────────────────────────────┐
│  AUDIT TIMELINE (Governance Command Center)                  │
│                                                              │
│  Filters: [All Events ▼] [User: All ▼] [Date range]        │
│                                                              │
│  2026-01-15                                                  │
│  ├─ 10:30:15  👤 admin        APPROVED patch-123            │
│  │            "Looks good, upstream-ready"                   │
│  ├─ 10:28:42  🤖 refactor     COMPLETED patch-123           │
│  │            confidence: 0.92                               │
│  ├─ 10:25:10  🤖 validation   PASSED patch-123              │
│  │            sparse: 0 warnings                             │
│  ├─ 10:20:00  👤 reviewer     COMMENTED patch-123           │
│  │            "Check indentation in line 145"                │
│  ├─ 10:15:33  🤖 learning     COMPLETED pattern-extraction  │
│  │            patterns: 15                                   │
│  └─ 10:00:00  👤 engineer     CREATED migration task         │
│               driver: wcd934x.c                              │
│                                                              │
│  Chain hash verification: ✅ Valid (all 1,247 records)      │
└──────────────────────────────────────────────────────────────┘
```

---

## ARTIFACT 8: SIMULATION VISUALIZATION ENGINE

### 8.1 DAPM Power Flow Visualization

```
┌──────────────────────────────────────────────────────────────┐
│  DAPM SIMULATION (Architecture Lab)                          │
│                                                              │
│  State: PLAYBACK ▶ │ Step: 23/45 | Widgets: 12 active       │
│                                                              │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐         │
│  │ AIF1IN   │─────►│ AIF1IN   │─────►│ HP       │         │
│  │ (source) │      │ (mux)    │      │ (output) │         │
│  │  [ON] 🟢 │      │  [ON] 🟢 │      │  [ON] 🟢 │         │
│  └──────────┘      └──────────┘      └──────────┘         │
│       ▲                                    │                │
│       │                                    │                │
│  ┌──────────┐      ┌──────────┐      ┌────┴─────┐         │
│  │ AIF2IN   │      │ RX1      │      │ SPK      │         │
│  │ [OFF] ⚪ │      │ [ON] 🟢  │      │ [ON] 🟢  │         │
│  └──────────┘      └──────────┘      └──────────┘         │
│                                                              │
│  Legend: 🟢 Active  ⚪ Inactive  ── Audio path              │
│                                                              │
│  Playback: [◀ Prev] [▶ Play/Pause] [Next ▶] [Reset]       │
│  Speed: [0.5x] [1x] [2x] [4x]                              │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Canvas API Implementation

```typescript
// Canvas-based simulation renderer (simpler than WebGL for MVP)
const canvas = document.getElementById('sim-canvas') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;

// Draw widget nodes
function drawWidget(widget: DAPMWidget, x: number, y: number) {
  ctx.fillStyle = widget.active ? '#22c55e' : '#9ca3af';
  ctx.fillRect(x - 40, y - 20, 80, 40);
  ctx.fillStyle = '#000';
  ctx.textAlign = 'center';
  ctx.fillText(widget.name, x, y + 5);
}

// Draw connections
function drawConnection(from: [number, number], to: [number, number], active: boolean) {
  ctx.strokeStyle = active ? '#22c55e' : '#d1d5db';
  ctx.lineWidth = active ? 3 : 1;
  ctx.beginPath();
  ctx.moveTo(from[0], from[1]);
  ctx.lineTo(to[0], to[1]);
  ctx.stroke();
}
```

**AOG Check: Canvas vs WebGL?** Canvas 2D is sufficient for < 100 widgets. DAPM graphs for audio have ~50 widgets. WebGL only needed for GPU-intensive rendering (10K+ particles).

---

## ARTIFACT 11: KNOWLEDGE GRAPH VISUALIZATION

### 11.1 Graph Structure

```
┌──────────────────────────────────────────────────────────────┐
│  KNOWLEDGE GRAPH                                             │
│                                                              │
│  [Search: _________] [Filter: ▼] [Layout: ▼]               │
│                                                              │
│        ┌──────────────┐                                     │
│        │Rule:         │                                     │
│        │soc_dai_write │◄────────────────────────┐          │
│        └──────┬───────┘                         │          │
│               │ applies to                      │          │
│    ┌──────────┼──────────┐                      │          │
│    ▼          ▼          ▼                      │          │
│ ┌──────┐  ┌──────┐  ┌──────┐                  │          │
│ │wcd   │  │wcd   │  │wcd   │                  │          │
│ │9340  │  │9370  │  │9380  │                  │          │
│ └──┬───┘  └──┬───┘  └──┬───┘                  │          │
│    │ uses    │ uses   │ uses                   │          │
│    ▼         ▼        ▼                        │          │
│ ┌──────────────────────────────────────────┐   │          │
│ │ Evidence: "Used in upstream wcd934x.c"  │───┘          │
│ │ Source: commit abc123, sound/soc/...    │              │
│ │ Confidence: 0.92                        │              │
│ └──────────────────────────────────────────┘              │
│                                                              │
│  Click node: show details panel                             │
│  Click edge: show relationship evidence                     │
│  Right-click: context menu (navigate, filter)               │
└──────────────────────────────────────────────────────────────┘
```

### 11.2 Implementation: D3.js Force Graph

```typescript
// Same approach as dependency graph (D3.js SVG)
// Nodes: Rules, Evidence, Maintainers, Patches
// Edges: applies_to, supports, contradicts, derives_from

const knowledgeGraph = {
  nodes: [
    { id: "rule-1", type: "rule", label: "soc_dai_write", confidence: 0.92 },
    { id: "ev-1", type: "evidence", label: "upstream commit abc123" },
    { id: "maint-1", type: "maintainer", label: "Mark Brown" },
  ],
  links: [
    { source: "rule-1", target: "ev-1", type: "supports" },
    { source: "ev-1", target: "maint-1", type: "reviewed_by" },
  ],
};
```

**AOG Check:** Same D3.js approach as dependency graph. Code reusable. No new framework.

---

## SELF-VALIDATION

| Artifact | Tech | AOG Pass | Justification |
|----------|------|----------|---------------|
| Agent Grid | CSS + React | Yes | No library needed |
| Dependency Graph | D3.js SVG | Yes | < 1000 nodes, SVG sufficient |
| Replay Timeline | React list | Yes | Simple list view |
| Audit Timeline | React list | Yes | Simple list view |
| Simulation | Canvas 2D | Yes | < 100 widgets, Canvas sufficient |
| Knowledge Graph | D3.js SVG | Yes | Same pattern as dependency |
