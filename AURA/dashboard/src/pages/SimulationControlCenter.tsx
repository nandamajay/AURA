import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface Scenario {
  id: string
  name: string
  description: string
  fidelity_modes: string[]
}

interface ScenariosResponse {
  scenarios: Scenario[]
}

interface SimulationStartResponse {
  simulation_id: string
  status: string
  simulation_type: string
  fidelity: string
}

interface SimulationStatusResponse {
  simulation_id: string
  status: string
  simulation_type: string
  fidelity_mode: string
  findings: Record<string, unknown>
  failure_predictions: string[]
  confidence_impact: number
  duration_ms: number | null
}

interface WidgetNode {
  id: string
  label: string
  x: number
  y: number
}

interface WidgetConnection {
  from: string
  to: string
}

const CANVAS_WIDTH = 940
const CANVAS_HEIGHT = 360

const DAPM_WIDGETS: WidgetNode[] = [
  { id: 'aif1in', label: 'AIF1IN', x: 120, y: 70 },
  { id: 'mux1', label: 'AIF1 MUX', x: 300, y: 70 },
  { id: 'rx1', label: 'RX1', x: 490, y: 70 },
  { id: 'hp', label: 'HP', x: 680, y: 70 },
  { id: 'spk', label: 'SPK', x: 860, y: 70 },
  { id: 'aif2in', label: 'AIF2IN', x: 120, y: 220 },
  { id: 'rx2', label: 'RX2', x: 490, y: 220 },
  { id: 'adc', label: 'ADC', x: 680, y: 220 },
]

const DAPM_CONNECTIONS: WidgetConnection[] = [
  { from: 'aif1in', to: 'mux1' },
  { from: 'mux1', to: 'rx1' },
  { from: 'rx1', to: 'hp' },
  { from: 'hp', to: 'spk' },
  { from: 'aif2in', to: 'rx2' },
  { from: 'rx2', to: 'adc' },
  { from: 'rx2', to: 'spk' },
]

const DAPM_FRAMES: string[][] = [
  ['aif1in'],
  ['aif1in', 'mux1'],
  ['aif1in', 'mux1', 'rx1'],
  ['aif1in', 'mux1', 'rx1', 'hp'],
  ['aif1in', 'mux1', 'rx1', 'hp', 'spk'],
  ['aif1in', 'mux1', 'rx1', 'hp', 'spk', 'aif2in'],
  ['aif1in', 'mux1', 'rx1', 'hp', 'spk', 'aif2in', 'rx2'],
  ['aif1in', 'mux1', 'rx1', 'hp', 'spk', 'aif2in', 'rx2', 'adc'],
]

const SPEED_OPTIONS = [0.5, 1, 2, 4]

function widgetById(widgetId: string): WidgetNode | undefined {
  return DAPM_WIDGETS.find((widget) => widget.id === widgetId)
}

export default function SimulationControlCenter() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  const [patchId, setPatchId] = useState('')
  const [simulationType, setSimulationType] = useState('')
  const [fidelity, setFidelity] = useState('state_machine')
  const [startResult, setStartResult] = useState<SimulationStartResponse | null>(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusResult, setStatusResult] = useState<SimulationStatusResponse | null>(null)

  const [frameIndex, setFrameIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  const { data: scenarios } = useApiData<ScenariosResponse>(API_ROUTES.simulation.scenarios(), { intervalMs: 30_000 })

  const scenarioList = scenarios?.scenarios || []
  const selectedScenario = scenarioList.find((scenario) => scenario.id === simulationType)
  const activeWidgets = useMemo(() => new Set(DAPM_FRAMES[frameIndex] || []), [frameIndex])

  useEffect(() => {
    if (!simulationType && scenarioList.length > 0) {
      setSimulationType(scenarioList[0].id)
    }
  }, [scenarioList, simulationType])

  useEffect(() => {
    if (!playing) {
      return
    }
    const intervalMs = Math.max(100, Math.round(900 / speed))
    const timer = window.setInterval(() => {
      setFrameIndex((prev) => (prev + 1) % DAPM_FRAMES.length)
    }, intervalMs)
    return () => window.clearInterval(timer)
  }, [playing, speed])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      return
    }

    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
    ctx.fillStyle = '#f8fafc'
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

    ctx.strokeStyle = '#cbd5e1'
    ctx.lineWidth = 1
    ctx.strokeRect(0.5, 0.5, CANVAS_WIDTH - 1, CANVAS_HEIGHT - 1)

    for (const connection of DAPM_CONNECTIONS) {
      const from = widgetById(connection.from)
      const to = widgetById(connection.to)
      if (!from || !to) {
        continue
      }

      const active = activeWidgets.has(connection.from) && activeWidgets.has(connection.to)
      ctx.strokeStyle = active ? '#22c55e' : '#cbd5e1'
      ctx.lineWidth = active ? 3 : 1.5
      ctx.beginPath()
      ctx.moveTo(from.x + 44, from.y)
      ctx.lineTo(to.x - 44, to.y)
      ctx.stroke()
    }

    for (const widget of DAPM_WIDGETS) {
      const active = activeWidgets.has(widget.id)
      ctx.fillStyle = active ? '#22c55e' : '#94a3b8'
      ctx.strokeStyle = active ? '#15803d' : '#64748b'
      ctx.lineWidth = 2
      ctx.fillRect(widget.x - 44, widget.y - 20, 88, 40)
      ctx.strokeRect(widget.x - 44, widget.y - 20, 88, 40)

      ctx.fillStyle = '#0f172a'
      ctx.font = '12px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(widget.label, widget.x, widget.y + 4)
      ctx.font = '11px sans-serif'
      ctx.fillText(active ? 'ON' : 'OFF', widget.x, widget.y + 18)
    }

    ctx.fillStyle = '#1e293b'
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'left'
    ctx.fillText(
      `DAPM Playback  Step: ${frameIndex + 1}/${DAPM_FRAMES.length}  Active widgets: ${activeWidgets.size}`,
      12,
      22,
    )
  }, [activeWidgets, frameIndex])

  useEffect(() => {
    if (!startResult?.simulation_id) {
      return
    }

    const timer = window.setInterval(() => {
      void checkStatus(startResult.simulation_id)
    }, 5_000)
    return () => window.clearInterval(timer)
  }, [startResult?.simulation_id])

  async function startSimulation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setRunning(true)
    setError('')
    setStartResult(null)
    setStatusResult(null)

    try {
      const result = await apiRequest<SimulationStartResponse>(API_ROUTES.simulation.root(), {
        method: 'POST',
        body: JSON.stringify({
          patch_id: patchId,
          simulation_type: simulationType,
          fidelity,
        }),
      })
      setStartResult(result)
      await checkStatus(result.simulation_id)
    } catch (err) {
      setError(toErrorMessage(err))
    } finally {
      setRunning(false)
    }
  }

  async function checkStatus(simulationIdOverride?: string) {
    const simulationId = simulationIdOverride || startResult?.simulation_id
    if (!simulationId) {
      return
    }
    setError('')
    setStatusLoading(true)
    try {
      const result = await apiRequest<SimulationStatusResponse>(API_ROUTES.simulation.byId(simulationId))
      setStatusResult(result)
      if (result.status === 'running' || result.status === 'pending') {
        setPlaying(true)
      } else {
        setPlaying(false)
      }
    } catch (err) {
      setError(toErrorMessage(err))
    } finally {
      setStatusLoading(false)
    }
  }

  function stepPrevious() {
    setPlaying(false)
    setFrameIndex((prev) => (prev - 1 + DAPM_FRAMES.length) % DAPM_FRAMES.length)
  }

  function stepNext() {
    setPlaying(false)
    setFrameIndex((prev) => (prev + 1) % DAPM_FRAMES.length)
  }

  function resetPlayback() {
    setPlaying(false)
    setFrameIndex(0)
  }

  return (
    <PageContainer>
      <PageHeader
        title="Simulation Control Center"
        subtitle="Run simulation scenarios and visualize DAPM power-flow playback with confidence impact."
      />

      <Grid>
        <SectionCard title="Start Simulation">
          <form onSubmit={startSimulation} style={{ display: 'grid', gap: '0.6rem' }}>
            <input
              value={patchId}
              onChange={(e) => setPatchId(e.target.value)}
              placeholder="Patch ID (optional)"
              style={inputStyle}
            />
            <select value={simulationType} onChange={(e) => setSimulationType(e.target.value)} style={inputStyle}>
              {scenarioList.length === 0 ? (
                <option value="">loading scenarios...</option>
              ) : (
                scenarioList.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.id}
                  </option>
                ))
              )}
            </select>
            <select value={fidelity} onChange={(e) => setFidelity(e.target.value)} style={inputStyle}>
              {(selectedScenario?.fidelity_modes || ['state_machine']).map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
            <button style={buttonStyle} type="submit" disabled={running || !simulationType.trim()}>
              {running ? 'Starting...' : 'Start Simulation'}
            </button>
          </form>
          <div style={{ marginTop: '0.75rem' }}>
            {error ? <MetaText>{error}</MetaText> : null}
            {startResult ? <JsonBlock data={startResult} /> : null}
            {selectedScenario ? <MetaText>{selectedScenario.description}</MetaText> : null}
          </div>
        </SectionCard>

        <SectionCard title="Simulation Status">
          <button style={buttonStyle} onClick={() => void checkStatus()} disabled={statusLoading || !startResult?.simulation_id}>
            {statusLoading ? 'Refreshing...' : 'Refresh Status'}
          </button>
          <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.35rem' }}>
            {statusResult ? (
              <>
                <MetaText>
                  status={statusResult.status} | type={statusResult.simulation_type} | fidelity={statusResult.fidelity_mode}
                </MetaText>
                <MetaText>
                  confidence_impact={statusResult.confidence_impact} | duration_ms={statusResult.duration_ms ?? 'n/a'}
                </MetaText>
                <JsonBlock data={statusResult.findings || {}} />
              </>
            ) : (
              <MetaText>No status fetched yet.</MetaText>
            )}
          </div>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="DAPM Simulation Visualization">
          <div style={{ display: 'grid', gap: '0.7rem' }}>
            <canvas
              ref={canvasRef}
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              style={{ width: '100%', maxWidth: `${CANVAS_WIDTH}px`, borderRadius: '8px' }}
            />
            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <button type="button" style={buttonStyle} onClick={stepPrevious}>
                Prev
              </button>
              <button type="button" style={buttonStyle} onClick={() => setPlaying((prev) => !prev)}>
                {playing ? 'Pause' : 'Play'}
              </button>
              <button type="button" style={buttonStyle} onClick={stepNext}>
                Next
              </button>
              <button type="button" style={buttonStyle} onClick={resetPlayback}>
                Reset
              </button>
              <span style={{ fontSize: '0.82rem', color: '#475569' }}>Speed:</span>
              {SPEED_OPTIONS.map((value) => (
                <button
                  key={value}
                  type="button"
                  style={speedButtonStyle(value === speed)}
                  onClick={() => setSpeed(value)}
                >
                  {value}x
                </button>
              ))}
            </div>
            <MetaText>Legend: green=active widget/path, gray=inactive. Playback controls are local and deterministic.</MetaText>
          </div>
        </SectionCard>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Available Scenarios">
          <JsonBlock data={scenarios || {}} />
        </SectionCard>
      </div>
    </PageContainer>
  )
}

const inputStyle: CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.48rem 0.6rem',
}

const buttonStyle: CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.5rem 0.75rem',
  cursor: 'pointer',
}

function speedButtonStyle(active: boolean): CSSProperties {
  return {
    border: '1px solid #334155',
    borderRadius: '6px',
    background: active ? '#334155' : '#ffffff',
    color: active ? '#ffffff' : '#0f172a',
    padding: '0.34rem 0.55rem',
    cursor: 'pointer',
    fontSize: '0.78rem',
  }
}
