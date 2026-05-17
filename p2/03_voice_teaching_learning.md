# AURA P2 — Voice/Narration, Interactive Teaching & Autonomous Learning Evolution
## Artifacts: 9, 10, 20 | Anti-Overengineering: Applied
### Built on: Frozen P0 (Event Bus, Dashboard, Agent SDK, Knowledge System)

---

## ARTIFACT 9: VOICE + NARRATION ARCHITECTURE

### 9.1 Source-Derived Requirements

From File #5 (Dashboard): "Voice output during architectural reasoning" — optional feature
From File #12 (Engineering Workflow): "Voice output capabilities for accessibility and workflow narration" — accessibility, not core

### 9.2 P2 Architecture (Interface Only — P3+ Implementation)

```typescript
// dashboard/src/voice/VoiceEngine.ts
// P2: Interface defined. P3+: Implementation.

interface VoiceEngine {
  /** Check if voice synthesis is available in browser. */
  isAvailable(): boolean;
  
  /** Speak a message. Interrupts current speech. */
  speak(message: string, priority?: 'normal' | 'urgent'): void;
  
  /** Stop current speech. */
  stop(): void;
  
  /** Enable/disable voice globally. */
  setEnabled(enabled: boolean): void;
  
  /** Set speech rate (0.5 - 2.0). */
  setRate(rate: number): void;
}

// P3+ implementation uses Web Speech API (built into browsers)
class BrowserVoiceEngine implements VoiceEngine {
  private synth = window.speechSynthesis;
  private utterance: SpeechSynthesisUtterance | null = null;
  private enabled = false;
  
  speak(message: string, priority = 'normal') {
    if (!this.enabled) return;
    this.stop();
    this.utterance = new SpeechSynthesisUtterance(message);
    this.utterance.rate = this.rate;
    this.synth.speak(this.utterance);
  }
  
  // ... implementation
}
```

### 9.3 AOG Assessment

| Question | Answer |
|----------|--------|
| Required for MVP? | **No.** Accessibility enhancement, not core functionality. |
| Can this be simpler? | **Yes.** Web Speech API, no backend dependency. |
| Operational burden? | **Zero.** Client-side only. |
| Justified in P2? | **Yes.** Interface defined, not implemented. Zero cost. |

### 9.4 Narration Points (Event-Driven)

Voice triggers on these events only:
- `TASK_COMPLETED` → "Learning agent completed. Found 15 patterns."
- `APPROVAL_REQUIRED` → "Patch ready for review."
- `ESCALATION_TRIGGERED` → "Attention required: escalation triggered."
- `CIRCUIT_BREAKER_STATE` (OPEN) → "Warning: circuit breaker open for {type}."

---

## ARTIFACT 10: INTERACTIVE TEACHING ENGINE

### 10.1 Source-Derived Requirements

From File #12 (Engineering Workflow): "Engineering Workflow Interface + Interactive Orchestration UX" — teaching via guided exploration

### 10.2 P2 Architecture (Interface + Basic Implementation)

```typescript
// dashboard/src/teaching/TeachingEngine.ts

interface TeachingStep {
  id: string;
  title: string;
  content: string;           // Markdown explanation
  targetElement?: string;    // CSS selector to highlight
  actionRequired?: 'click' | 'observe' | 'input';
  nextCondition?: () => boolean;
}

interface TeachingFlow {
  id: string;
  name: string;
  steps: TeachingStep[];
  trigger: 'first_visit' | 'manual' | 'event';
}

// Built-in teaching flows
const DEFAULT_FLOWS: TeachingFlow[] = [
  {
    id: "first_time_setup",
    name: "Welcome to AURA",
    trigger: "first_visit",
    steps: [
      {
        id: "welcome",
        title: "Welcome to AURA",
        content: "AURA helps you upstream Qualcomm Audio drivers to the Linux kernel. Let's take a quick tour.",
        targetElement: "[data-testid=dashboard-title]",
      },
      {
        id: "navigation",
        title: "Navigation",
        content: "These 12 pages cover all aspects of the upstreaming workflow.",
        targetElement: "[data-testid=sidebar]",
      },
      {
        id: "submit_driver",
        title: "Submit a Driver",
        content: "Start by submitting a downstream driver for migration.",
        targetElement: "[data-testid=submit-driver]",
        actionRequired: "click",
      },
    ],
  },
  {
    id: "approval_workflow",
    name: "Understanding Approvals",
    trigger: "manual",
    steps: [
      {
        id: "approval_matrix",
        title: "3-Dimensional Approval",
        content: "Patches must pass lifecycle, subsystem, AND quality reviews.",
        targetElement: "[data-testid=approval-matrix]",
      },
    ],
  },
];
```

### 10.3 AOG Assessment

| Question | Answer |
|----------|--------|
| Required for MVP? | **No.** Onboarding aid. |
| Can this be simpler? | **Yes.** CSS overlay + step array. No backend. |
| Operational burden? | **Zero.** Client-side React component. |
| Justified in P2? | **Yes.** Improves onboarding for 20 users. Simple implementation. |

---

## ARTIFACT 20: AUTONOMOUS LEARNING EVOLUTION STRATEGY

### 20.1 4-Tier Learning Architecture (Frozen from P0)

```
Tier 1: Kernel Pattern Learning (File #3)
  - Downstream-vs-upstream comparison
  - Migration rule extraction
  - Pattern validation against upstreamed drivers
  
Tier 2: Maintainer Intelligence (File #4)
  - Reviewer personality modeling
  - Acceptance prediction per maintainer
  - NAK reason analysis from LKML
  
Tier 3: Cross-Subsystem Transfer (File #6)
  - Pattern transfer across camera/DRM/GPU/etc.
  - Common patterns: runtime PM, regmap, managed resources
  
Tier 4: Upstream Suitability (File #13)
  - Rejection prediction
  - Philosophy alignment scoring
  - DCO/SPDX compliance validation
```

### 20.2 P2 Implementation: Tier 1 + Tier 2

**Tier 1 (P2 — Implemented):**
```python
# agents/learning.py — Already specified in P0
# Extracts patterns from upstreamed drivers
# Stores in migration_rules table
# Confidence evolves with validation feedback
```

**Tier 2 (P2 — Architecture, P3+ — Full):**
```python
# governance/maintainer_intel.py — P2 interface
class MaintainerIntelligenceEngine:
    """
    P2: Interface and basic profile storage.
    P3+: Full LKML mining, personality modeling.
    """
    
    async def get_profile(self, email: str) -> MaintainerProfile:
        """Get maintainer profile from DB."""
        pass
    
    async def predict_acceptance(self, patch: Patch, maintainer_email: str) -> float:
        """Predict acceptance probability (0-1). P3+: ML model."""
        # P2: Simple heuristic based on historical data
        pass
    
    async def analyze_lkml_thread(self, thread_url: str) -> list[NAKReason]:
        """Extract NAK reasons from LKML thread. P3+: Full mining."""
        pass
```

**Tier 3 (P3+ — Strategy):**
- Activated when second subsystem plugin loads
- Transfers validated patterns from audio to new subsystem
- Requires: pattern abstraction, similarity scoring

**Tier 4 (P3+ — Strategy):**
- Activated when upstream submission preparation begins
- Predicts rejection likelihood
- Requires: LKML history database, feature extraction

### 20.3 AOG Assessment

| Question | Answer |
|----------|--------|
| All 4 tiers in P2? | **No.** Only Tier 1 implemented. Tier 2 interface defined. Tiers 3-4 are P3+ strategies. |
| Is this overengineered? | **No.** Incremental: Tier 1 works now, others layer on. |
| Does it improve determinism? | **Yes.** Learning produces rules that make agent behavior more predictable. |

---

## SELF-VALIDATION

| Artifact | P2 Status | AOG Pass | Complexity |
|----------|-----------|----------|------------|
| Voice/Narration | Interface only | Yes | Low (client-side Web API) |
| Teaching Engine | Interface + basic | Yes | Low (CSS overlay) |
| Learning Evolution | Tier 1 full, Tier 2 interface | Yes | Medium (justified by 4-tier design) |
