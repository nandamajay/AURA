import EndpointGridPage from '../components/EndpointGridPage'
import { ENDPOINTS } from '../config'

export default function LearningCenter() {
  return (
    <EndpointGridPage
      title="Learning Center"
      subtitle="Track lessons learned from decisions, failures, and replay incidents."
      panels={[
        { title: 'Memory Summary', endpoint: `${ENDPOINTS.memory}/summary`, intervalMs: 30_000 },
        { title: 'Decisions', endpoint: `${ENDPOINTS.memory}/decisions?limit=20`, intervalMs: 30_000 },
        { title: 'Failures', endpoint: `${ENDPOINTS.memory}/failures?limit=20`, intervalMs: 30_000 },
        { title: 'Replay Incidents', endpoint: `${ENDPOINTS.memory}/replay-incidents?limit=20`, intervalMs: 30_000 },
      ]}
    />
  )
}
