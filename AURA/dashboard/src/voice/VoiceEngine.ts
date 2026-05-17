export type VoicePriority = 'normal' | 'urgent'

export interface VoiceEngine {
  /** Check if voice synthesis is available in the current runtime. */
  isAvailable(): boolean

  /** Speak a message. Implementations may interrupt current speech. */
  speak(message: string, priority?: VoicePriority): void

  /** Stop any active speech output. */
  stop(): void

  /** Enable or disable voice globally. */
  setEnabled(enabled: boolean): void

  /** Set speech rate (0.5 - 2.0). */
  setRate(rate: number): void
}

/**
 * P2 scope: interface-only default implementation.
 * P3+ can replace this with browser speech synthesis.
 */
export class StubVoiceEngine implements VoiceEngine {
  private enabled = false
  private rate = 1

  isAvailable(): boolean {
    return false
  }

  speak(_message: string, _priority: VoicePriority = 'normal'): void {
    if (!this.enabled) {
      return
    }
    // Interface-only stub: no runtime speech in P2.
  }

  stop(): void {
    // Interface-only stub: no runtime speech in P2.
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled
  }

  setRate(rate: number): void {
    this.rate = Math.min(2, Math.max(0.5, rate))
  }

  getRate(): number {
    return this.rate
  }
}

export type NarrationTriggerEvent =
  | 'task.completed'
  | 'governance.approval_required'
  | 'governance.escalation_triggered'
  | 'system.circuit_breaker_state'

export interface NarrationMessageFactory {
  build(payload: Record<string, unknown>): string
}

export const NARRATION_POINTS: Record<NarrationTriggerEvent, NarrationMessageFactory> = {
  'task.completed': {
    build: (payload) => {
      const patterns = Number(payload.patterns_found || 0)
      const safePatterns = Number.isFinite(patterns) ? patterns : 0
      return `Learning agent completed. Found ${safePatterns} patterns.`
    },
  },
  'governance.approval_required': {
    build: () => 'Patch ready for review.',
  },
  'governance.escalation_triggered': {
    build: () => 'Attention required. Escalation triggered.',
  },
  'system.circuit_breaker_state': {
    build: (payload) => {
      const state = String(payload.state || '').toUpperCase()
      const agentType = String(payload.agent_type || 'agent')
      if (state === 'OPEN') {
        return `Warning. Circuit breaker open for ${agentType}.`
      }
      return `Circuit breaker state updated for ${agentType}.`
    },
  },
}
