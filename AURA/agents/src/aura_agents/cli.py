"""CLI entry point for agents."""

import sys

from aura_agents.base import BaseAgent
from aura_agents.dashboard import DashboardAgent
from aura_agents.dependency import DependencyAgent
from aura_agents.dts_bindings import DTSBindingsAgent
from aura_agents.knowledge_base import KnowledgeBaseAgent
from aura_agents.learning import LearningAgent
from aura_agents.maintainer_intel import MaintainerIntelAgent
from aura_agents.patch_builder import PatchBuilderAgent
from aura_agents.refactor import RefactorAgent
from aura_agents.regression import RegressionAgent
from aura_agents.review_coordinator import ReviewCoordinatorAgent
from aura_agents.simulation import SimulationAgent
from aura_agents.test_runner import TestRunnerAgent
from aura_agents.upstream_philosophy import UpstreamPhilosophyAgent
from aura_agents.validation import ValidationAgent

# Registry of implemented agent types.
# Keep explicit to avoid silently exposing incomplete agents.
AGENT_TYPES: dict[str, type[BaseAgent]] = {
    DashboardAgent.AGENT_TYPE: DashboardAgent,
    DependencyAgent.AGENT_TYPE: DependencyAgent,
    DTSBindingsAgent.AGENT_TYPE: DTSBindingsAgent,
    KnowledgeBaseAgent.AGENT_TYPE: KnowledgeBaseAgent,
    LearningAgent.AGENT_TYPE: LearningAgent,
    MaintainerIntelAgent.AGENT_TYPE: MaintainerIntelAgent,
    PatchBuilderAgent.AGENT_TYPE: PatchBuilderAgent,
    RefactorAgent.AGENT_TYPE: RefactorAgent,
    RegressionAgent.AGENT_TYPE: RegressionAgent,
    ReviewCoordinatorAgent.AGENT_TYPE: ReviewCoordinatorAgent,
    SimulationAgent.AGENT_TYPE: SimulationAgent,
    TestRunnerAgent.AGENT_TYPE: TestRunnerAgent,
    UpstreamPhilosophyAgent.AGENT_TYPE: UpstreamPhilosophyAgent,
    ValidationAgent.AGENT_TYPE: ValidationAgent,
}


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: aura-agents <agent-type> [options]")
        print(f"Available agents: {', '.join(AGENT_TYPES.keys()) or 'none registered'}")
        sys.exit(1)

    agent_type = sys.argv[1]

    if agent_type == "--list":
        print("Available agents:")
        for name, cls in AGENT_TYPES.items():
            print(f"  {name}: {cls.__doc__ or 'No description'}")
        sys.exit(0)

    agent_class = AGENT_TYPES.get(agent_type)
    if agent_class is None:
        print(f"Unknown agent type: {agent_type}")
        print(f"Available: {', '.join(AGENT_TYPES.keys()) or 'none'}")
        sys.exit(1)

    # Remove agent type from args and pass rest to agent
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    agent_class.main()


if __name__ == "__main__":
    main()
