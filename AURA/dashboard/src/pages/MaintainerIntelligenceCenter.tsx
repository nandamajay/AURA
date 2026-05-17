import EndpointGridPage from '../components/EndpointGridPage'
import { ENDPOINTS } from '../config'

export default function MaintainerIntelligenceCenter() {
  return (
    <EndpointGridPage
      title="Maintainer Intelligence Center"
      subtitle="Review decision context, known risks, and governance boundaries before submissions."
      panels={[
        { title: 'Known Risks', endpoint: `${ENDPOINTS.memory}/risks?limit=20`, intervalMs: 30_000 },
        { title: 'Technical Debt', endpoint: `${ENDPOINTS.memory}/debt?limit=20`, intervalMs: 30_000 },
        { title: 'Governance High-Risk Actions', endpoint: `${ENDPOINTS.charter}/high-risk-actions` },
        { title: 'Architecture Drift', endpoint: `${ENDPOINTS.memory}/drift?limit=20` },
      ]}
    />
  )
}
