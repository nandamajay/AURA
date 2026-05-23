"""AURA transport abstraction layer."""

from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    RuntimeState,
    TransportConfidence,
    TransportMetadata,
    TransportResponse,
    RuntimeTransportAPI,
    classify_command,
)
from aura_sdk.transport.runtime_command_dispatcher import RuntimeCommandDispatcher
from aura_sdk.transport.runtime_protocol import (
    HEARTBEAT_STALENESS_SECONDS,
    MAX_COMMANDS_PER_BATCH,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    PROTOCOL_VERSION,
    RuntimeExecutionState,
    build_request_block,
    compute_request_integrity,
    compute_response_integrity,
    map_status_to_execution_state,
    validate_request_block,
    validate_response_block,
)
from aura_sdk.transport.remote_transport_dispatcher import build_remote_dispatcher
from aura_sdk.transport.runtime_transport_client import RuntimeTransportClient
from aura_sdk.transport.runtime_serial_executor import RuntimeSerialExecutor, SerialAgentConfig
from aura_sdk.transport.safe_read_only_discovery import (
    DiscoveryConfig,
    SAFE_READ_ONLY_COMMANDS,
    SafeReadOnlyDiscoveryRunner,
)
from aura_sdk.transport.serial_prompt_detector import (
    PromptDetectionResult,
    SerialPromptDetector,
)
from aura_sdk.transport.tcp_runtime_bridge import TcpRuntimeBridge
from aura_sdk.transport.windows_serial_agent import main as windows_serial_agent_main
from aura_sdk.transport.adapters.local_shell_transport_adapter import LocalShellTransportAdapter
from aura_sdk.transport.adapters.adb_transport_adapter import AdbTransportAdapter
from aura_sdk.transport.adapters.serial_transport_adapter import SerialTransportAdapter
from aura_sdk.transport.adapters.ssh_transport_adapter import SshTransportAdapter
from aura_sdk.transport.adapters.future_diag_transport_adapter import FutureDiagTransportAdapter
from aura_sdk.transport.adapters.remote_serial_transport_adapter import (
    RemoteSerialTransportAdapter,
)
from aura_sdk.transport.environment_classifier import (
    EnvironmentClassification,
    classify_target_environment,
)
from aura_sdk.transport.command_planner import (
    PlanResult,
    ProceduralAudioPlanResult,
    RB3SpeakerWorkflowResult,
    TargetPluginWorkflowResult,
    build_adaptive_plan,
    build_procedural_audio_plan,
    build_rb3_speaker_workflow,
    build_target_plugin_workflow,
)
from aura_sdk.transport.rb3_playback_cognition import (
    RB3PlaybackPlanResult,
    RB3ProceduralMemory,
    build_audio_route_knowledge_graph,
    build_playback_state_machine,
    build_rb3_speaker_playback_plan,
    correlate_runtime_evidence,
    explain_playback_failure,
    stage_asset_to_bridge,
)
from aura_sdk.transport.rb3_baseline_profiles import (
    BaselineRecordResult,
    RB3BaselineProfileRegistry,
    RB3ProceduralMemoryLock,
    build_runtime_regression_comparison,
)
from aura_sdk.transport.rb3_topology_cognition import (
    RB3ProceduralRouteMemory,
    TopologyCognitionResult,
    build_rb3_topology_cognition,
)
from aura_sdk.transport.cognitive_persistence import (
    AURAArtifactIndexEngine,
    AURACognitionBootLoader,
    AURACognitionPortability,
    AURACognitionRegistry,
    AURACognitionReplayEngine,
    AURAGovernanceEngine,
    AURAPhaseEngine,
    CognitionBootResult,
    copy_portable_snapshot,
)
from aura_sdk.transport.agentization import (
    AURAInternalAgentizationCoordinator,
    AgentizationResult,
)
from aura_sdk.transport.aura_cognition_bus import AURACognitionBus
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine
from aura_sdk.transport.audio_runtime_cognition import (
    MODE_DISCOVERY,
    MODE_KNOWN,
    MODE_LEARNING,
    AudioCognitionResult,
    build_audio_runtime_cognition,
)
from aura_sdk.transport.dts_audio_cognition import (
    DtsAudioCognitionResult,
    parse_dts_audio_cognition,
)
from aura_sdk.transport.target_fingerprint_engine import (
    CAP_SUPPORTED,
    CAP_UNKNOWN,
    CAP_UNSUPPORTED,
    FingerprintResult,
    TargetFingerprintEngine,
)
from aura_sdk.transport.runtime_capability_graph import build_runtime_capability_graph
from aura_sdk.transport.portable_runtime_layer import (
    PortableRuntimeLayer,
    PortableRuntimeWorkflowResult,
)
from aura_sdk.transport.plugins import (
    DegradedTargetGammaPlugin,
    FakeTargetAlphaPlugin,
    FakeTargetBetaPlugin,
    PluginIsolationValidator,
    PluginLifecycleOrchestrator,
    PluginLifecycleResult,
    PluginNegotiationRequest,
    PluginNegotiationResult,
    RB3TargetPlugin,
    TargetPluginContract,
    TargetPluginLoader,
    assert_plugin_contract,
    build_simulation_registry_payload,
    detect_plugin_drift,
    get_degraded_target_gamma_plugin,
    get_fake_target_alpha_plugin,
    get_fake_target_beta_plugin,
    get_rb3_plugin,
)
from aura_sdk.transport.semantic_cognition import (
    SemanticCognitionEngine,
    SemanticCognitionResult,
)
from aura_sdk.transport.semantic_fingerprint import (
    SemanticFingerprintResult,
    build_vendor_dependency_fingerprint,
    stable_fingerprint,
)
from aura_sdk.transport.semantic_registry import SemanticCognitionRegistry

__all__ = [
    "CommandClassification",
    "RuntimeState",
    "TransportConfidence",
    "TransportMetadata",
    "TransportResponse",
    "RuntimeTransportAPI",
    "RuntimeCommandDispatcher",
    "MAX_COMMANDS_PER_BATCH",
    "MAX_STDOUT_BYTES",
    "MAX_STDERR_BYTES",
    "HEARTBEAT_STALENESS_SECONDS",
    "PROTOCOL_VERSION",
    "RuntimeExecutionState",
    "build_request_block",
    "compute_request_integrity",
    "compute_response_integrity",
    "map_status_to_execution_state",
    "validate_request_block",
    "validate_response_block",
    "build_remote_dispatcher",
    "RuntimeTransportClient",
    "RuntimeSerialExecutor",
    "SerialAgentConfig",
    "DiscoveryConfig",
    "SAFE_READ_ONLY_COMMANDS",
    "SafeReadOnlyDiscoveryRunner",
    "PromptDetectionResult",
    "SerialPromptDetector",
    "TcpRuntimeBridge",
    "windows_serial_agent_main",
    "LocalShellTransportAdapter",
    "AdbTransportAdapter",
    "SerialTransportAdapter",
    "SshTransportAdapter",
    "FutureDiagTransportAdapter",
    "RemoteSerialTransportAdapter",
    "classify_command",
    "EnvironmentClassification",
    "classify_target_environment",
    "PlanResult",
    "ProceduralAudioPlanResult",
    "RB3SpeakerWorkflowResult",
    "TargetPluginWorkflowResult",
    "build_adaptive_plan",
    "build_procedural_audio_plan",
    "build_rb3_speaker_workflow",
    "build_target_plugin_workflow",
    "RB3PlaybackPlanResult",
    "RB3ProceduralMemory",
    "build_audio_route_knowledge_graph",
    "build_playback_state_machine",
    "build_rb3_speaker_playback_plan",
    "correlate_runtime_evidence",
    "explain_playback_failure",
    "stage_asset_to_bridge",
    "BaselineRecordResult",
    "RB3BaselineProfileRegistry",
    "RB3ProceduralMemoryLock",
    "build_runtime_regression_comparison",
    "RB3ProceduralRouteMemory",
    "TopologyCognitionResult",
    "build_rb3_topology_cognition",
    "AURAArtifactIndexEngine",
    "AURACognitionBootLoader",
    "AURACognitionPortability",
    "AURACognitionRegistry",
    "AURACognitionReplayEngine",
    "AURAGovernanceEngine",
    "AURAPhaseEngine",
    "CognitionBootResult",
    "copy_portable_snapshot",
    "AURAInternalAgentizationCoordinator",
    "AgentizationResult",
    "AURACognitionBus",
    "AURAEventReplayEngine",
    "MODE_KNOWN",
    "MODE_LEARNING",
    "MODE_DISCOVERY",
    "AudioCognitionResult",
    "build_audio_runtime_cognition",
    "DtsAudioCognitionResult",
    "parse_dts_audio_cognition",
    "CAP_SUPPORTED",
    "CAP_UNKNOWN",
    "CAP_UNSUPPORTED",
    "FingerprintResult",
    "TargetFingerprintEngine",
    "build_runtime_capability_graph",
    "PortableRuntimeLayer",
    "PortableRuntimeWorkflowResult",
    "TargetPluginContract",
    "PluginNegotiationRequest",
    "PluginNegotiationResult",
    "TargetPluginLoader",
    "RB3TargetPlugin",
    "assert_plugin_contract",
    "get_rb3_plugin",
    "PluginIsolationValidator",
    "PluginLifecycleOrchestrator",
    "PluginLifecycleResult",
    "detect_plugin_drift",
    "FakeTargetAlphaPlugin",
    "FakeTargetBetaPlugin",
    "DegradedTargetGammaPlugin",
    "get_fake_target_alpha_plugin",
    "get_fake_target_beta_plugin",
    "get_degraded_target_gamma_plugin",
    "build_simulation_registry_payload",
    "SemanticCognitionEngine",
    "SemanticCognitionResult",
    "SemanticCognitionRegistry",
    "SemanticFingerprintResult",
    "build_vendor_dependency_fingerprint",
    "stable_fingerprint",
]
