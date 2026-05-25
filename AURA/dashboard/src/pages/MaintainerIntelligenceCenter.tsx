import EndpointGridPage from '../components/EndpointGridPage'
import { API_ROUTES } from '../config'

export default function MaintainerIntelligenceCenter() {
  return (
    <EndpointGridPage
      title="Maintainer Intelligence Center"
      subtitle="Review decision context, known risks, and governance boundaries before submissions."
      panels={[
        { title: 'Maintainer Intelligence', endpoint: API_ROUTES.memory.maintainerIntelligence(200), intervalMs: 30_000 },
        { title: 'Known Risks', endpoint: API_ROUTES.memory.risks(20), intervalMs: 30_000 },
        { title: 'Technical Debt', endpoint: API_ROUTES.memory.debt(20), intervalMs: 30_000 },
        { title: 'Governance High-Risk Actions', endpoint: API_ROUTES.charter.highRiskActions() },
        { title: 'Architecture Drift', endpoint: API_ROUTES.memory.drift(20) },
      ]}
    />
  )
}
