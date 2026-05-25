import { useState } from 'react'
import { apiRequest, toErrorMessage } from '../api/client'
import { API_ROUTES } from '../config'
import { useApiData } from '../hooks/useApiData'
import { Grid, JsonBlock, MetaText, PageContainer, PageHeader, SectionCard } from '../components/PagePrimitives'

export default function PatchReviewWarRoom() {
  const [patchId, setPatchId] = useState('')
  const [detail, setDetail] = useState<unknown>(null)
  const [diff, setDiff] = useState<unknown>(null)
  const [evidence, setEvidence] = useState<unknown>(null)
  const [actionResult, setActionResult] = useState<unknown>(null)
  const [error, setError] = useState('')

  const { data: patches, error: patchesError } = useApiData(API_ROUTES.patches.list(20), {
    intervalMs: 30_000,
  })

  async function loadPatch() {
    if (!patchId.trim()) {
      return
    }
    setError('')
    setActionResult(null)
    try {
      const [detailRes, diffRes, evidenceRes] = await Promise.all([
        apiRequest(API_ROUTES.patches.byId(patchId)),
        apiRequest(API_ROUTES.patches.diff(patchId)),
        apiRequest(API_ROUTES.patches.evidence(patchId)),
      ])
      setDetail(detailRes)
      setDiff(diffRes)
      setEvidence(evidenceRes)
    } catch (err) {
      setError(toErrorMessage(err))
    }
  }

  async function submitForApproval() {
    if (!patchId.trim()) {
      return
    }
    setError('')
    try {
      const result = await apiRequest(API_ROUTES.patches.submitApproval(patchId), {
        method: 'POST',
      })
      setActionResult(result)
    } catch (err) {
      setError(toErrorMessage(err))
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Patch Review War Room"
        subtitle="Inspect patch evidence and submit selected patches for approval."
      />

      <Grid>
        <SectionCard title="Patch Query">
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <input
              value={patchId}
              onChange={(e) => setPatchId(e.target.value)}
              placeholder="Patch ID"
              style={inputStyle}
            />
            <button style={buttonStyle} onClick={() => void loadPatch()}>
              Load
            </button>
            <button style={buttonStyle} onClick={() => void submitForApproval()}>
              Submit Approval
            </button>
          </div>
          <div style={{ marginTop: '0.75rem' }}>
            {error ? <MetaText>{error}</MetaText> : null}
            {actionResult ? <JsonBlock data={actionResult} /> : null}
          </div>
        </SectionCard>

        <SectionCard title="Patch List">
          {patchesError ? <MetaText>{patchesError}</MetaText> : <JsonBlock data={patches || {}} />}
        </SectionCard>
      </Grid>

      <div style={{ marginTop: '1rem' }}>
        <Grid>
          <SectionCard title="Patch Detail">
            <JsonBlock data={detail || {}} />
          </SectionCard>
          <SectionCard title="Patch Diff">
            <JsonBlock data={diff || {}} />
          </SectionCard>
          <SectionCard title="Evidence">
            <JsonBlock data={evidence || {}} />
          </SectionCard>
        </Grid>
      </div>
    </PageContainer>
  )
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '0.45rem 0.6rem',
  minWidth: '240px',
}

const buttonStyle: React.CSSProperties = {
  border: '1px solid #334155',
  borderRadius: '6px',
  background: '#334155',
  color: '#fff',
  padding: '0.45rem 0.75rem',
  cursor: 'pointer',
}
