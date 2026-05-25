import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import GlobalCommandCenter from './pages/GlobalCommandCenter'
import DriverMigrationCenter from './pages/DriverMigrationCenter'
import KnowledgeGraphCenter from './pages/KnowledgeGraphCenter'
import MaintainerIntelligenceCenter from './pages/MaintainerIntelligenceCenter'
import LearningCenter from './pages/LearningCenter'
import LiveAgentObservability from './pages/LiveAgentObservability'
import ArchitectureLab from './pages/ArchitectureLab'
import PatchReviewWarRoom from './pages/PatchReviewWarRoom'
import DebuggingCenter from './pages/DebuggingCenter'
import SimulationControlCenter from './pages/SimulationControlCenter'
import ApprovalOperationsCenter from './pages/ApprovalOperationsCenter'
import GovernanceCommandCenter from './pages/GovernanceCommandCenter'
import RuntimeCognitionCenter from './pages/RuntimeCognitionCenter'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<GlobalCommandCenter />} />
        <Route path="/migration" element={<DriverMigrationCenter />} />
        <Route path="/knowledge" element={<KnowledgeGraphCenter />} />
        <Route path="/maintainers" element={<MaintainerIntelligenceCenter />} />
        <Route path="/learning" element={<LearningCenter />} />
        <Route path="/agents" element={<LiveAgentObservability />} />
        <Route path="/architecture" element={<ArchitectureLab />} />
        <Route path="/patches" element={<PatchReviewWarRoom />} />
        <Route path="/debug" element={<DebuggingCenter />} />
        <Route path="/simulation" element={<SimulationControlCenter />} />
        <Route path="/approvals" element={<ApprovalOperationsCenter />} />
        <Route path="/approval" element={<ApprovalOperationsCenter />} />
        <Route path="/governance" element={<GovernanceCommandCenter />} />
        <Route path="/runtime" element={<RuntimeCognitionCenter />} />

        {/* Backward compatibility with older nav links */}
        <Route path="/tasks" element={<DriverMigrationCenter />} />
      </Route>
    </Routes>
  )
}

export default App
