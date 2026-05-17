import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { type TeachingFlow } from '../teaching/TeachingEngine'

interface TeachingOverlayProps {
  flow: TeachingFlow | null
  open: boolean
  onClose: () => void
  onComplete: (flowId: string) => void
}

interface TargetRect {
  top: number
  left: number
  width: number
  height: number
}

export default function TeachingOverlay({ flow, open, onClose, onComplete }: TeachingOverlayProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null)
  const [actionSatisfied, setActionSatisfied] = useState(false)

  const step = useMemo(() => {
    if (!flow) {
      return null
    }
    return flow.steps[stepIndex] || null
  }, [flow, stepIndex])

  useEffect(() => {
    if (!open) {
      setStepIndex(0)
      setTargetRect(null)
      setActionSatisfied(false)
    }
  }, [open])

  useEffect(() => {
    if (!open || !step) {
      return
    }

    const selector = step.targetElement
    if (!selector) {
      setTargetRect(null)
      setActionSatisfied(true)
      return
    }

    const element = document.querySelector(selector) as HTMLElement | null
    if (!element) {
      setTargetRect(null)
      setActionSatisfied(step.actionRequired !== 'click' && step.actionRequired !== 'input')
      return
    }

    const updateRect = () => {
      const rect = element.getBoundingClientRect()
      setTargetRect({
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      })
    }

    updateRect()
    const interval = window.setInterval(updateRect, 250)
    window.addEventListener('resize', updateRect)
    window.addEventListener('scroll', updateRect, true)

    const requiresAction = step.actionRequired === 'click' || step.actionRequired === 'input'
    setActionSatisfied(!requiresAction)

    function satisfyAction() {
      setActionSatisfied(true)
    }

    if (step.actionRequired === 'click') {
      element.addEventListener('click', satisfyAction)
    }
    if (step.actionRequired === 'input') {
      element.addEventListener('input', satisfyAction)
    }

    return () => {
      window.clearInterval(interval)
      window.removeEventListener('resize', updateRect)
      window.removeEventListener('scroll', updateRect, true)
      element.removeEventListener('click', satisfyAction)
      element.removeEventListener('input', satisfyAction)
    }
  }, [open, step])

  if (!open || !flow || !step) {
    return null
  }

  const flowId = flow.id
  const isLastStep = stepIndex >= flow.steps.length - 1
  const canAdvance = !step.actionRequired || actionSatisfied

  function closeAndReset() {
    setStepIndex(0)
    onClose()
  }

  function goNext() {
    if (!canAdvance) {
      return
    }
    if (isLastStep) {
      onComplete(flowId)
      closeAndReset()
      return
    }
    setStepIndex((prev) => prev + 1)
  }

  function goPrevious() {
    setStepIndex((prev) => Math.max(0, prev - 1))
  }

  return (
    <div style={overlayStyle}>
      {targetRect ? <div style={highlightStyle(targetRect)} /> : null}
      <section style={panelStyle}>
        <div style={{ marginBottom: '0.5rem', fontSize: '0.76rem', color: '#64748b' }}>
          {flow.name} • Step {stepIndex + 1}/{flow.steps.length}
        </div>
        <h3 style={{ margin: '0 0 0.4rem', fontSize: '1rem' }}>{step.title}</h3>
        <p style={{ margin: 0, fontSize: '0.9rem', color: '#334155' }}>{step.content}</p>
        {step.actionRequired ? (
          <p style={{ margin: '0.45rem 0 0', fontSize: '0.8rem', color: '#475569' }}>
            Action required: {step.actionRequired}
          </p>
        ) : null}
        <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.45rem', justifyContent: 'flex-end' }}>
          <button type="button" style={secondaryButtonStyle} onClick={goPrevious} disabled={stepIndex === 0}>
            Back
          </button>
          <button type="button" style={secondaryButtonStyle} onClick={closeAndReset}>
            Close
          </button>
          <button type="button" style={primaryButtonStyle(canAdvance)} onClick={goNext} disabled={!canAdvance}>
            {isLastStep ? 'Finish' : 'Next'}
          </button>
        </div>
      </section>
    </div>
  )
}

const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(15, 23, 42, 0.45)',
  zIndex: 60,
}

function highlightStyle(rect: TargetRect): CSSProperties {
  return {
    position: 'fixed',
    top: Math.max(rect.top - 6, 0),
    left: Math.max(rect.left - 6, 0),
    width: rect.width + 12,
    height: rect.height + 12,
    border: '2px solid #f59e0b',
    borderRadius: '8px',
    boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.45)',
    pointerEvents: 'none',
  }
}

const panelStyle: CSSProperties = {
  position: 'fixed',
  right: '1rem',
  bottom: '1rem',
  width: 'min(420px, calc(100vw - 2rem))',
  background: '#ffffff',
  border: '1px solid #dbe3ec',
  borderRadius: '10px',
  padding: '0.8rem 0.9rem',
  boxShadow: '0 12px 30px rgba(2, 6, 23, 0.25)',
}

const secondaryButtonStyle: CSSProperties = {
  border: '1px solid #475569',
  borderRadius: '6px',
  background: '#ffffff',
  color: '#0f172a',
  padding: '0.35rem 0.6rem',
  cursor: 'pointer',
  fontSize: '0.8rem',
}

function primaryButtonStyle(enabled: boolean): CSSProperties {
  return {
    border: '1px solid #0f172a',
    borderRadius: '6px',
    background: enabled ? '#0f172a' : '#94a3b8',
    color: '#ffffff',
    padding: '0.35rem 0.6rem',
    cursor: enabled ? 'pointer' : 'not-allowed',
    fontSize: '0.8rem',
  }
}
