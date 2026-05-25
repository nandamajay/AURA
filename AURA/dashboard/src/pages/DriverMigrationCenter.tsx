import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

interface AgentCatalog {
  agent_types: string[]
}

interface TaskItem {
  id: string
  status: string
  agent_type: string
  description?: string
  created_at?: string
}

interface TaskListResponse {
  tasks: TaskItem[]
  total: number
  page: number
  limit: number
}

type WorkflowStepState = 'pending' | 'running' | 'completed' | 'failed' | 'manual'

export default function DriverMigrationCenter() {
  const navigate = useNavigate()
  const [agentType, setAgentType] = useState('learning')
  const [priority, setPriority] = useState('P1')
  const [description, setDescription] = useState('')
  const [downstreamPath, setDownstreamPath] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitResult, setSubmitResult] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)
  const [workflowTaskId, setWorkflowTaskId] = useState('')

  const {
    data: queueStats,
    error: queueError,
    reload: reloadQueue,
  } = useApiData(API_ROUTES.tasks.queueStats(), {
    intervalMs: 10_000,
  })
  const {
    data: tasks,
    error: tasksError,
    reload: reloadTasks,
  } = useApiData<TaskListResponse>(API_ROUTES.tasks.list(), {
    intervalMs: 10_000,
  })
  const { data: agents } = useApiData<AgentCatalog>(API_ROUTES.agents.root(), {
    intervalMs: 20_000,
  })

  const agentOptions = useMemo(() => {
    return agents?.agent_types?.length ? agents.agent_types : ['learning', 'validation', 'refactor']
  }, [agents])

  useEffect(() => {
    const storedTaskId = window.sessionStorage.getItem('aura.workflow.task_id')
    if (storedTaskId) {
      setWorkflowTaskId(storedTaskId)
    }
  }, [])

  useEffect(() => {
    if (workflowTaskId) {
      window.sessionStorage.setItem('aura.workflow.task_id', workflowTaskId)
    }
  }, [workflowTaskId])

  const selectedTask = useMemo(() => {
    const allTasks = tasks?.tasks || []
    if (!allTasks.length) {
      return null
    }
    if (workflowTaskId) {
      const match = allTasks.find((task) => task.id === workflowTaskId)
      if (match) {
        return match
      }
    }
    return allTasks[0]
  }, [tasks, workflowTaskId])

  useEffect(() => {
    if (selectedTask?.id && selectedTask.id !== workflowTaskId) {
      setWorkflowTaskId(selectedTask.id)
    }
  }, [selectedTask, workflowTaskId])

  const workflowSteps = useMemo(() => {
    const taskStatus = (selectedTask?.status || '').toLowerCase()
    const hasTask = Boolean(selectedTask?.id)
    const schedulerDone = hasTask && taskStatus !== 'created'
    const executionRunning = taskStatus === 'running' || taskStatus === 'started'
    const executionCompleted = taskStatus === 'completed'
    const executionFailed = taskStatus === 'failed'

    return [
      {
        title: '1. Submit Driver',
        detail: hasTask ? `Task created (${selectedTask?.id.slice(0, 8)})` : 'Create a migration task with downstream path',
        state: hasTask ? 'completed' : 'pending',
      },
      {
        title: '2. Orchestrator Schedules',
        detail: schedulerDone ? `Task status: ${selectedTask?.status}` : 'Waiting in create queue',
        state: schedulerDone ? 'completed' : 'pending',
      },
      {
        title: '3. Agents Execute',
        detail: executionCompleted
          ? 'Agent pipeline completed'
          : executionRunning
            ? 'Learning/dependency/refactor/validation in progress'
            : executionFailed
              ? 'Execution failed - inspect Debugging Center'
              : 'Awaiting execution',
        state: executionFailed ? 'failed' : executionCompleted ? 'completed' : executionRunning ? 'running' : 'pending',
        actionLabel: 'Open Live Agent Observability',
        actionPath: '/agents',
      },
      {
        title: '4. Simulation (Optional)',
        detail: 'Run simulation checks for probe flow and confidence impact',
        state: 'manual',
        actionLabel: 'Open Simulation Control Center',
        actionPath: '/simulation',
      },
      {
        title: '5. Review Patch',
        detail: 'Inspect diff, maintainer feedback, and evidence links',
        state: 'manual',
        actionLabel: 'Open Patch Review War Room',
        actionPath: '/patches',
      },
      {
        title: '6. Approve For Upstream',
        detail: 'Process final approval grant/reject in approval operations',
        state: 'manual',
        actionLabel: 'Open Approval Operations Center',
        actionPath: '/approvals',
      },
    ] as Array<{
      title: string
      detail: string
      state: WorkflowStepState
      actionLabel?: string
      actionPath?: string
    }>
  }, [selectedTask])

  async function createTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setSubmitError('')
    setSubmitResult(null)

    try {
      const payload = {
        agent_type: agentType,
        priority,
        description,
        input_data: {
          requested_from: 'driver-migration-center',
          downstream_driver_path: downstreamPath.trim(),
        },
      }
      const result = await apiRequest(API_ROUTES.tasks.root(), {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setSubmitResult(result)
      setDescription('')
      if (typeof result === 'object' && result !== null && 'task_id' in result) {
        const taskId = String((result as { task_id: string }).task_id)
        setWorkflowTaskId(taskId)
      }
      await Promise.all([reloadQueue(), reloadTasks()])
    } catch (error) {
      setSubmitError(toErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Driver Migration Center"
        subtitle="Create migration tasks and execute the submit -> migrate -> review -> approve workflow."
      />

      <Grid>
        <SectionCard title="Queue Snapshot">
          {queueError ? <MetaText>{queueError}</MetaText> : <JsonBlock data={queueStats || {}} />}
        </SectionCard>

        <SectionCard title="Engineering Workflow Tracker">
          <div style={{ display: 'grid', gap: '0.55rem' }}>
            {workflowSteps.map((step) => (
              <div key={step.title} style={{ ...stepRowStyle, borderColor: stateColor(step.state) }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{step.title}</div>
                  <MetaText>{step.detail}</MetaText>
                </div>
                <div style={{ display: 'grid', gap: '0.35rem', justifyItems: 'end' }}>
                  <span style={{ ...stateBadgeStyle, background: stateColor(step.state) }}>{step.state}</span>
                  {step.actionPath && step.actionLabel ? (
                    <button
                      type="button"
                      style={secondaryButtonStyle}
                      onClick={() => navigate(step.actionPath as string)}
                    >
                      {step.actionLabel}
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
            <MetaText>Workflow context task: {selectedTask?.id || 'none selected'}</MetaText>
          </div>
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Create Migration Task">
            <form onSubmit={createTask} style={{ display: 'grid', gap: '0.6rem' }}>
              <label style={labelStyle}>
                Agent Type
                <select value={agentType} onChange={(e) => setAgentType(e.target.value)} style={inputStyle}>
                  {agentOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <label style={labelStyle}>
                Priority
                <select value={priority} onChange={(e) => setPriority(e.target.value)} style={inputStyle}>
                  <option value="P0">P0 Critical</option>
                  <option value="P1">P1 Normal</option>
                  <option value="P2">P2 Background</option>
                </select>
              </label>
              <label style={labelStyle}>
                Downstream Driver Path
                <input
                  value={downstreamPath}
                  onChange={(e) => setDownstreamPath(e.target.value)}
                  style={inputStyle}
                  placeholder="/vendor/qcom/audio/<driver>.c"
                />
              </label>
              <label style={labelStyle}>
                Description
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  style={{ ...inputStyle, resize: 'vertical' }}
                  placeholder="Describe the migration intent and constraints"
                />
              </label>
              <button
                data-testid="submit-driver"
                type="submit"
                style={buttonStyle}
                disabled={submitting || !description.trim()}
              >
                {submitting ? 'Submitting...' : 'Create Task'}
              </button>
              {submitError ? <MetaText>{submitError}</MetaText> : null}
              {submitResult ? <JsonBlock data={submitResult} /> : null}
            </form>
          </SectionCard>

          <SectionCard title="Current Workflow Task Detail">
            {selectedTask ? <JsonBlock data={selectedTask} /> : <MetaText>No task selected yet.</MetaText>}
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Task List (Current API Response)">
          {tasksError ? <MetaText>{tasksError}</MetaText> : <JsonBlock data={tasks || {}} />}
        </SectionCard>
      </div>
    </PageContainer>
  )
}

function stateColor(state: WorkflowStepState): string {
  if (state === 'completed') return '#16a34a'
  if (state === 'running') return '#2563eb'
  if (state === 'failed') return '#dc2626'
  if (state === 'manual') return '#7c3aed'
  return '#64748b'
}

const stepRowStyle: React.CSSProperties = {
  border: '1px solid',
  borderRadius: '8px',
  padding: '0.6rem 0.7rem',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '0.8rem',
  background: '#ffffff',
}

const stateBadgeStyle: React.CSSProperties = {
  color: '#ffffff',
  borderRadius: '999px',
  fontSize: '0.72rem',
  padding: '0.14rem 0.5rem',
  textTransform: 'uppercase',
  letterSpacing: '0.02em',
}

const secondaryButtonStyle: React.CSSProperties = {
  border: '1px solid #334155',
  borderRadius: '6px',
  background: '#334155',
  color: '#fff',
  padding: '0.32rem 0.6rem',
  cursor: 'pointer',
  fontSize: '0.78rem',
}

const labelStyle: React.CSSProperties = {
  display: 'grid',
  gap: '0.3rem',
  fontSize: '0.85rem',
  color: '#334155',
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.5rem',
  fontSize: '0.9rem',
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.55rem 0.8rem',
  cursor: 'pointer',
}
