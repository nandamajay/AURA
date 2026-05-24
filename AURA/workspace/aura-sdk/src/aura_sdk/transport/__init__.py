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
from aura_sdk.transport.semantic_html_parser import (
    SemanticHtmlParseResult,
    parse_semantic_html,
)
from aura_sdk.transport.semantic_entity_extractor import (
    SemanticEntityExtractionResult,
    extract_semantic_entities,
)
from aura_sdk.transport.semantic_relationship_graph import (
    SemanticRelationshipGraphResult,
    build_semantic_relationship_map,
)
from aura_sdk.transport.semantic_ontology_builder import (
    SemanticOntologyResult,
    build_semantic_ontology,
)
from aura_sdk.transport.semantic_governance_boundary import (
    SemanticGovernanceBoundaryResult,
    evaluate_semantic_governance_boundary,
)
from aura_sdk.transport.semantic_equivalence_mapper import (
    SemanticEquivalenceMapResult,
    build_semantic_equivalence_map,
)
from aura_sdk.transport.semantic_portability_reasoning import (
    SemanticPortabilityReasoningResult,
    build_semantic_portability_rules,
)
from aura_sdk.transport.semantic_runtime_advisory import (
    SemanticRuntimeAdvisoryEngine,
    SemanticRuntimeAdvisoryResult,
)
from aura_sdk.transport.semantic_replay_compatibility import (
    SemanticReplayCompatibilityResult,
    build_semantic_replay_compatibility,
)
from aura_sdk.transport.semantic_confidence_engine import (
    SemanticConfidenceResult,
    build_semantic_confidence_report,
)
from aura_sdk.transport.semantic_traceability_engine import (
    KernelSemanticKnowledgeRegistry,
    SemanticTraceabilityResult,
    build_semantic_traceability_graph,
)
from aura_sdk.transport.evidence_correlation import (
    EvidenceCorrelationResult,
    correlate_evidence,
)
from aura_sdk.transport.causal_lineage import (
    CausalLineageResult,
    build_causal_lineage,
)
from aura_sdk.transport.confidence_evolution import (
    ConfidenceEvolutionResult,
    evolve_confidence,
)
from aura_sdk.transport.cognition_correlation import (
    CognitionCorrelationRegistry,
    CognitionCorrelationResult,
    UnifiedCognitionCorrelationEngine,
)
from aura_sdk.transport.downstream_upstream_mapping import (
    DownstreamUpstreamMappingResult,
    build_downstream_upstream_mapping,
)
from aura_sdk.transport.topology_translation_cognition import (
    TopologyTranslationResult,
    build_topology_translation_report,
)
from aura_sdk.transport.runtime_conversion_reasoning import (
    RuntimeConversionReasoningResult,
    analyze_runtime_conversion,
)
from aura_sdk.transport.migration_lineage import (
    MigrationLineageResult,
    build_migration_lineage,
)
from aura_sdk.transport.upstream_conversion_planner import (
    TranslationIntelligenceRegistry,
    UpstreamConversionPlanner,
    UpstreamConversionPlannerResult,
)
from aura_sdk.transport.downstream_driver_ingestion import (
    DownstreamDriverIngestionResult,
    ingest_downstream_driver_tree,
)
from aura_sdk.transport.upstream_semantic_matcher import (
    UpstreamSemanticMatcherResult,
    match_upstream_semantics,
)
from aura_sdk.transport.portability_blocker_classifier import (
    PortabilityBlockerResult,
    classify_portability_blockers,
)
from aura_sdk.transport.topology_reconstruction_cognition import (
    TopologyReconstructionResult,
    reconstruct_topology_runtime_graph,
)
from aura_sdk.transport.real_downstream_conversion_planner import (
    RealDownstreamConversionPlanner,
    RealDownstreamConversionPlannerResult,
    RealDownstreamConversionRegistry,
)
from aura_sdk.transport.topology_runtime_correlator import (
    RuntimeTopologyCorrelationResult,
    correlate_topology_runtime,
)
from aura_sdk.transport.lifecycle_causality_mapper import (
    LifecycleCausalityMapResult,
    build_lifecycle_causality_map,
)
from aura_sdk.transport.migration_runtime_alignment import (
    MigrationRuntimeAlignmentResult,
    build_migration_runtime_alignment,
)
from aura_sdk.transport.patch_runtime_lineage import (
    PatchRuntimeLineageResult,
    build_patch_runtime_lineage,
)
from aura_sdk.transport.dsp_runtime_causality import (
    DspRuntimeCausalityResult,
    build_dsp_runtime_causality,
)
from aura_sdk.transport.cross_domain_reasoning_engine import (
    CrossDomainReasoningResult,
    build_cross_domain_reasoning,
)
from aura_sdk.transport.regression_rootcause_reasoner import (
    RegressionRootcauseResult,
    reason_regression_rootcause,
)
from aura_sdk.transport.unified_engineering_truth_graph import (
    UnifiedEngineeringTruthGraphResult,
    build_unified_engineering_truth_graph,
)
from aura_sdk.transport.deterministic_fusion_replay import (
    DeterministicFusionReplayResult,
    build_deterministic_fusion_replay,
)
from aura_sdk.transport.runtime_evidence_fusion_engine import (
    RuntimeEvidenceFusionEngine,
    RuntimeEvidenceFusionRegistry,
    RuntimeEvidenceFusionResult,
)
from aura_sdk.transport.runtime_sequence_drift_engine import (
    RuntimeSequenceDriftResult,
    reconstruct_runtime_sequence_drift,
)
from aura_sdk.transport.lifecycle_violation_detector import (
    LifecycleViolationReportResult,
    detect_lifecycle_violations,
)
from aura_sdk.transport.topology_runtime_failure_mapper import (
    TopologyRuntimeCausalityResult,
    map_topology_runtime_failures,
)
from aura_sdk.transport.patch_runtime_causality_engine import (
    RegressionCausalityReportResult,
    build_patch_runtime_causality,
)
from aura_sdk.transport.root_cause_reasoner import (
    RootCauseCandidatesResult,
    build_root_cause_candidates,
)
from aura_sdk.transport.evidence_confidence_engine import (
    EngineeringConfidenceReportResult,
    build_engineering_confidence_report,
)
from aura_sdk.transport.runtime_incident_reconstructor import (
    RuntimeIncidentReconstructionRegistry,
    RuntimeIncidentReconstructionResult,
    RuntimeIncidentReconstructor,
)
from aura_sdk.transport.causality_query_planner import (
    CausalityQueryPlanResult,
    plan_causality_query,
)
from aura_sdk.transport.runtime_question_resolver import (
    RuntimeQuestionResolutionResult,
    resolve_runtime_question,
)
from aura_sdk.transport.migration_question_resolver import (
    MigrationQuestionResolutionResult,
    resolve_migration_question,
)
from aura_sdk.transport.topology_question_resolver import (
    TopologyQuestionResolutionResult,
    resolve_topology_question,
)
from aura_sdk.transport.patch_reasoning_resolver import (
    PatchReasoningResolutionResult,
    resolve_patch_reasoning_question,
)
from aura_sdk.transport.replay_evidence_resolver import (
    ReplayEvidenceResolutionResult,
    resolve_replay_evidence_question,
)
from aura_sdk.transport.investigation_reasoner import (
    InvestigationReasoningResult,
    synthesize_investigation_reasoning,
)
from aura_sdk.transport.engineering_query_history import (
    EngineeringQueryHistoryResult,
    update_engineering_query_history,
)
from aura_sdk.transport.reasoning_lineage_tracker import (
    ReasoningLineageResult,
    build_reasoning_lineage,
)
from aura_sdk.transport.investigation_session_registry import InvestigationSessionRegistry
from aura_sdk.transport.engineering_query_engine import (
    EngineeringQueryEngine,
    EngineeringQueryEngineResult,
)
from aura_sdk.transport.governed_translation_intelligence import (
    GovernedTranslationIntelligenceEngine,
    GovernedTranslationIntelligenceRegistry,
    GovernedTranslationIntelligenceResult,
)
from aura_sdk.transport.governed_translation_execution import (
    GovernedTranslationExecutionEngine,
    GovernedTranslationExecutionRegistry,
    GovernedTranslationExecutionResult,
)
from aura_sdk.transport.governed_adaptive_remediation import (
    GovernedAdaptiveRemediationEngine,
    GovernedAdaptiveRemediationRegistry,
    GovernedAdaptiveRemediationResult,
)
from aura_sdk.transport.dmesg_ingestor import DmesgIngestionResult, ingest_dmesg
from aura_sdk.transport.ftrace_ingestor import FtraceIngestionResult, ingest_ftrace
from aura_sdk.transport.tracecmd_ingestor import TracecmdIngestionResult, ingest_tracecmd
from aura_sdk.transport.tinymix_state_ingestor import (
    TinymixStateIngestionResult,
    ingest_tinymix_state,
)
from aura_sdk.transport.procfs_runtime_ingestor import (
    ProcfsRuntimeIngestionResult,
    ingest_procfs_runtime,
)
from aura_sdk.transport.debugfs_runtime_ingestor import (
    DebugfsRuntimeIngestionResult,
    ingest_debugfs_runtime,
)
from aura_sdk.transport.soundwire_runtime_ingestor import (
    SoundwireRuntimeIngestionResult,
    ingest_soundwire_runtime,
)
from aura_sdk.transport.dsp_mailbox_ingestor import (
    DspMailboxIngestionResult,
    ingest_dsp_mailbox,
)
from aura_sdk.transport.irq_runtime_ingestor import (
    IrqRuntimeIngestionResult,
    ingest_irq_runtime,
)
from aura_sdk.transport.runtime_capture_fingerprint import (
    RuntimeCaptureFingerprintResult,
    build_runtime_capture_fingerprint,
)
from aura_sdk.transport.engineering_session_replay import (
    EngineeringSessionReplayResult,
    build_engineering_session_replay,
)
from aura_sdk.transport.runtime_session_registry import RuntimeSessionRegistry
from aura_sdk.transport.runtime_evidence_ingestor import (
    RuntimeEvidenceIngestionResult,
    RuntimeEvidenceIngestor,
)
from aura_sdk.transport.runtime_evidence_acquisition import (
    RuntimeEvidenceAcquisitionEngine,
    RuntimeEvidenceAcquisitionRegistry,
    RuntimeEvidenceAcquisitionResult,
)
from aura_sdk.transport.upstream_acceptance_simulation import (
    UpstreamAcceptanceSimulationEngine,
    UpstreamAcceptanceSimulationRegistry,
    UpstreamAcceptanceSimulationResult,
)
from aura_sdk.transport.controlled_pilot_conversion import (
    ControlledPilotConversionEngine,
    ControlledPilotConversionRegistry,
    ControlledPilotConversionResult,
)
from aura_sdk.transport.real_micro_conversion_pilot import (
    RealMicroConversionPilotEngine,
    RealMicroConversionPilotRegistry,
    RealMicroConversionPilotResult,
    build_real_micro_source_input_model,
)
from aura_sdk.transport.governed_patchset_orchestration import (
    GovernedPatchsetOrchestrationEngine,
    GovernedPatchsetOrchestrationRegistry,
    GovernedPatchsetOrchestrationResult,
)
from aura_sdk.transport.real_source_tree_governed_conversion import (
    RealSourceTreeGovernedConversionEngine,
    RealSourceTreeGovernedConversionRegistry,
    RealSourceTreeGovernedConversionResult,
)
from aura_sdk.transport.real_patch_application_governed_build import (
    RealPatchApplicationGovernedBuildEngine,
    RealPatchApplicationGovernedBuildRegistry,
    RealPatchApplicationGovernedBuildResult,
)
from aura_sdk.transport.compile_cognition_engine import (
    CompileCognitionEngine,
    CompileCognitionRegistry,
    CompileCognitionResult,
)
from aura_sdk.transport.build_execution_engine import (
    BuildExecutionEngine,
    BuildExecutionRegistry,
    BuildExecutionResult,
)
from aura_sdk.transport.sandbox_patch_validation_engine import (
    SandboxPatchValidationEngine,
    SandboxPatchValidationRegistry,
    SandboxPatchValidationResult,
)

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
    "SemanticHtmlParseResult",
    "parse_semantic_html",
    "SemanticEntityExtractionResult",
    "extract_semantic_entities",
    "SemanticRelationshipGraphResult",
    "build_semantic_relationship_map",
    "SemanticOntologyResult",
    "build_semantic_ontology",
    "SemanticGovernanceBoundaryResult",
    "evaluate_semantic_governance_boundary",
    "SemanticEquivalenceMapResult",
    "build_semantic_equivalence_map",
    "SemanticPortabilityReasoningResult",
    "build_semantic_portability_rules",
    "SemanticRuntimeAdvisoryEngine",
    "SemanticRuntimeAdvisoryResult",
    "SemanticReplayCompatibilityResult",
    "build_semantic_replay_compatibility",
    "SemanticConfidenceResult",
    "build_semantic_confidence_report",
    "SemanticTraceabilityResult",
    "build_semantic_traceability_graph",
    "KernelSemanticKnowledgeRegistry",
    "SemanticFingerprintResult",
    "build_vendor_dependency_fingerprint",
    "stable_fingerprint",
    "EvidenceCorrelationResult",
    "correlate_evidence",
    "CausalLineageResult",
    "build_causal_lineage",
    "ConfidenceEvolutionResult",
    "evolve_confidence",
    "CognitionCorrelationResult",
    "UnifiedCognitionCorrelationEngine",
    "CognitionCorrelationRegistry",
    "DownstreamUpstreamMappingResult",
    "build_downstream_upstream_mapping",
    "TopologyTranslationResult",
    "build_topology_translation_report",
    "RuntimeConversionReasoningResult",
    "analyze_runtime_conversion",
    "MigrationLineageResult",
    "build_migration_lineage",
    "UpstreamConversionPlannerResult",
    "UpstreamConversionPlanner",
    "TranslationIntelligenceRegistry",
    "DownstreamDriverIngestionResult",
    "ingest_downstream_driver_tree",
    "UpstreamSemanticMatcherResult",
    "match_upstream_semantics",
    "PortabilityBlockerResult",
    "classify_portability_blockers",
    "TopologyReconstructionResult",
    "reconstruct_topology_runtime_graph",
    "RealDownstreamConversionPlannerResult",
    "RealDownstreamConversionPlanner",
    "RealDownstreamConversionRegistry",
    "RuntimeTopologyCorrelationResult",
    "correlate_topology_runtime",
    "LifecycleCausalityMapResult",
    "build_lifecycle_causality_map",
    "MigrationRuntimeAlignmentResult",
    "build_migration_runtime_alignment",
    "PatchRuntimeLineageResult",
    "build_patch_runtime_lineage",
    "DspRuntimeCausalityResult",
    "build_dsp_runtime_causality",
    "CrossDomainReasoningResult",
    "build_cross_domain_reasoning",
    "RegressionRootcauseResult",
    "reason_regression_rootcause",
    "UnifiedEngineeringTruthGraphResult",
    "build_unified_engineering_truth_graph",
    "DeterministicFusionReplayResult",
    "build_deterministic_fusion_replay",
    "RuntimeEvidenceFusionResult",
    "RuntimeEvidenceFusionEngine",
    "RuntimeEvidenceFusionRegistry",
    "RuntimeSequenceDriftResult",
    "reconstruct_runtime_sequence_drift",
    "LifecycleViolationReportResult",
    "detect_lifecycle_violations",
    "TopologyRuntimeCausalityResult",
    "map_topology_runtime_failures",
    "RegressionCausalityReportResult",
    "build_patch_runtime_causality",
    "RootCauseCandidatesResult",
    "build_root_cause_candidates",
    "EngineeringConfidenceReportResult",
    "build_engineering_confidence_report",
    "RuntimeIncidentReconstructionResult",
    "RuntimeIncidentReconstructor",
    "RuntimeIncidentReconstructionRegistry",
    "CausalityQueryPlanResult",
    "plan_causality_query",
    "RuntimeQuestionResolutionResult",
    "resolve_runtime_question",
    "MigrationQuestionResolutionResult",
    "resolve_migration_question",
    "TopologyQuestionResolutionResult",
    "resolve_topology_question",
    "PatchReasoningResolutionResult",
    "resolve_patch_reasoning_question",
    "ReplayEvidenceResolutionResult",
    "resolve_replay_evidence_question",
    "InvestigationReasoningResult",
    "synthesize_investigation_reasoning",
    "EngineeringQueryHistoryResult",
    "update_engineering_query_history",
    "ReasoningLineageResult",
    "build_reasoning_lineage",
    "InvestigationSessionRegistry",
    "EngineeringQueryEngine",
    "EngineeringQueryEngineResult",
    "GovernedTranslationIntelligenceEngine",
    "GovernedTranslationIntelligenceRegistry",
    "GovernedTranslationIntelligenceResult",
    "GovernedTranslationExecutionEngine",
    "GovernedTranslationExecutionRegistry",
    "GovernedTranslationExecutionResult",
    "GovernedAdaptiveRemediationEngine",
    "GovernedAdaptiveRemediationRegistry",
    "GovernedAdaptiveRemediationResult",
    "DmesgIngestionResult",
    "ingest_dmesg",
    "FtraceIngestionResult",
    "ingest_ftrace",
    "TracecmdIngestionResult",
    "ingest_tracecmd",
    "TinymixStateIngestionResult",
    "ingest_tinymix_state",
    "ProcfsRuntimeIngestionResult",
    "ingest_procfs_runtime",
    "DebugfsRuntimeIngestionResult",
    "ingest_debugfs_runtime",
    "SoundwireRuntimeIngestionResult",
    "ingest_soundwire_runtime",
    "DspMailboxIngestionResult",
    "ingest_dsp_mailbox",
    "IrqRuntimeIngestionResult",
    "ingest_irq_runtime",
    "RuntimeCaptureFingerprintResult",
    "build_runtime_capture_fingerprint",
    "EngineeringSessionReplayResult",
    "build_engineering_session_replay",
    "RuntimeSessionRegistry",
    "RuntimeEvidenceIngestionResult",
    "RuntimeEvidenceIngestor",
    "RuntimeEvidenceAcquisitionEngine",
    "RuntimeEvidenceAcquisitionRegistry",
    "RuntimeEvidenceAcquisitionResult",
    "UpstreamAcceptanceSimulationEngine",
    "UpstreamAcceptanceSimulationRegistry",
    "UpstreamAcceptanceSimulationResult",
    "ControlledPilotConversionEngine",
    "ControlledPilotConversionRegistry",
    "ControlledPilotConversionResult",
    "RealMicroConversionPilotEngine",
    "RealMicroConversionPilotRegistry",
    "RealMicroConversionPilotResult",
    "build_real_micro_source_input_model",
    "GovernedPatchsetOrchestrationEngine",
    "GovernedPatchsetOrchestrationRegistry",
    "GovernedPatchsetOrchestrationResult",
    "RealSourceTreeGovernedConversionEngine",
    "RealSourceTreeGovernedConversionRegistry",
    "RealSourceTreeGovernedConversionResult",
    "RealPatchApplicationGovernedBuildEngine",
    "RealPatchApplicationGovernedBuildRegistry",
    "RealPatchApplicationGovernedBuildResult",
    "CompileCognitionEngine",
    "CompileCognitionRegistry",
    "CompileCognitionResult",
    "BuildExecutionEngine",
    "BuildExecutionRegistry",
    "BuildExecutionResult",
    "SandboxPatchValidationEngine",
    "SandboxPatchValidationRegistry",
    "SandboxPatchValidationResult",
]
