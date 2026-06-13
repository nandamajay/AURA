import EndpointGridPage from '../components/EndpointGridPage'
import { API_ROUTES } from '../config'

export default function LearningCenter() {
  return (
    <EndpointGridPage
      title="Learning Center"
      subtitle="Track lessons learned from decisions, failures, and replay incidents."
      panels={[
        { title: 'Memory Summary', endpoint: API_ROUTES.memory.summary(), intervalMs: 30_000 },
        { title: 'Learning Timeline', endpoint: API_ROUTES.memory.learningTimeline(200), intervalMs: 30_000 },
        { title: 'Decisions', endpoint: API_ROUTES.memory.decisions(20), intervalMs: 30_000 },
        { title: 'Failures', endpoint: API_ROUTES.memory.failures(20), intervalMs: 30_000 },
        { title: 'Replay Incidents', endpoint: API_ROUTES.memory.replayIncidents(20), intervalMs: 30_000 },
        { title: 'Track-B Learning Index', endpoint: API_ROUTES.trackB.learningIndexQuery(100, 1), intervalMs: 30_000 },
        { title: 'Track-B Learning Patterns', endpoint: API_ROUTES.trackB.learningPatterns(), intervalMs: 30_000 },
        { title: 'Track-B Readiness Examples', endpoint: API_ROUTES.trackB.dashboardReadiness(), intervalMs: 30_000 },
      ]}
    />
  )
}
