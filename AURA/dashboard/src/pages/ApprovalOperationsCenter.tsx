import { useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { DataPanel } from '../components/DataPanel'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

export default function ApprovalOperationsCenter() {
  const [governanceId, setGovernanceId] = useState('')
  const [governanceAction, setGovernanceAction] = useState('grant')
  const [governanceComment, setGovernanceComment] = useState('')

  const [charterRequestId, setCharterRequestId] = useState('')
  const [charterAction, setCharterAction] = useState<'approve' | 'reject'>('approve')

  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')

  async function processGovernanceApproval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!governanceId.trim()) {
      return
    }
    setError('')
    try {
      const response = await apiRequest(API_ROUTES.governance.approvalById(governanceId), {
        method: 'POST',
        body: JSON.stringify({ action: governanceAction, comment: governanceComment }),
      })
      setResult(response)
    } catch (err) {
      setError(toErrorMessage(err))
    }
  }

  async function processCharterApproval(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!charterRequestId.trim()) {
      return
    }
    setError('')
    try {
      const response = await apiRequest(
        API_ROUTES.charter.approvalAction(charterRequestId, charterAction),
        { method: 'POST' },
      )
      setResult(response)
    } catch (err) {
      setError(toErrorMessage(err))
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Approval Operations Center"
        subtitle="Process governance approvals and charter-gated high-risk requests."
      />

      <div data-testid="approval-matrix">
        <Grid>
          <SectionCard title="Governance Approval Action">
            <form onSubmit={processGovernanceApproval} style={{ display: 'grid', gap: '0.5rem' }}>
              <input
                style={inputStyle}
                value={governanceId}
                onChange={(e) => setGovernanceId(e.target.value)}
                placeholder="Governance approval ID"
              />
              <select style={inputStyle} value={governanceAction} onChange={(e) => setGovernanceAction(e.target.value)}>
                <option value="grant">grant</option>
                <option value="reject">reject</option>
                <option value="escalate">escalate</option>
                <option value="comment">comment</option>
              </select>
              <input
                style={inputStyle}
                value={governanceComment}
                onChange={(e) => setGovernanceComment(e.target.value)}
                placeholder="Optional comment"
              />
              <button style={buttonStyle} type="submit">
                Process Governance Action
              </button>
            </form>
          </SectionCard>

          <SectionCard title="Charter Approval Action">
            <form onSubmit={processCharterApproval} style={{ display: 'grid', gap: '0.5rem' }}>
              <input
                style={inputStyle}
                value={charterRequestId}
                onChange={(e) => setCharterRequestId(e.target.value)}
                placeholder="Charter request ID"
              />
              <select
                style={inputStyle}
                value={charterAction}
                onChange={(e) => setCharterAction(e.target.value as 'approve' | 'reject')}
              >
                <option value="approve">approve</option>
                <option value="reject">reject</option>
              </select>
              <button style={buttonStyle} type="submit">
                Process Charter Action
              </button>
            </form>
          </SectionCard>
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <DataPanel
            title="Governance Evidence Summary"
            endpoint={API_ROUTES.governance.evidenceSummary()}
            intervalMs={15_000}
          />
          <DataPanel title="Governance Approvals" endpoint={API_ROUTES.governance.approvalsList('pending', 50)} intervalMs={15_000} />
          <DataPanel title="Charter Pending Approvals" endpoint={API_ROUTES.charter.pendingApprovals()} intervalMs={15_000} />
        </Grid>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <SectionCard title="Action Result">
          {error ? <MetaText>{error}</MetaText> : null}
          {result ? <JsonBlock data={result} /> : <MetaText>No action executed yet.</MetaText>}
        </SectionCard>
      </div>
    </PageContainer>
  )
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.45rem 0.6rem',
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #0f172a',
  borderRadius: '6px',
  background: '#0f172a',
  color: '#fff',
  padding: '0.5rem 0.75rem',
  cursor: 'pointer',
}
