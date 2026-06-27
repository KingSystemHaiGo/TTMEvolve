import { useCallback, useEffect, useState } from 'react'
import { AgentWorkbenchState, WorkbenchGoalCriterion } from '../hooks/useBackend'

const API_BASE = 'http://127.0.0.1:7345'

type QuickstartSurface = 'generic' | 'codex' | 'claude-code' | 'opencode'

const QUICKSTART_SURFACES: Array<{ id: QuickstartSurface; label: string }> = [
  { id: 'generic', label: 'Generic' },
  { id: 'codex', label: 'Codex' },
  { id: 'claude-code', label: 'Claude' },
  { id: 'opencode', label: 'opencode' },
]

interface Props {
  state: AgentWorkbenchState
}

interface HandoffPreview {
  latest_context_sync?: {
    revision?: number
    last_tool?: string
    plan_verdict?: string
    goal_overall?: string
    artifact_count?: number
    snapshot?: {
      task?: string
      trajectory_steps?: number
      last_tool?: string
      artifact_count?: number
      goal_checklist?: {
        overall?: string
      }
      plan_validation?: {
        verdict?: string
      }
    }
  } | null
  maker_briefing?: {
    readiness?: string
    authority?: string
    recommended_first_action?: string
    recommended_endpoint?: string
    selected_template?: {
      id?: string
      status?: string
    }
    suggested_tools?: string[]
  }
  maker_guard_latest?: {
    decision?: string
    tool?: string
    reason?: string
    authority?: string
    selected_template?: {
      id?: string
      status?: string
    }
    allowed_tools?: string[]
    suggested_tools?: string[]
    recommended_endpoint?: string
  } | null
  skill_summary?: {
    registry?: {
      state?: string
    }
    graph_summary?: Record<string, number | string>
    manifest_summary?: Record<string, number | string>
  }
  runtime_metrics_summary?: {
    llm_total_tokens?: number
    max_latency?: {
      phase?: string
      elapsed_ms?: number
    }
    token_cache?: {
      hits?: number
      misses?: number
      size?: number
    }
    retrieval?: {
      agents_md_hits?: number
      cold_recall_hits?: number
      context_build_ms?: number
    }
    tool_ranking?: {
      candidate_count?: number
      selected_count?: number
      ranking_ms?: number
      cache_hit?: boolean
      cache_size?: number
    }
  }
  learning_latest?: {
    event?: string
    state?: string
    detail?: string
    metrics?: Record<string, number | string | boolean>
  } | null
  runtime_advice?: {
    status?: string
    priority?: string
    next_action?: string
    reasons?: string[]
  }
  llm_probe_latest?: {
    status?: string
    ok?: boolean | null
    provider?: string
    runtime_kind?: string
    llm_class?: string
    model?: string
    endpoint?: string
    base_url?: string
    elapsed_ms?: number
    total_tokens?: number
    error_type?: string
    error?: string
  }
  token_rule?: string
}

interface QuickstartPreview {
  version?: string
  session_id?: string
  task?: string
  surface?: {
    id?: string
    label?: string
    memory_files?: string[]
    start_rule?: string
    skill_style?: string
  }
  prompt?: string
  prompt_markdown?: string
  boot_sequence?: string[]
  maker?: {
    readiness?: string
    connected?: boolean
    tool_count?: number
    warning_codes?: string[]
  }
  runtime_advice?: {
    status?: string
    priority?: string
    next_action?: string
    reasons?: string[]
  }
  maker_briefing?: {
    authority?: string
    selected_template?: {
      id?: string
      status?: string
    }
    recommended_first_action?: string
    suggested_tools?: string[]
  }
  llm_probe?: {
    status?: string
    ok?: boolean | null
    provider?: string
    runtime_kind?: string
    llm_class?: string
    model?: string
    endpoint?: string
    base_url?: string
    elapsed_ms?: number
    total_tokens?: number
    error_type?: string
    error?: string
  }
  endpoints?: Record<string, string>
  rules?: string[]
}

interface RuntimeAdvicePreview {
  status?: string
  priority?: string
  next_action?: string
  reasons?: string[]
  evidence?: Record<string, unknown>
}

interface RuntimeMetricsSummary {
  event_count?: number
  llm_total_tokens?: number
  max_latency?: {
    phase?: string
    elapsed_ms?: number
  }
  token_cache?: {
    hits?: number
    misses?: number
    size?: number
  }
  retrieval?: {
    agents_md_hits?: number
    cold_recall_hits?: number
    context_build_ms?: number
  }
  tool_ranking?: {
    phase?: string
    candidate_count?: number
    selected_count?: number
    ranking_ms?: number
    cache_hit?: boolean
    cache_size?: number
  }
}

interface RuntimeMetricLatest {
  kind?: string
  phase?: string
  iteration?: number
  elapsed_ms?: number
  total_tokens?: number
  token_count?: number
  candidate_count?: number
  selected_count?: number
  cache_hit?: boolean
  context_build_ms?: number
  timestamp?: number
}

interface RuntimeMetricsPreview {
  count?: number
  latest?: RuntimeMetricLatest | null
  summary?: RuntimeMetricsSummary
}

interface LearningEventPreview {
  event?: string
  state?: string
  detail?: string
  source_layer?: string
  target_layer?: string
  cause?: string
  metrics?: Record<string, number | string | boolean>
  timestamp?: number
}

interface LearningJobPolicyPreview {
  managed?: boolean
  mode?: string
  source?: string
  max_attempts?: number
  retry_delay_seconds?: number
  worker_idle_timeout_seconds?: number
  cancellation?: string
  truthfulness_rule?: string
}

interface LearningJobPreview {
  session_id?: string
  status?: string
  source?: string
  event?: string
  state?: string
  health?: string
  job_status?: string
  queue_depth?: number
  eligible?: boolean
  async?: boolean
  attempts?: number
  max_attempts?: number
  retryable?: boolean
  cancel_requested?: boolean
  cancelled?: boolean
  retried?: boolean
  reason?: string
  elapsed_ms?: number
  error?: string
  insight_count?: number
  shared_memory?: {
    counts?: {
      archived?: number
      promoted?: number
      conflicts?: number
    }
  }
  policy?: LearningJobPolicyPreview
}

interface LearningPreview {
  count?: number
  latest?: LearningEventPreview | null
  job?: LearningJobPreview | null
  policy?: LearningJobPolicyPreview
}

interface RagBenchmarkPreview {
  status?: string
  budget_status?: string
  endpoint?: string
  record_count?: number
  cache?: string
  cache_ttl_seconds?: number
  checked_at?: number
  no_network_call?: boolean
  truthfulness?: string
  embedding_quality?: {
    status?: string
    coverage?: string
    can_claim_production_embedding_quality?: boolean
  }
  closure_gate?: {
    can_claim_deterministic_rag_speed?: boolean
    can_claim_production_embedding_quality?: boolean
  }
  config?: {
    record_count?: number
    requested_record_count?: number
    warm_runs?: number
  }
  metrics?: {
    index_size?: number
    build_ms?: number
    cold_start_ms?: number
    first_recall_ms?: number
    warm_recall_p95_ms?: number
    warm_recall_max_ms?: number
    profile_hit_rate?: number
    fallback_hit_rate?: number
  }
  budgets?: Record<string, {
    value?: number
    threshold?: number
    relation?: string
    ok?: boolean
  }>
  note?: string
}

interface ProjectControlActionPreview {
  id?: string
  source?: string
  priority?: number
  owner_layer?: string
  domain?: string
  reason?: string
}

interface ProjectControlLayerSummary {
  status?: string
  decision?: string
  signal_count?: number
  action_count?: number
  can_claim_layer_independence?: boolean
  can_continue_user_task?: boolean
  top_action?: ProjectControlActionPreview
}

interface ProjectControlEngineeringSummary {
  status?: string
  decision?: string
  signal_count?: number
  action_count?: number
  memory_total_hits?: number
  tool_failure_count?: number
  plan_verdict?: string
  can_claim_engineering_control_ready?: boolean
  can_continue_user_task?: boolean
  can_claim_memory_rag_optimized?: boolean
  top_action?: ProjectControlActionPreview
}

interface ProjectControlPreview {
  version?: string
  status?: string
  current_focus?: string
  next_action?: string
  blockers?: Array<{
    id?: string
    severity?: string
    detail?: string
  }>
  classification?: {
    task_type?: string
    task_type_label?: string
    level?: string
    mode?: string
    understanding_status?: string
    declaration?: string
  }
  required_gates?: string[]
  completed_gates?: string[]
  pending_gates?: string[]
  memory_updates_due?: Array<{
    gate?: string
    file?: string
  }>
  verification?: {
    status?: string
    requires_evidence?: boolean
    rule?: string
    evidence_sources?: string[]
  }
  project_manager?: {
    role?: string
    health_check_required?: boolean
    owns_next_action?: boolean
  }
  layer_control?: ProjectControlLayerSummary
  engineering_control?: ProjectControlEngineeringSummary
  control_actions?: ProjectControlActionPreview[]
}

interface ProjectWritebackPreview {
  version?: string
  status?: string
  applicable?: boolean
  operation_count?: number
  files?: string[]
  invalid_target_count?: number
  reason?: string
  endpoint?: string
}

interface ProjectStatePreview {
  status?: string
  source?: string
  next_action?: string
  next_focus?: string
  goal_overall?: string
  plan_verdict?: string
  last_tool?: string
  risk_flags?: string[]
  project_control?: ProjectControlPreview
}

interface EvidenceBundlePreview {
  version?: string
  session_id?: string
  task?: string
  project_state?: ProjectStatePreview
  project_control?: ProjectControlPreview
  project_writeback?: ProjectWritebackPreview
  runtime_advice?: RuntimeAdvicePreview
  maker_mcp?: {
    readiness?: string
    connected?: boolean
    tool_count?: number
    top_tools?: Array<{ name?: string }>
    remote_identity?: {
      status?: string
    }
    last_call?: {
      tool?: string
      ok?: boolean
    }
  }
  maker_setup?: {
    readiness?: string
    blockers?: string[]
    warnings?: string[]
  }
  maker_tool_audit?: {
    ok?: boolean
    remote_tool_count?: number
  }
  latest_context_sync?: HandoffPreview['latest_context_sync']
  resume_drill?: {
    status?: string
    capability_levels?: {
      durable_handoff?: { status?: string }
      warm_process?: { status?: string }
      hot_tool_call?: { status?: string }
    }
    closure_gate?: {
      can_claim_long_task_durable_handoff?: boolean
      can_claim_hot_tool_call_resume?: boolean
    }
  }
  layer_summary?: {
    event_count?: number
    latest_by_layer?: Record<string, {
      state?: string
      event?: string
      source_layer?: string
      target_layer?: string
    }>
  }
  layer_health?: {
    layers?: {
      learning?: LearningJobPreview
    }
  }
  runtime_metrics_summary?: RuntimeMetricsSummary
  learning_latest?: LearningEventPreview | null
  learning_job?: LearningJobPreview
  learning_policy?: LearningJobPolicyPreview
  rag_benchmark?: RagBenchmarkPreview
  layer_control?: {
    status?: string
    decision?: string
  }
  engineering_control?: {
    status?: string
    decision?: string
    summary?: {
      memory_total_hits?: number
      tool_failure_count?: number
      plan_verdict?: string
    }
  }
  maker_guard_latest?: HandoffPreview['maker_guard_latest']
  llm_probe_latest?: HandoffPreview['llm_probe_latest']
  llm_call_proof?: {
    conclusion?: string
    provider?: string
    runtime_kind?: string
    model?: string
    expected_endpoint?: string
    observed_endpoint?: string
    evidence_source?: string
    endpoint_matches_expected?: boolean | null
    api_key_set?: boolean | null
  }
  llm_feedback_summary?: {
    total_runs?: number
    counts?: Record<string, number>
    latest_run?: {
      ok?: boolean
      failure_type?: string
      provider?: string
      actionable?: boolean
      decision?: string
      elapsed_ms?: number
    }
    latest_successful_feedback?: {
      top_pain_point?: string
      smallest_fix?: string
      priority?: string
    } | null
  }
  counts?: {
    context_sync?: number
    runtime_metrics?: number
    learning?: number
    layer?: number
    maker_guard?: number
    llm_probe?: number
  }
  endpoints?: Record<string, string>
  token_rule?: string
}

export default function AgentWorkbench({ state }: Props) {
  const activeTools = state.toolRuns.filter((run) => run.status === 'running').length
  const failedTools = state.toolRuns.filter((run) => run.status === 'error').length
  const completedTools = state.toolRuns.filter((run) => run.status === 'ok').length
  const makerGoalCount = (state.goalChecklist.criteria || [])
    .filter((item) => item.source === 'maker_template').length
  const hasSkillSync = Boolean(
    state.skillSync.state
    || state.skillSync.graphSummary
    || state.skillSync.conflicts?.length
    || state.skillSync.actionsPreview?.length
  )
  const hasContextSync = Boolean(state.contextSync.revision || state.contextSync.signature)
  const hasRuntimeContract = Boolean(
    state.runtimeContract.version
    || state.runtimeContract.makerMcp?.readiness
    || state.runtimeContract.warnings?.length
  )
  const hasMakerBriefing = Boolean(
    state.makerBriefing.recommendedFirstAction
    || state.makerBriefing.selectedTemplate?.id
    || state.makerBriefing.warningCodes?.length
  )
  const hasMakerGuard = Boolean(state.makerGuard.decision && state.makerGuard.decision !== 'skip')
  const hasLlmProbe = Boolean(state.llmProbe.status || state.llmProbe.provider || state.llmProbe.error)

  return (
    <section className={`agent-workbench stage-${state.stage}`}>
      <div className="workbench-layers">
        <LayerPill label="Agent" layer={state.layers.agent} />
        <LayerPill label="运行" layer={state.layers.runtime} />
        <LayerPill label="学习" layer={state.layers.learning} />
      </div>

      <div className="workbench-topline">
        <div>
          <span className="workbench-label">状态</span>
          <strong>{stageLabel(state.stage)}</strong>
        </div>
        <div>
          <span className="workbench-label">轮次</span>
          <strong>{state.iteration === null ? '-' : state.iteration + 1}</strong>
        </div>
        <div>
          <span className="workbench-label">工具</span>
          <strong>{activeTools}/{completedTools + failedTools}</strong>
        </div>
      </div>

      <div className="workbench-latency">
        <Metric label="首响" value={formatMs(state.latency.firstResponseMs)} />
        <Metric label="模型" value={formatMs(state.latency.lastLlmMs)} />
        <Metric label="工具" value={formatMs(state.latency.lastToolMs)} />
        <Metric label="总耗时" value={formatMs(state.latency.totalMs)} />
      </div>

      <div className="workbench-current">
        <span>{userFacingWorkbenchStatus(state.currentStatus) || '等待任务'}</span>
        {state.currentTool && <strong>{state.currentTool}</strong>}
      </div>

      {hasRuntimeContract && <RuntimeContractPanel state={state} />}

      {hasMakerBriefing && <MakerBriefingPanel state={state} />}

      {hasMakerGuard && <MakerGuardPanel state={state} />}

      {hasLlmProbe && <LlmProbePanel state={state} />}

      {hasContextSync && <ContextSyncPanel state={state} />}

      {hasSkillSync && <SkillSyncPanel state={state} />}

      {state.goalChecklist.criteria && state.goalChecklist.criteria.length > 0 && (
        <div className={`workbench-goals goals-${state.goalChecklist.overall || 'active'}`}>
          <div className="workbench-goals-head">
            <span>验收</span>
            <strong>{state.goalChecklist.nextFocus || goalOverallLabel(state.goalChecklist.overall)}</strong>
            {makerGoalCount > 0 && <small>{makerGoalCount} Maker flow</small>}
          </div>
          <div className="workbench-goal-list">
            {state.goalChecklist.criteria.map((item) => (
              <div
                key={item.id || item.label}
                className={`workbench-goal goal-${item.status || 'pending'} ${item.source === 'maker_template' ? 'goal-maker-template' : ''}`}
              >
                <span>{goalStatusLabel(item.status)}</span>
                <strong>{item.label || item.id}</strong>
                {goalMeta(item) && <small>{goalMeta(item)}</small>}
              </div>
            ))}
          </div>
        </div>
      )}

      {state.toolPreflight.tool && !state.toolPreflight.ok && (
        <div className="workbench-preflight">
          <span>{state.toolPreflight.suggestedNextStep || 'Fix the tool call before executing.'}</span>
          {state.toolPreflight.alternatives && state.toolPreflight.alternatives.length > 0 && (
            <small>
              {state.toolPreflight.alternatives
                .map((item) => item.name)
                .filter(Boolean)
                .join(' / ')}
            </small>
          )}
        </div>
      )}

      {state.planValidation.verdict && (
        <div className={`workbench-plan-validation plan-${state.planValidation.verdict}`}>
          <span>{planValidationLabel(state.planValidation.verdict)}</span>
          <strong>{state.planValidation.summary || state.planValidation.tool || 'step validation'}</strong>
          {state.planValidation.nextCheck && <small>{state.planValidation.nextCheck}</small>}
        </div>
      )}

      {state.commitState.idempotencyKey && (
        <div className={`workbench-commit commit-${commitClass(state.commitState.committed)}`}>
          <span>{commitLabel(state.commitState.committed)}</span>
          <strong>{state.commitState.tool || 'write'}</strong>
          <small>{state.commitState.idempotencyKey}</small>
          {commitDetail(state.commitState) && <em>{commitDetail(state.commitState)}</em>}
        </div>
      )}

      {state.currentThought && (
        <div className="workbench-thought">
          {state.currentThought}
        </div>
      )}

      {state.toolRuns.length > 0 && (
        <div className="workbench-tools">
          {state.toolRuns.slice(-4).map((run) => (
            <div key={run.id} className={`workbench-tool tool-${run.status}`}>
              <span>{run.tool}</span>
              <strong>{toolRunDetail(run)}</strong>
            </div>
          ))}
        </div>
      )}

      {state.lastError && (
        <div className="workbench-error">
          {state.lastError}
        </div>
      )}
    </section>
  )
}

function LlmProbePanel({ state }: { state: AgentWorkbenchState }) {
  const probe = state.llmProbe
  return (
    <div className={`workbench-llm-probe probe-${probe.ok ? 'ok' : 'error'}`}>
      <span>{probe.ok ? 'LLM Probe OK' : 'LLM Probe Failed'}</span>
      <strong>
        {llmProbeSummary({
          status: probe.status,
          ok: probe.ok,
          provider: probe.provider,
          runtime_kind: probe.runtimeKind,
          llm_class: probe.llmClass,
          model: probe.model,
          endpoint: probe.endpoint,
          base_url: probe.baseUrl,
          elapsed_ms: probe.elapsedMs,
          total_tokens: probe.totalTokens,
          error_type: probe.errorType,
          error: probe.error,
        })}
      </strong>
      {probe.outputPreview && <small>{probe.outputPreview}</small>}
    </div>
  )
}

function MakerBriefingPanel({ state }: { state: AgentWorkbenchState }) {
  const briefing = state.makerBriefing
  const template = briefing.selectedTemplate || {}
  const tools = briefing.suggestedTools || []
  const warnings = briefing.warningCodes || []
  const checklist = briefing.checklist || []
  const endpoints = briefing.evidenceEndpoints || {}
  const endpointText = [
    endpoints.context_sync ? `context=${endpoints.context_sync}` : '',
    endpoints.mcp_status ? `mcp=${endpoints.mcp_status}` : '',
    endpoints.mcp_tools ? `tools=${endpoints.mcp_tools}` : '',
  ].filter(Boolean).join(' | ')
  const status = briefing.connected
    ? 'ready'
    : warnings.length > 0
      ? 'warn'
      : 'blocked'

  return (
    <div className={`workbench-maker-briefing briefing-${status}`}>
      <div className="workbench-maker-briefing-head">
        <span>Maker 起步建议</span>
        <strong>{briefing.authority || '-'}</strong>
        {template.id && <small>{template.id}</small>}
      </div>
      {briefing.recommendedFirstAction && (
        <div className="workbench-maker-briefing-action">
          <span>下一步</span>
          <strong>{briefing.recommendedFirstAction}</strong>
        </div>
      )}
      <div className="workbench-maker-briefing-grid">
        <Metric label="就绪" value={briefing.readiness || '-'} />
        <Metric label="流程" value={template.status || '-'} />
        <Metric label="工具" value={String(tools.length)} />
        <Metric label="提醒" value={String(warnings.length)} />
      </div>
      {tools.length > 0 && (
        <div className="workbench-maker-briefing-line">
          <span>建议工具</span>
          <strong>{tools.join(' / ')}</strong>
        </div>
      )}
      {(briefing.recommendedEndpoint || endpointText) && (
        <div className="workbench-maker-briefing-line">
          <span>证据</span>
          <strong>{[briefing.recommendedEndpoint, endpointText].filter(Boolean).join(' | ')}</strong>
        </div>
      )}
      {template.acceptanceCriteria && template.acceptanceCriteria.length > 0 && (
        <div className="workbench-maker-briefing-list">
          {template.acceptanceCriteria.map((item) => (
            <small key={item}>{item}</small>
          ))}
        </div>
      )}
      {checklist.length > 0 && (
        <div className="workbench-maker-briefing-checks">
          {checklist.slice(0, 4).map((item) => (
            <small key={item.id || item.action}>
              {item.status || '-'} · {item.id || item.action}
            </small>
          ))}
        </div>
      )}
    </div>
  )
}

function MakerGuardPanel({ state }: { state: AgentWorkbenchState }) {
  const guard = state.makerGuard
  const decision = guard.decision || 'warn'
  const tools = guard.suggestedTools && guard.suggestedTools.length > 0
    ? guard.suggestedTools
    : guard.allowedTools || []

  return (
    <div className={`workbench-maker-guard guard-${decision}`}>
      <div className="workbench-maker-guard-head">
        <span>起步检查</span>
        <strong>{makerGuardLabel(decision)}</strong>
        {guard.tool && <small>{guard.tool}</small>}
      </div>
      {guard.reason && <strong className="workbench-maker-guard-reason">{guard.reason}</strong>}
      {(guard.recommendedFirstAction || tools.length > 0) && (
        <div className="workbench-maker-guard-line">
          <span>{guard.authority || 'maker'}</span>
          <small>
            {[guard.recommendedFirstAction, tools.length > 0 ? `tools=${tools.slice(0, 4).join('/')}` : '']
              .filter(Boolean)
              .join(' | ')}
          </small>
        </div>
      )}
      {guard.recommendedEndpoint && (
        <div className="workbench-maker-guard-line">
          <span>端点</span>
          <small>{guard.recommendedEndpoint}</small>
        </div>
      )}
    </div>
  )
}

function RuntimeContractPanel({ state }: { state: AgentWorkbenchState }) {
  const [handoffCopyState, setHandoffCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [handoffPreview, setHandoffPreview] = useState<HandoffPreview | null>(null)
  const [handoffPreviewState, setHandoffPreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [advicePreview, setAdvicePreview] = useState<RuntimeAdvicePreview | null>(null)
  const [advicePreviewState, setAdvicePreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [runtimeMetricsPreview, setRuntimeMetricsPreview] = useState<RuntimeMetricsPreview | null>(null)
  const [runtimeMetricsState, setRuntimeMetricsState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [learningPreview, setLearningPreview] = useState<LearningPreview | null>(null)
  const [learningPreviewState, setLearningPreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [learningControlState, setLearningControlState] = useState<'idle' | 'canceling' | 'retrying' | 'done' | 'error'>('idle')
  const [learningControlMessage, setLearningControlMessage] = useState('')
  const [ragBenchmarkPreview, setRagBenchmarkPreview] = useState<RagBenchmarkPreview | null>(null)
  const [ragBenchmarkState, setRagBenchmarkState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [evidencePreview, setEvidencePreview] = useState<EvidenceBundlePreview | null>(null)
  const [evidencePreviewState, setEvidencePreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [onboardingCopyState, setOnboardingCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [evidenceCopyState, setEvidenceCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [externalBootCopyState, setExternalBootCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [quickstartCopyState, setQuickstartCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [quickstartUrlCopyState, setQuickstartUrlCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const [quickstartPreview, setQuickstartPreview] = useState<QuickstartPreview | null>(null)
  const [quickstartPreviewState, setQuickstartPreviewState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [quickstartSurface, setQuickstartSurface] = useState<QuickstartSurface>('generic')
  const contract = state.runtimeContract
  const maker = contract.makerMcp || {}
  const readiness = maker.readiness || 'unknown'
  const remote = maker.remote_identity || {}
  const warnings = contract.warnings || []
  const warningCodes = contract.warningCodes || []
  const topTools = maker.top_tools || []
  const checklist = maker.first_action_checklist || []
  const templates = maker.task_templates || []
  const communication = contract.communication || {}
  const externalAgents = contract.externalAgents || {}
  const attachSequence = externalAgents.attach_sequence || []
  const onboardingPath = communication.onboarding_bundle || (
    state.sessionId
      ? `/agent/onboarding?session_id=${state.sessionId}&steps=20`
      : ''
  )
  const onboardingPathForSurface = onboardingPath
    ? withQueryParam(onboardingPath, 'surface', quickstartSurface)
    : ''
  const onboardingUrl = onboardingPathForSurface ? `${API_BASE}${onboardingPathForSurface}` : ''
  const onboardingMarkdownUrl = onboardingUrl
    ? `${onboardingUrl}${onboardingUrl.includes('?') ? '&' : '?'}format=markdown`
    : ''
  const readinessPath = communication.runtime_readiness || (
    state.sessionId
      ? `/runtime/readiness?session_id=${state.sessionId}`
      : ''
  )
  const readinessUrl = readinessPath ? `${API_BASE}${readinessPath}` : ''
  const quickstartBasePath = communication.quickstart_bundle || (
    state.sessionId
      ? `/agent/quickstart?session_id=${state.sessionId}&steps=3`
      : ''
  )
  const quickstartPath = quickstartBasePath
    ? withQueryParam(quickstartBasePath, 'surface', quickstartSurface)
    : ''
  const quickstartUrl = quickstartPath ? `${API_BASE}${quickstartPath}` : ''
  const quickstartMarkdownUrl = quickstartUrl
    ? `${quickstartUrl}${quickstartUrl.includes('?') ? '&' : '?'}format=markdown`
    : ''
  const handoffPath = communication.handoff_bundle || (
    state.sessionId
      ? `/agent/handoff?session_id=${state.sessionId}&steps=3`
      : ''
  )
  const handoffUrl = handoffPath ? `${API_BASE}${handoffPath}` : ''
  const evidencePath = communication.evidence_bundle || (
    state.sessionId
      ? `/sessions/${state.sessionId}/evidence?steps=20`
      : ''
  )
  const evidenceUrl = evidencePath ? `${API_BASE}${evidencePath}` : ''
  const evidenceMarkdownUrl = evidenceUrl
    ? `${evidenceUrl}${evidenceUrl.includes('?') ? '&' : '?'}format=markdown`
    : ''
  const advicePath = communication.runtime_advice || (
    state.sessionId
      ? `/sessions/${state.sessionId}/runtime-advice?steps=20`
      : ''
  )
  const adviceUrl = advicePath ? `${API_BASE}${advicePath}` : ''
  const metricsPath = communication.runtime_metrics || (
    state.sessionId
      ? `/sessions/${state.sessionId}/runtime-metrics?steps=20`
      : ''
  )
  const metricsUrl = metricsPath ? `${API_BASE}${metricsPath}` : ''
  const projectWritebackPath = communication.project_writeback || (
    state.sessionId
      ? `/sessions/${state.sessionId}/project-writeback`
      : ''
  )
  const projectWritebackUrl = projectWritebackPath ? `${API_BASE}${projectWritebackPath}` : ''
  const learningPath = communication.learning_status || (
    state.sessionId
      ? `/sessions/${state.sessionId}/learning?steps=20`
      : ''
  )
  const learningUrl = learningPath ? `${API_BASE}${learningPath}` : ''
  const learningCancelPath = communication.learning_cancel || (
    state.sessionId
      ? `/sessions/${state.sessionId}/learning/cancel`
      : ''
  )
  const learningCancelUrl = learningCancelPath ? `${API_BASE}${learningCancelPath}` : ''
  const learningRetryPath = communication.learning_retry || (
    state.sessionId
      ? `/sessions/${state.sessionId}/learning/retry`
      : ''
  )
  const learningRetryUrl = learningRetryPath ? `${API_BASE}${learningRetryPath}` : ''
  const ragBenchmarkPath = communication.rag_benchmark || '/memory/rag-benchmark'
  const ragBenchmarkUrl = ragBenchmarkPath ? `${API_BASE}${ragBenchmarkPath}` : ''
  const tokenRules = contract.tokenEfficiency?.rules || []
  const status = readiness === 'ready'
    ? 'ready'
    : readiness === 'disconnected'
      ? 'offline'
      : 'degraded'
  const projectControlPreview = evidencePreview?.project_state?.project_control || evidencePreview?.project_control || null
  const projectWritebackPreview = evidencePreview?.project_writeback || null

  useEffect(() => {
    setQuickstartPreview(null)
    setQuickstartPreviewState('idle')
    setQuickstartCopyState('idle')
    setQuickstartUrlCopyState('idle')
    setExternalBootCopyState('idle')
    setOnboardingCopyState('idle')
  }, [quickstartSurface, state.sessionId])

  useEffect(() => {
    setAdvicePreview(null)
    setAdvicePreviewState('idle')
    setRuntimeMetricsPreview(null)
    setRuntimeMetricsState('idle')
    setLearningPreview(null)
    setLearningPreviewState('idle')
    setLearningControlState('idle')
    setLearningControlMessage('')
    setRagBenchmarkPreview(null)
    setRagBenchmarkState('idle')
    setEvidencePreview(null)
    setEvidencePreviewState('idle')
    setEvidenceCopyState('idle')
  }, [state.sessionId])

  const applyEvidenceBundle = useCallback((data: EvidenceBundlePreview) => {
    const learningJob = data.learning_job || learningJobFromLayerHealth(data.layer_health)
    setEvidencePreview(data)
    setAdvicePreview(data.runtime_advice || null)
    setAdvicePreviewState('idle')
    setRuntimeMetricsPreview({
      count: data.counts?.runtime_metrics,
      latest: null,
      summary: data.runtime_metrics_summary || {},
    })
    setRuntimeMetricsState('idle')
    setLearningPreview({
      count: data.counts?.learning,
      latest: data.learning_latest || null,
      job: learningJob || null,
      policy: learningJob?.policy || data.learning_policy || {},
    })
    setLearningPreviewState('idle')
    setRagBenchmarkPreview(data.rag_benchmark || null)
    setRagBenchmarkState('idle')
  }, [])

  const loadEvidenceBundle = useCallback(async (mode: 'manual' | 'auto' = 'manual') => {
    if (!evidenceUrl || evidencePreviewState === 'loading') return
    if (mode === 'manual') setEvidencePreviewState('loading')
    try {
      const response = await fetch(evidenceUrl)
      if (!response.ok) {
        throw new Error(`evidence ${response.status}`)
      }
      const data = await response.json()
      applyEvidenceBundle(data)
      setEvidencePreviewState('idle')
    } catch {
      setEvidencePreviewState('error')
    }
  }, [applyEvidenceBundle, evidencePreviewState, evidenceUrl])

  useEffect(() => {
    if (!evidenceUrl || !state.sessionId) return
    const timer = window.setTimeout(() => {
      void loadEvidenceBundle('auto')
    }, 250)
    return () => window.clearTimeout(timer)
  }, [
    evidenceUrl,
    loadEvidenceBundle,
    state.sessionId,
    state.llmProbe.status,
    state.llmProbe.errorType,
    state.makerGuard.decision,
    state.contextSync.revision,
    state.goalChecklist.overall,
    state.latency.firstResponseMs,
    state.latency.lastLlmMs,
    state.latency.lastToolMs,
    state.latency.totalMs,
    state.layers.runtime.event,
    state.layers.learning.status,
    state.layers.learning.event,
    state.layers.learning.timestamp,
  ])

  const loadRuntimeAdvice = useCallback(async (mode: 'manual' | 'auto' = 'manual') => {
    if (!adviceUrl || advicePreviewState === 'loading') return
    if (mode === 'manual') setAdvicePreviewState('loading')
    try {
      const response = await fetch(adviceUrl)
      if (!response.ok) {
        throw new Error(`runtime advice ${response.status}`)
      }
      const data = await response.json()
      setAdvicePreview(data.runtime_advice || null)
      setAdvicePreviewState('idle')
    } catch {
      setAdvicePreviewState('error')
    }
  }, [adviceUrl, advicePreviewState])

  useEffect(() => {
    if (evidenceUrl || !adviceUrl || !state.sessionId) return
    const timer = window.setTimeout(() => {
      void loadRuntimeAdvice('auto')
    }, 250)
    return () => window.clearTimeout(timer)
  }, [
    adviceUrl,
    evidenceUrl,
    loadRuntimeAdvice,
    state.sessionId,
    state.llmProbe.status,
    state.llmProbe.errorType,
    state.makerGuard.decision,
    state.contextSync.revision,
    state.goalChecklist.overall,
    state.latency.totalMs,
    state.layers.learning.event,
  ])

  const loadRuntimeMetrics = useCallback(async (mode: 'manual' | 'auto' = 'manual') => {
    if (!metricsUrl) return
    if (mode === 'manual') setRuntimeMetricsState('loading')
    try {
      const response = await fetch(metricsUrl)
      if (!response.ok) {
        throw new Error(`runtime metrics ${response.status}`)
      }
      const data = await response.json()
      setRuntimeMetricsPreview({
        count: data.count,
        latest: data.latest || null,
        summary: data.summary || {},
      })
      setRuntimeMetricsState('idle')
    } catch {
      setRuntimeMetricsState('error')
    }
  }, [metricsUrl])

  useEffect(() => {
    if (evidenceUrl || !metricsUrl || !state.sessionId) return
    const timer = window.setTimeout(() => {
      void loadRuntimeMetrics('auto')
    }, 250)
    return () => window.clearTimeout(timer)
  }, [
    metricsUrl,
    evidenceUrl,
    loadRuntimeMetrics,
    state.sessionId,
    state.layers.runtime.event,
    state.latency.firstResponseMs,
    state.latency.lastLlmMs,
    state.latency.lastToolMs,
    state.latency.totalMs,
  ])

  const loadLearningStatus = useCallback(async (mode: 'manual' | 'auto' = 'manual') => {
    if (!learningUrl) return
    if (mode === 'manual') setLearningPreviewState('loading')
    try {
      const response = await fetch(learningUrl)
      if (!response.ok) {
        throw new Error(`learning ${response.status}`)
      }
      const data = await response.json()
      setLearningPreview({
        count: data.count,
        latest: data.latest || null,
        job: data.job || null,
        policy: data.policy || data.job?.policy || {},
      })
      setLearningPreviewState('idle')
    } catch {
      setLearningPreviewState('error')
    }
  }, [learningUrl])

  const postLearningControl = useCallback(async (kind: 'cancel' | 'retry') => {
    const url = kind === 'cancel' ? learningCancelUrl : learningRetryUrl
    if (!url) return
    setLearningControlState(kind === 'cancel' ? 'canceling' : 'retrying')
    setLearningControlMessage('')
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      let data: Record<string, unknown> = {}
      try {
        data = await response.json()
      } catch {
        data = {}
      }
      const job = (data.job && typeof data.job === 'object'
        ? data.job
        : data) as LearningJobPreview
      if (!response.ok || data.ok === false) {
        const reason = String(data.error || data.reason || `${kind} failed with ${response.status}`)
        setLearningControlState('error')
        setLearningControlMessage(`blocked: ${reason}`)
      } else {
        setLearningPreview((previous) => ({
          ...(previous || {}),
          job,
          policy: job.policy || previous?.policy || {},
        }))
        setLearningControlState('done')
        setLearningControlMessage(learningControlResultSummary(kind, job))
        window.setTimeout(() => setLearningControlState('idle'), 1600)
      }
      await loadLearningStatus('auto')
      if (evidenceUrl) {
        await loadEvidenceBundle('auto')
      }
    } catch (error) {
      setLearningControlState('error')
      setLearningControlMessage(`failed: ${error instanceof Error ? error.message : String(error)}`)
    }
  }, [evidenceUrl, learningCancelUrl, learningRetryUrl, loadEvidenceBundle, loadLearningStatus])

  useEffect(() => {
    if (evidenceUrl || !learningUrl || !state.sessionId) return
    const timer = window.setTimeout(() => {
      void loadLearningStatus('auto')
    }, 250)
    return () => window.clearTimeout(timer)
  }, [
    learningUrl,
    evidenceUrl,
    loadLearningStatus,
    state.sessionId,
    state.stage,
    state.layers.learning.status,
    state.layers.learning.event,
    state.layers.learning.timestamp,
  ])

  const loadRagBenchmark = useCallback(async (force = false) => {
    if (!ragBenchmarkUrl || ragBenchmarkState === 'loading') return
    setRagBenchmarkState('loading')
    try {
      const separator = ragBenchmarkUrl.includes('?') ? '&' : '?'
      const response = await fetch(force ? `${ragBenchmarkUrl}${separator}force=true` : ragBenchmarkUrl)
      if (!response.ok) {
        throw new Error(`rag benchmark ${response.status}`)
      }
      const data = await response.json()
      setRagBenchmarkPreview(data)
      setRagBenchmarkState('idle')
    } catch {
      setRagBenchmarkState('error')
    }
  }, [ragBenchmarkState, ragBenchmarkUrl])

  const copyHandoff = async () => {
    if (!handoffUrl) return
    try {
      await navigator.clipboard.writeText(handoffUrl)
      setHandoffCopyState('copied')
      window.setTimeout(() => setHandoffCopyState('idle'), 1600)
    } catch {
      setHandoffCopyState('error')
      window.setTimeout(() => setHandoffCopyState('idle'), 2200)
    }
  }

  const copyExternalAgentBoot = async () => {
    const lines = externalAgentBootLines({
      quickstartMarkdownUrl,
      quickstartUrl,
      onboardingMarkdownUrl,
      onboardingUrl,
      evidenceMarkdownUrl,
      readinessUrl,
      evidenceUrl,
      handoffUrl,
      adviceUrl,
      metricsUrl,
      learningUrl,
      communication,
      quickstartSurface,
    })
    if (lines.length === 0) return
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      setExternalBootCopyState('copied')
      window.setTimeout(() => setExternalBootCopyState('idle'), 1600)
    } catch {
      setExternalBootCopyState('error')
      window.setTimeout(() => setExternalBootCopyState('idle'), 2200)
    }
  }

  const copyOnboardingMarkdown = async () => {
    if (!onboardingMarkdownUrl) return
    try {
      const response = await fetch(onboardingMarkdownUrl)
      if (!response.ok) {
        throw new Error(`onboarding markdown ${response.status}`)
      }
      const text = await response.text()
      await navigator.clipboard.writeText(text)
      setOnboardingCopyState('copied')
      window.setTimeout(() => setOnboardingCopyState('idle'), 1600)
    } catch {
      setOnboardingCopyState('error')
      window.setTimeout(() => setOnboardingCopyState('idle'), 2200)
    }
  }

  const copyEvidenceMarkdown = async () => {
    if (!evidenceMarkdownUrl) return
    try {
      const response = await fetch(evidenceMarkdownUrl)
      if (!response.ok) {
        throw new Error(`evidence markdown ${response.status}`)
      }
      const text = await response.text()
      await navigator.clipboard.writeText(text)
      setEvidenceCopyState('copied')
      window.setTimeout(() => setEvidenceCopyState('idle'), 1600)
    } catch {
      setEvidenceCopyState('error')
      window.setTimeout(() => setEvidenceCopyState('idle'), 2200)
    }
  }

  const loadQuickstartPreview = async () => {
    if (!quickstartUrl || quickstartPreviewState === 'loading') return
    setQuickstartPreviewState('loading')
    try {
      const response = await fetch(quickstartUrl)
      if (!response.ok) {
        throw new Error(`quickstart ${response.status}`)
      }
      const data = await response.json()
      setQuickstartPreview(data)
      setQuickstartPreviewState('idle')
    } catch {
      setQuickstartPreviewState('error')
    }
  }

  const copyQuickstartPrompt = async () => {
    let text = quickstartPreview?.prompt_markdown || quickstartPreview?.prompt
    if (!text && quickstartMarkdownUrl) {
      try {
        const response = await fetch(quickstartMarkdownUrl)
        if (!response.ok) {
          throw new Error(`quickstart markdown ${response.status}`)
        }
        text = await response.text()
      } catch {
        setQuickstartCopyState('error')
        window.setTimeout(() => setQuickstartCopyState('idle'), 2200)
        return
      }
    }
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setQuickstartCopyState('copied')
      window.setTimeout(() => setQuickstartCopyState('idle'), 1600)
    } catch {
      setQuickstartCopyState('error')
      window.setTimeout(() => setQuickstartCopyState('idle'), 2200)
    }
  }

  const copyQuickstartMarkdownUrl = async () => {
    if (!quickstartMarkdownUrl) return
    try {
      await navigator.clipboard.writeText(quickstartMarkdownUrl)
      setQuickstartUrlCopyState('copied')
      window.setTimeout(() => setQuickstartUrlCopyState('idle'), 1600)
    } catch {
      setQuickstartUrlCopyState('error')
      window.setTimeout(() => setQuickstartUrlCopyState('idle'), 2200)
    }
  }

  const loadHandoffPreview = async () => {
    if (!handoffUrl || handoffPreviewState === 'loading') return
    setHandoffPreviewState('loading')
    try {
      const response = await fetch(handoffUrl)
      if (!response.ok) {
        throw new Error(`handoff ${response.status}`)
      }
      const data = await response.json()
      setHandoffPreview(data)
      setHandoffPreviewState('idle')
    } catch {
      setHandoffPreviewState('error')
    }
  }

  const learningJob = learningPreview?.job || null
  const learningActionBusy = learningControlState === 'canceling' || learningControlState === 'retrying'
  const learningBoundary = learningControlBoundary(learningJob)

  return (
    <div className={`workbench-runtime-contract contract-${status}`}>
      <div className="workbench-contract-head">
        <span>运行契约</span>
        <strong>{runtimeContractLabel(readiness)}</strong>
        {contract.version && <small>{contract.version}</small>}
      </div>
      <div className="workbench-contract-grid">
        <Metric label="MakerMCP" value={String(readiness)} />
        <Metric label="工具" value={String(maker.tool_count || 0)} />
        <Metric label="身份" value={String(remote.status || '-')} />
        <Metric label="规则" value={String(tokenRules.length)} />
      </div>
      {topTools.length > 0 && (
        <div className="workbench-contract-line">
          <span>Maker 工具</span>
          <strong>{topTools.map((tool) => tool.name).filter(Boolean).slice(0, 4).join(' / ')}</strong>
        </div>
      )}
      {(onboardingUrl || readinessUrl || quickstartUrl || handoffUrl || adviceUrl) && (
        <div className="workbench-external-agent">
          <div className="workbench-external-agent-head">
            <span>外部 Agent 启动包</span>
            <strong>{externalAgentBootSummary({ onboardingUrl, readinessUrl, quickstartUrl, evidenceUrl, handoffUrl, adviceUrl, metricsUrl, learningUrl })}</strong>
            <div className="workbench-external-agent-actions">
              {onboardingMarkdownUrl && (
                <button type="button" onClick={copyOnboardingMarkdown}>
                  {onboardingCopyState === 'copied'
                    ? '已复制'
                    : onboardingCopyState === 'error'
                      ? '复制失败'
                      : '复制启动包'}
                </button>
              )}
              {evidenceUrl && (
                <button type="button" onClick={() => loadEvidenceBundle('manual')}>
                  {evidencePreviewState === 'loading'
                    ? '读取中'
                    : evidencePreviewState === 'error'
                      ? '重试'
                      : '证据'}
                </button>
              )}
              {evidenceMarkdownUrl && (
                <button type="button" onClick={copyEvidenceMarkdown}>
                  {evidenceCopyState === 'copied'
                    ? '已复制'
                    : evidenceCopyState === 'error'
                      ? '复制失败'
                      : '复制证据'}
                </button>
              )}
              <button type="button" onClick={copyExternalAgentBoot}>
                {externalBootCopyState === 'copied'
                  ? '已复制'
                  : externalBootCopyState === 'error'
                    ? '复制失败'
                    : '复制启动'}
              </button>
            </div>
          </div>
          {evidenceUrl && (
            <div className="workbench-external-agent-evidence">
              <span>证据包</span>
              <strong>{evidenceBundleSummary(evidencePreview, evidencePreviewState)}</strong>
            </div>
          )}
          {onboardingUrl && (
            <div className="workbench-external-agent-evidence workbench-external-agent-onboarding">
              <span>启动入口</span>
              <strong>{onboardingUrl}</strong>
            </div>
          )}
          <div className="workbench-external-agent-steps">
            {externalAgentBootLines({
              quickstartMarkdownUrl,
              quickstartUrl,
              onboardingMarkdownUrl,
              onboardingUrl,
              evidenceMarkdownUrl,
              readinessUrl,
              evidenceUrl,
              handoffUrl,
              adviceUrl,
              metricsUrl,
              learningUrl,
              communication,
              quickstartSurface,
            }).slice(0, 7).map((line, index) => (
              <small key={`${line}-${index}`}>{line}</small>
            ))}
          </div>
        </div>
      )}
      {projectControlPreview && (
        <div className={`workbench-project-control project-${projectControlClass(projectControlPreview)}`}>
          <div className="workbench-project-control-head">
            <span>项目控制</span>
            <strong>{projectControlSummary(projectControlPreview)}</strong>
          </div>
          <div className="workbench-project-control-grid">
            <Metric label="状态" value={projectControlStatusLabel(projectControlPreview.status)} />
            <Metric label="门槛" value={projectControlGateSummary(projectControlPreview)} />
            <Metric label="验证" value={projectControlPreview.verification?.status || '-'} />
            <Metric label="POST" value={String(projectControlPreview.memory_updates_due?.length ?? 0)} />
          </div>
          {projectControlPreview.next_action && (
            <small>下一步：{projectControlPreview.next_action}</small>
          )}
          {projectControlLayerSummary(projectControlPreview) && (
            <small>Layer control: {projectControlLayerSummary(projectControlPreview)}</small>
          )}
          {projectControlEngineeringSummary(projectControlPreview) && (
            <small>Engineering control: {projectControlEngineeringSummary(projectControlPreview)}</small>
          )}
          {projectControlActionSummary(projectControlPreview) && (
            <em>{projectControlActionSummary(projectControlPreview)}</em>
          )}
          {projectControlBlockerSummary(projectControlPreview) && (
            <em>{projectControlBlockerSummary(projectControlPreview)}</em>
          )}
          {projectControlMemoryDue(projectControlPreview) && (
            <code>{projectControlMemoryDue(projectControlPreview)}</code>
          )}
          {projectWritebackPreview && (
            <small>写回计划：{projectWritebackSummary(projectWritebackPreview, projectWritebackUrl)}</small>
          )}
        </div>
      )}
      {quickstartUrl && (
        <div className="workbench-quickstart">
          <div className="workbench-quickstart-head">
            <span>模型启动指引</span>
            <div>
              <button type="button" onClick={loadQuickstartPreview}>
                {quickstartPreviewState === 'loading'
                  ? '读取中'
                  : quickstartPreviewState === 'error'
                    ? '重试'
                    : quickstartPreview
                      ? '刷新'
                      : '预览'}
              </button>
              <button
                type="button"
                onClick={copyQuickstartPrompt}
                disabled={!quickstartMarkdownUrl && !quickstartPreview?.prompt_markdown && !quickstartPreview?.prompt}
              >
                {quickstartCopyState === 'copied'
                  ? 'Copied'
                  : quickstartCopyState === 'error'
                    ? 'Copy failed'
                    : 'Copy Prompt'}
              </button>
              <button type="button" onClick={copyQuickstartMarkdownUrl}>
                {quickstartUrlCopyState === 'copied'
                  ? 'URL Copied'
                  : quickstartUrlCopyState === 'error'
                    ? 'URL failed'
                    : 'Copy MD URL'}
              </button>
            </div>
          </div>
          <div className="workbench-quickstart-surfaces" role="tablist" aria-label="LLM quickstart target">
            {QUICKSTART_SURFACES.map((surface) => (
              <button
                key={surface.id}
                type="button"
                role="tab"
                aria-selected={quickstartSurface === surface.id}
                className={quickstartSurface === surface.id ? 'active' : ''}
                onClick={() => setQuickstartSurface(surface.id)}
              >
                {surface.label}
              </button>
            ))}
          </div>
          <strong>{quickstartUrl}</strong>
          {quickstartMarkdownUrl && <small>{quickstartMarkdownUrl}</small>}
          {quickstartPreview && (
            <div className="workbench-quickstart-preview">
              <div>
                <span>Advice</span>
                <strong>{quickstartAdviceSummary(quickstartPreview)}</strong>
              </div>
              <div>
                <span>Maker</span>
                <strong>{quickstartMakerSummary(quickstartPreview)}</strong>
              </div>
              <div>
                <span>Surface</span>
                <strong>{quickstartSurfaceSummary(quickstartPreview)}</strong>
              </div>
              <div>
                <span>LLM</span>
                <strong>{quickstartLlmSummary(quickstartPreview)}</strong>
              </div>
              {(quickstartPreview.prompt_markdown || quickstartPreview.prompt) && (
                <small>{quickstartPreview.prompt_markdown || quickstartPreview.prompt}</small>
              )}
              {quickstartPreview.boot_sequence && quickstartPreview.boot_sequence.length > 0 && (
                <div className="workbench-quickstart-steps">
                  {quickstartPreview.boot_sequence.slice(0, 4).map((step, index) => (
                    <small key={`${step}-${index}`}>{step}</small>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {communication.context_sync && (
        <div className="workbench-contract-line">
          <span>Context</span>
          <strong>{communication.context_sync}</strong>
        </div>
      )}
      {communication.maker_briefing && (
        <div className="workbench-contract-line">
          <span>Briefing</span>
          <strong>{communication.maker_briefing}</strong>
        </div>
      )}
      {communication.maker_guard && (
        <div className="workbench-contract-line">
          <span>Guard</span>
          <strong>{communication.maker_guard}</strong>
        </div>
      )}
      {communication.runtime_metrics && (
        <div className="workbench-contract-line">
          <span>运行</span>
          <strong>{communication.runtime_metrics}</strong>
        </div>
      )}
      {communication.project_writeback && (
        <div className="workbench-contract-line">
          <span>写回</span>
          <strong>{communication.project_writeback}</strong>
        </div>
      )}
      {metricsUrl && (
        <div className="workbench-runtime-metrics">
          <div className="workbench-runtime-metrics-head">
            <span>运行指标</span>
            <strong>{runtimeMetricsSummary(runtimeMetricsPreview?.summary)}</strong>
            <button type="button" onClick={() => loadRuntimeMetrics('manual')}>
              {runtimeMetricsState === 'loading'
                ? '读取中'
                : runtimeMetricsState === 'error'
                  ? '重试'
                  : '刷新'}
            </button>
          </div>
          <div className="workbench-runtime-metrics-grid">
            <Metric label="事件" value={String(runtimeMetricsPreview?.count ?? '-')} />
            <Metric label="Tokens" value={String(runtimeMetricsPreview?.summary?.llm_total_tokens ?? '-')} />
            <Metric label="Cache" value={runtimeTokenCacheSummary(runtimeMetricsPreview?.summary)} />
            <Metric label="工具筛选" value={runtimeRankingSummary(runtimeMetricsPreview?.summary)} />
          </div>
          {runtimeMetricsPreview?.latest && (
            <small>{runtimeLatestMetricSummary(runtimeMetricsPreview.latest)}</small>
          )}
        </div>
      )}
      {ragBenchmarkUrl && (
        <div className={`workbench-rag-benchmark benchmark-${ragBenchmarkClass(ragBenchmarkPreview, ragBenchmarkState)}`}>
          <div className="workbench-rag-benchmark-head">
            <span>记忆基准</span>
            <strong>{ragBenchmarkSummary(ragBenchmarkPreview, ragBenchmarkState)}</strong>
            <button type="button" onClick={() => loadRagBenchmark(true)}>
              {ragBenchmarkState === 'loading'
                ? '读取中'
                : ragBenchmarkState === 'error'
                  ? '重试'
                  : '刷新'}
            </button>
          </div>
          <div className="workbench-rag-benchmark-grid">
            <Metric label="预算" value={ragBenchmarkPreview?.budget_status || '-'} />
            <Metric label="Quality" value={ragBenchmarkPreview?.embedding_quality?.status || '-'} />
            <Metric label="记录" value={String(ragBenchmarkRecordCount(ragBenchmarkPreview))} />
            <Metric label="首召回" value={formatMs(ragBenchmarkPreview?.metrics?.first_recall_ms)} />
            <Metric label="Warm p95" value={formatMs(ragBenchmarkPreview?.metrics?.warm_recall_p95_ms)} />
          </div>
          <small>{ragBenchmarkDetailLine(ragBenchmarkPreview, ragBenchmarkUrl)}</small>
          {(ragBenchmarkPreview?.truthfulness || ragBenchmarkPreview?.note) && (
            <code>{ragBenchmarkPreview.truthfulness || ragBenchmarkPreview.note}</code>
          )}
        </div>
      )}
      {communication.llm_probe && (
        <div className="workbench-contract-line">
          <span>模型探测</span>
          <strong>{communication.llm_probe}</strong>
        </div>
      )}
      {communication.llm_probe_history && (
        <div className="workbench-contract-line">
          <span>探测历史</span>
          <strong>{communication.llm_probe_history}</strong>
        </div>
      )}
      {communication.runtime_advice && (
        <div className="workbench-contract-line">
          <span>建议</span>
          <strong>{communication.runtime_advice}</strong>
        </div>
      )}
      {adviceUrl && (
        <div className={`workbench-runtime-advice advice-${advicePreview?.priority || advicePreview?.status || 'unknown'}`}>
          <div className="workbench-runtime-advice-head">
            <span>运行建议</span>
            <strong>{runtimeAdviceSummary(advicePreview)}</strong>
            <button type="button" onClick={() => loadRuntimeAdvice('manual')}>
              {advicePreviewState === 'loading'
                ? '读取中'
                : advicePreviewState === 'error'
                  ? '重试'
                  : '刷新'}
            </button>
          </div>
          {advicePreview?.next_action && <small>{advicePreview.next_action}</small>}
          {advicePreview?.reasons && advicePreview.reasons.length > 0 && (
            <em>{advicePreview.reasons.slice(0, 2).join(' / ')}</em>
          )}
          {advicePreview?.evidence && (
            <code>{runtimeAdviceEvidenceSummary(advicePreview.evidence)}</code>
          )}
        </div>
      )}
      {communication.learning_status && (
        <div className="workbench-contract-line">
          <span>学习</span>
          <strong>{communication.learning_status}</strong>
        </div>
      )}
      {learningUrl && (
        <div className={`workbench-learning-status learning-${learningStatusClass(learningPreview, state.layers.learning.status)}`}>
          <div className="workbench-learning-status-head">
            <span>学习状态</span>
            <strong>{learningStatusSummary(learningPreview, state.layers.learning.detail)}</strong>
            <button type="button" onClick={() => loadLearningStatus('manual')}>
              {learningPreviewState === 'loading'
                ? '读取中'
                : learningPreviewState === 'error'
                  ? '重试'
                  : '刷新'}
            </button>
          </div>
          {learningJob && (
            <small>{learningJobSummary(learningJob, learningPreview?.policy)}</small>
          )}
          {(learningCanCancel(learningJob) || learningCanRetry(learningJob) || learningControlMessage || learningBoundary) && (
            <div className="workbench-learning-actions">
              {learningCanCancel(learningJob) && (
                <button
                  type="button"
                  onClick={() => void postLearningControl('cancel')}
                  disabled={learningActionBusy}
                >
                  {learningControlState === 'canceling' ? 'Canceling' : 'Cancel'}
                </button>
              )}
              {learningCanRetry(learningJob) && (
                <button
                  type="button"
                  onClick={() => void postLearningControl('retry')}
                  disabled={learningActionBusy}
                >
                  {learningControlState === 'retrying' ? 'Retrying' : 'Retry'}
                </button>
              )}
              <small>{learningControlMessage || learningBoundary || learningControlIdleSummary(learningJob)}</small>
            </div>
          )}
          {learningPreview?.latest?.detail && <small>{learningPreview.latest.detail}</small>}
          {learningPreview?.latest?.metrics && (
            <code>{learningMetricsSummary(learningPreview.latest.metrics)}</code>
          )}
        </div>
      )}
      {warningCodes.length > 0 && (
        <div className="workbench-contract-line">
          <span>诊断码</span>
          <strong>{warningCodes.join(' / ')}</strong>
        </div>
      )}
      {handoffUrl && (
        <div className="workbench-handoff">
          <div className="workbench-handoff-head">
            <span>Agent 交接</span>
            <div>
              <button type="button" onClick={loadHandoffPreview}>
                {handoffPreviewState === 'loading'
                  ? '读取中'
                  : handoffPreviewState === 'error'
                    ? '重试'
                    : handoffPreview
                      ? '刷新'
                      : '预览'}
              </button>
              <button type="button" onClick={copyHandoff}>
                {handoffCopyState === 'copied'
                  ? 'Copied'
                  : handoffCopyState === 'error'
                    ? 'Copy failed'
                    : 'Copy URL'}
              </button>
            </div>
          </div>
          <strong>{handoffUrl}</strong>
          {attachSequence.length > 0 && (
            <div className="workbench-handoff-steps">
              {attachSequence.slice(0, 3).map((step, index) => (
                <small key={`${step}-${index}`}>{step}</small>
              ))}
            </div>
          )}
          {handoffPreview && (
            <div className="workbench-handoff-preview">
              <div>
                <span>Context</span>
                <strong>{handoffContextSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Skills</span>
                <strong>{handoffSkillSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Runtime</span>
                <strong>{handoffRuntimeSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Maker</span>
                <strong>{handoffMakerSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Guard</span>
                <strong>{handoffGuardSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Advice</span>
                <strong>{handoffAdviceSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>LLM</span>
                <strong>{handoffLlmSummary(handoffPreview)}</strong>
              </div>
              <div>
                <span>Learning</span>
                <strong>{handoffLearningSummary(handoffPreview)}</strong>
              </div>
              {handoffPreview.token_rule && <small>{handoffPreview.token_rule}</small>}
            </div>
          )}
        </div>
      )}
      {checklist.length > 0 && (
        <div className="workbench-maker-checklist">
          {checklist.slice(0, 6).map((item) => (
            <div
              key={item.id || item.label}
              className={`workbench-maker-step maker-step-${item.status || 'ready'}`}
            >
              <span>{makerStepStatusLabel(item.status)}</span>
              <strong>{item.label || item.id}</strong>
              <small>{item.evidence || item.action || ''}</small>
            </div>
          ))}
        </div>
      )}
      {templates.length > 0 && (
        <div className="workbench-maker-templates">
          {templates.slice(0, 5).map((item) => {
            const tools = (item.suggested_tools || []).filter(Boolean).slice(0, 3).join(' / ')
            const acceptance = (item.acceptance_criteria || []).filter(Boolean)[0]
            return (
              <div
                key={item.id || item.label}
                className={`workbench-maker-template maker-step-${item.status || 'ready'}`}
              >
                <span>{makerStepStatusLabel(item.status)}</span>
                <strong>{item.label || item.id}</strong>
                <small>{tools || acceptance || item.when || ''}</small>
              </div>
            )
          })}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="workbench-contract-warnings">
          {warnings.slice(0, 3).map((item, index) => (
            <span key={`${item}-${index}`}>{item}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function ContextSyncPanel({ state }: { state: AgentWorkbenchState }) {
  const sync = state.contextSync
  const snapshot = sync.snapshot || {}
  const plan = snapshot.plan_validation || {}
  const goal = snapshot.goal_checklist || {}
  const artifacts = Number(snapshot.artifact_count || 0)
  const diff = sync.diffKeys && sync.diffKeys.length > 0
    ? sync.diffKeys.join(' / ')
    : 'no diff'

  return (
    <div className={`workbench-context-sync ${sync.changed ? 'context-changed' : 'context-steady'}`}>
      <div className="workbench-context-head">
        <span>Context Sync</span>
        <strong>rev {sync.revision || 0}</strong>
        {sync.signature && <small>{sync.signature}</small>}
      </div>
      <div className="workbench-context-grid">
        <Metric label="Last" value={String(snapshot.last_tool || '-')} />
        <Metric label="Plan" value={String(plan.verdict || '-')} />
        <Metric label="Goal" value={String(goal.overall || '-')} />
        <Metric label="Artifacts" value={String(artifacts)} />
      </div>
      <small className="workbench-context-diff">{diff}</small>
    </div>
  )
}

function SkillSyncPanel({ state }: { state: AgentWorkbenchState }) {
  const sync = state.skillSync
  const graph = sync.graphSummary || {}
  const manifest = sync.manifestSummary || {}
  const plan = sync.exportPlanSummary || {}
  const conflictCount = Number(manifest.total_conflicts || sync.conflicts?.length || 0)
  const actionCount = Number(plan.total_actions || sync.actionsPreview?.length || 0)
  const skillCount = Number(graph.total_skills || manifest.total_skills || 0)
  const status = sync.compatibilityStatus === 'needs_review' || conflictCount > 0
    ? 'review'
    : sync.changed
      ? 'changed'
      : 'ok'

  return (
    <div className={`workbench-skill-sync skill-${status}`}>
      <div className="workbench-skill-head">
        <span>Skill Graph</span>
        <strong>{skillSyncLabel(status)}</strong>
      </div>
      <div className="workbench-skill-metrics">
        <Metric label="Skills" value={String(skillCount)} />
        <Metric label="Actions" value={String(actionCount)} />
        <Metric label="Conflicts" value={String(conflictCount)} />
      </div>
      {sync.conflicts && sync.conflicts.length > 0 && (
        <div className="workbench-skill-list">
          {sync.conflicts.slice(0, 2).map((item, index) => (
            <span key={`${item.skill_id || 'conflict'}-${index}`}>
              {item.type || 'conflict'}: {item.skill_id || 'unknown'}
            </span>
          ))}
        </div>
      )}
      {sync.actionsPreview && sync.actionsPreview.length > 0 && (
        <div className="workbench-skill-list">
          {sync.actionsPreview.slice(0, 2).map((item, index) => (
            <span key={`${item.skill_id || 'action'}-${index}`}>
              {item.action || 'sync'} {item.skill_id || 'skill'} {'->'} {item.target || 'target'}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="workbench-label">{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function formatMs(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

function toolRunDetail(run: AgentWorkbenchState['toolRuns'][number]): string {
  if (run.elapsedMs !== undefined) return formatMs(run.elapsedMs)
  if (run.status === 'running' && run.progressElapsedMs !== undefined) {
    const heartbeat = run.heartbeatCount ? ` #${run.heartbeatCount}` : ''
    return `${formatMs(run.progressElapsedMs)}${heartbeat}`
  }
  return toolStatusLabel(run.status)
}

function LayerPill({
  label,
  layer,
}: {
  label: string
  layer: AgentWorkbenchState['layers']['agent']
}) {
  const route = layer.sourceLayer && layer.targetLayer
    ? `${layer.sourceLayer} -> ${layer.targetLayer}`
    : ''
  const metrics = summarizeMetrics(layer.metrics)

  return (
    <div className={`workbench-layer layer-${layer.status}`}>
      <span>{label}</span>
      <strong>{layer.detail}</strong>
      {(route || layer.event) && (
        <small>{[route, layer.event].filter(Boolean).join(' / ')}</small>
      )}
      {metrics && <em>{metrics}</em>}
    </div>
  )
}

function summarizeMetrics(metrics?: Record<string, unknown>): string {
  if (!metrics) return ''
  const keys = [
    'iteration_count',
    'trajectory_steps',
    'health_status',
    'repair_status',
    'error_count',
    'token_usage_ratio',
    'context_window_ratio',
    'context_saturation',
    'compression_applied',
    'dropped_parts',
    'truncated_chars',
    'token_cache_hits',
    'token_cache_misses',
    'token_cache_size',
    'agents_md_hits',
    'cold_recall_hits',
    'agents_md_ms',
    'cold_recall_ms',
    'context_build_ms',
    'tool_phase',
    'tool_candidates',
    'tool_selected',
    'tool_ranking_ms',
    'tool_rank_cache_hit',
    'tool_rank_cache_size',
    'eligible',
    'context_revision',
    'context_diff_keys',
    'context_artifacts',
    'contract_tools',
    'contract_warnings',
    'contract_warning_codes',
    'maker_checklist_ready',
    'maker_checklist_warn',
    'maker_templates',
    'maker_templates_warn',
    'maker_goal_templates',
    'skill_total',
    'skill_conflicts',
    'skill_actions',
  ]
  return keys
    .filter((key) => metrics[key] !== undefined)
    .map((key) => `${metricLabel(key)}=${formatMetricValue(key, metrics[key])}`)
    .join('  ')
}

function formatMetricValue(key: string, value: unknown): string {
  if (
    (key === 'token_usage_ratio' || key === 'context_window_ratio')
    && typeof value === 'number'
  ) {
    return `${Math.round(value * 100)}%`
  }
  if (key.endsWith('_ms') && typeof value === 'number') {
    return formatMs(value)
  }
  return String(value)
}

function metricLabel(key: string): string {
  switch (key) {
    case 'iteration_count':
      return 'iter'
    case 'trajectory_steps':
      return 'steps'
    case 'health_status':
      return '健康'
    case 'repair_status':
      return '修复'
    case 'error_count':
      return '错误'
    case 'token_usage_ratio':
      return 'tokens'
    case 'context_window_ratio':
      return 'ctx'
    case 'context_saturation':
      return '上下文'
    case 'compression_applied':
      return 'zip'
    case 'dropped_parts':
      return 'drop'
    case 'truncated_chars':
      return 'trim'
    case 'token_cache_hits':
      return 'tok_hit'
    case 'token_cache_misses':
      return 'tok_miss'
    case 'token_cache_size':
      return 'tok_cache'
    case 'agents_md_hits':
      return 'agents'
    case 'cold_recall_hits':
      return 'recall'
    case 'agents_md_ms':
      return 'agents_ms'
    case 'cold_recall_ms':
      return 'recall_ms'
    case 'context_build_ms':
      return 'ctx_ms'
    case 'tool_phase':
      return '工具阶段'
    case 'tool_candidates':
      return '可选能力'
    case 'tool_selected':
      return '已选能力'
    case 'tool_ranking_ms':
      return '筛选耗时'
    case 'tool_rank_cache_hit':
      return '筛选缓存'
    case 'tool_rank_cache_size':
      return '缓存数'
    case 'eligible':
      return 'learn'
    case 'context_revision':
      return 'ctx_rev'
    case 'context_diff_keys':
      return 'ctx_diff'
    case 'context_artifacts':
      return 'artifacts'
    case 'contract_tools':
      return 'mcp_tools'
    case 'contract_warnings':
      return 'contract_warn'
    case 'contract_warning_codes':
      return 'warn_codes'
    case 'maker_checklist_ready':
      return 'maker_ok'
    case 'maker_checklist_warn':
      return 'maker_warn'
    case 'maker_templates':
      return 'flows'
    case 'maker_templates_warn':
      return 'flow_warn'
    case 'maker_goal_templates':
      return 'flow_goals'
    case 'skill_total':
      return 'skills'
    case 'skill_conflicts':
      return 'conflicts'
    case 'skill_actions':
      return 'actions'
    default:
      return key
  }
}

function stageLabel(stage: AgentWorkbenchState['stage']): string {
  switch (stage) {
    case 'idle':
      return '就绪'
    case 'running':
      return '运行中'
    case 'approval':
      return '待确认'
    case 'error':
      return '需要处理'
    case 'done':
      return '已完成'
    default:
      return stage
  }
}

function toolStatusLabel(status: 'running' | 'ok' | 'error'): string {
  switch (status) {
    case 'running':
      return '运行中'
    case 'ok':
      return '完成'
    case 'error':
      return '失败'
    default:
      return status
  }
}

function goalOverallLabel(overall?: AgentWorkbenchState['goalChecklist']['overall']): string {
  switch (overall) {
    case 'done':
      return '全部通过'
    case 'warn':
      return '需要复核'
    case 'fail':
      return '需要修复'
    default:
      return '进行中'
  }
}

function goalStatusLabel(status?: WorkbenchGoalCriterion['status']): string {
  switch (status) {
    case 'done':
      return 'ok'
    case 'warn':
      return '!'
    case 'fail':
      return 'x'
    default:
      return '-'
  }
}

function goalMeta(item: WorkbenchGoalCriterion): string {
  const parts = []
  if (item.source === 'maker_template') {
    parts.push(item.template_id || 'maker_template')
  }
  if (item.evidence && item.evidence.length > 0) {
    parts.push(item.evidence.slice(0, 2).join(' / '))
  } else if (item.next_check) {
    parts.push(item.next_check)
  }
  return parts.join(' | ')
}

function runtimeAdviceSummary(advice?: RuntimeAdvicePreview | null): string {
  if (!advice) return 'waiting for evidence'
  return [
    `status=${advice.status || '-'}`,
    `priority=${advice.priority || '-'}`,
  ].filter(Boolean).join(' | ')
}

function runtimeAdviceEvidenceSummary(evidence: Record<string, unknown>): string {
  const rows = Object.entries(evidence).slice(0, 4).map(([key, value]) => {
    if (!value || typeof value !== 'object') return key
    const item = value as Record<string, unknown>
    const detail = [
      typeof item.decision === 'string' ? `decision=${item.decision}` : '',
      typeof item.provider === 'string' ? `provider=${item.provider}` : '',
      typeof item.endpoint === 'string' ? `endpoint=${item.endpoint}` : '',
      typeof item.elapsed_ms === 'number' ? `elapsed=${formatMs(item.elapsed_ms)}` : '',
      typeof item.revision === 'number' ? `rev=${item.revision}` : '',
      typeof item.state === 'string' ? `state=${item.state}` : '',
    ].filter(Boolean).join(',')
    return detail ? `${key}(${detail})` : key
  })
  return rows.length > 0 ? rows.join(' | ') : 'evidence=none'
}

function projectControlClass(control?: ProjectControlPreview | null): string {
  const status = control?.status || 'instrumented'
  const layerStatus = control?.layer_control?.status
  const engineeringStatus = control?.engineering_control?.status
  if (engineeringStatus === 'blocked') return 'blocked'
  if (layerStatus === 'blocked') return 'blocked'
  if (engineeringStatus === 'needs_action') return 'action'
  if (layerStatus === 'needs_action') return 'action'
  if (engineeringStatus === 'watch' && status === 'ready') return 'instrumented'
  if (layerStatus === 'watch' && status === 'ready') return 'instrumented'
  if (status === 'blocked') return 'blocked'
  if (status === 'needs_confirmation') return 'confirm'
  if (status === 'needs_action') return 'action'
  if (status === 'ready') return 'ready'
  return 'instrumented'
}

function projectControlStatusLabel(status?: string): string {
  switch (status) {
    case 'ready':
      return '就绪'
    case 'needs_confirmation':
      return '待确认'
    case 'needs_action':
      return '需处理'
    case 'blocked':
      return '阻断'
    case 'instrumented':
      return '已观测'
    default:
      return status || '-'
  }
}

function projectControlSummary(control?: ProjectControlPreview | null): string {
  if (!control) return 'waiting for project control evidence'
  const classification = control.classification || {}
  return [
    `status=${control.status || '-'}`,
    classification.level ? `level=${classification.level}` : '',
    classification.mode ? `mode=${classification.mode}` : '',
    control.current_focus ? `focus=${control.current_focus}` : '',
  ].filter(Boolean).join(' | ')
}

function projectControlGateSummary(control?: ProjectControlPreview | null): string {
  if (!control) return '-'
  const required = control.required_gates?.length ?? 0
  const completed = control.completed_gates?.length ?? 0
  const pending = control.pending_gates || []
  if (pending.length > 0) {
    return `${pending[0]}${pending.length > 1 ? ` +${pending.length - 1}` : ''}`
  }
  if (required > 0) return `${completed}/${required}`
  return '-'
}

function projectControlBlockerSummary(control?: ProjectControlPreview | null): string {
  const blockers = control?.blockers || []
  if (blockers.length === 0) return ''
  return blockers.slice(0, 2).map((blocker) => (
    `${blocker.severity || 'warn'}:${blocker.id || blocker.detail || 'blocker'}`
  )).join(' | ')
}

function projectControlMemoryDue(control?: ProjectControlPreview | null): string {
  const due = control?.memory_updates_due || []
  if (due.length === 0) return ''
  return `POST ${due
    .map((item) => [item.gate, item.file].filter(Boolean).join('='))
    .filter(Boolean)
    .join(' | ')}`
}

function projectControlLayerSummary(control?: ProjectControlPreview | null): string {
  const layer = control?.layer_control
  if (!layer || layer.status === 'missing') return ''
  const claim = layer.can_claim_layer_independence === undefined
    ? 'claim=-'
    : layer.can_claim_layer_independence
      ? 'claim=ready'
      : 'claim=hold'
  return [
    `status=${layer.status || '-'}`,
    `decision=${layer.decision || '-'}`,
    `signals=${layer.signal_count ?? '-'}`,
    claim,
  ].join(' | ')
}

function projectControlEngineeringSummary(control?: ProjectControlPreview | null): string {
  const engineering = control?.engineering_control
  if (!engineering || engineering.status === 'missing') return ''
  const claim = engineering.can_claim_engineering_control_ready === undefined
    ? 'claim=-'
    : engineering.can_claim_engineering_control_ready
      ? 'claim=ready'
      : 'claim=hold'
  return [
    `status=${engineering.status || '-'}`,
    `decision=${engineering.decision || '-'}`,
    `signals=${engineering.signal_count ?? '-'}`,
    `mem_hits=${engineering.memory_total_hits ?? '-'}`,
    `tool_fail=${engineering.tool_failure_count ?? '-'}`,
    `plan=${engineering.plan_verdict || '-'}`,
    claim,
  ].join(' | ')
}

function projectControlActionSummary(control?: ProjectControlPreview | null): string {
  const action = (
    (control?.control_actions || [])[0]
    || control?.engineering_control?.top_action
    || control?.layer_control?.top_action
  )
  if (!action || !action.id) return ''
  return [
    `control=${action.source || action.domain || action.owner_layer || '-'}`,
    action.id,
    action.reason ? `reason=${action.reason}` : '',
  ].filter(Boolean).join(' | ')
}

function projectWritebackSummary(preview?: ProjectWritebackPreview | null, fallbackEndpoint = ''): string {
  if (!preview) return 'waiting for writeback evidence'
  const files = preview.files?.length ? preview.files.join(',') : 'files=-'
  return [
    `status=${preview.status || '-'}`,
    preview.applicable ? 'apply=ready' : 'apply=hold',
    `ops=${preview.operation_count ?? '-'}`,
    files,
    preview.invalid_target_count ? `invalid=${preview.invalid_target_count}` : '',
    preview.endpoint || fallbackEndpoint ? `endpoint=${preview.endpoint || fallbackEndpoint}` : '',
    preview.reason ? `reason=${preview.reason}` : '',
  ].filter(Boolean).join(' | ')
}

function runtimeMetricsSummary(summary?: RuntimeMetricsSummary): string {
  if (!summary) return '等待指标'
  const latency = summary.max_latency || {}
  const retrieval = summary.retrieval || {}
  return [
    latency.phase ? `${latency.phase}=${formatMs(latency.elapsed_ms)}` : '延迟=-',
    summary.llm_total_tokens !== undefined ? `tokens=${summary.llm_total_tokens}` : 'tokens=-',
    `ctx=${formatMs(retrieval.context_build_ms)}`,
    runtimeTokenCacheSummary(summary),
    runtimeRankingSummary(summary),
  ].filter(Boolean).join(' | ')
}

function runtimeTokenCacheSummary(summary?: RuntimeMetricsSummary): string {
  const cache = summary?.token_cache || {}
  const hits = cache.hits ?? '-'
  const misses = cache.misses ?? '-'
  const size = cache.size ?? '-'
  return `${hits}/${misses}/${size}`
}

function runtimeRankingSummary(summary?: RuntimeMetricsSummary): string {
  const ranking = summary?.tool_ranking || {}
  const selected = ranking.selected_count ?? '-'
  const hit = ranking.cache_hit === undefined ? '-' : ranking.cache_hit ? '命中' : '未命中'
  return `启用 ${selected} / 缓存 ${hit}`
}

function runtimeLatestMetricSummary(metric: RuntimeMetricLatest): string {
  return [
    `最新=${metric.kind || '-'}`,
    metric.phase ? `阶段=${metric.phase}` : '',
    typeof metric.iteration === 'number' ? `轮次=${metric.iteration + 1}` : '',
    typeof metric.elapsed_ms === 'number' ? `耗时=${formatMs(metric.elapsed_ms)}` : '',
    typeof metric.total_tokens === 'number' ? `tokens=${metric.total_tokens}` : '',
    typeof metric.token_count === 'number' ? `ctx_tokens=${metric.token_count}` : '',
    typeof metric.context_build_ms === 'number' ? `ctx=${formatMs(metric.context_build_ms)}` : '',
    typeof metric.selected_count === 'number' ? `启用=${metric.selected_count}` : '',
    metric.cache_hit !== undefined ? `缓存=${metric.cache_hit ? '命中' : '未命中'}` : '',
  ].filter(Boolean).join(' | ')
}

function ragBenchmarkClass(
  preview?: RagBenchmarkPreview | null,
  state: 'idle' | 'loading' | 'error' = 'idle',
): string {
  if (state === 'loading') return 'loading'
  if (state === 'error') return 'error'
  if (!preview || preview.status === 'not_run') return 'not-run'
  if (preview.status === 'ready' && preview.budget_status === 'pass') return 'pass'
  if (preview.status === 'ready' && preview.budget_status !== 'pass') return 'warn'
  return preview.status || 'unknown'
}

function ragBenchmarkSummary(
  preview?: RagBenchmarkPreview | null,
  state: 'idle' | 'loading' | 'error' = 'idle',
): string {
  if (state === 'loading') return 'running deterministic local benchmark'
  if (state === 'error') return 'benchmark endpoint unavailable'
  if (!preview) return 'waiting for benchmark evidence'
  const metrics = preview.metrics || {}
  return [
    `status=${preview.status || '-'}`,
    `budget=${preview.budget_status || '-'}`,
    `quality=${preview.embedding_quality?.status || 'unproven'}`,
    `p95=${formatMs(metrics.warm_recall_p95_ms)}`,
    `first=${formatMs(metrics.first_recall_ms)}`,
  ].join(' | ')
}

function ragBenchmarkRecordCount(preview?: RagBenchmarkPreview | null): number | string {
  return preview?.record_count
    ?? preview?.config?.record_count
    ?? preview?.metrics?.index_size
    ?? '-'
}

function ragBenchmarkDetailLine(preview: RagBenchmarkPreview | null | undefined, fallbackEndpoint: string): string {
  if (!preview) return `endpoint=${fallbackEndpoint}`
  const metrics = preview.metrics || {}
  const parts = [
    `endpoint=${preview.endpoint || fallbackEndpoint}`,
    preview.cache ? `cache=${preview.cache}` : '',
    preview.no_network_call === true ? 'no_network=true' : '',
    preview.embedding_quality?.status ? `quality=${preview.embedding_quality.status}` : '',
    typeof metrics.build_ms === 'number' ? `build=${formatMs(metrics.build_ms)}` : '',
    typeof metrics.cold_start_ms === 'number' ? `cold=${formatMs(metrics.cold_start_ms)}` : '',
    typeof metrics.profile_hit_rate === 'number' ? `profile_hit=${metrics.profile_hit_rate}` : '',
    typeof metrics.fallback_hit_rate === 'number' ? `fallback_hit=${metrics.fallback_hit_rate}` : '',
  ]
  return parts.filter(Boolean).join(' | ')
}

function learningJobFromLayerHealth(
  layerHealth?: EvidenceBundlePreview['layer_health'],
): LearningJobPreview | null {
  const learning = layerHealth?.layers?.learning
  if (!learning) return null
  const status = learning.job_status || learning.status || learning.state
  if (!status && !learning.event && !learning.health) return null
  return {
    ...learning,
    status: status || 'missing',
    source: learning.source || 'layer_health',
  }
}

function learningStatusClass(preview?: LearningPreview | null, fallback = ''): string {
  const raw = preview?.job?.status || preview?.latest?.state || fallback || 'idle'
  return String(raw).toLowerCase().replace(/[^a-z0-9_-]+/g, '-') || 'idle'
}

function learningJobSummary(
  job?: LearningJobPreview | null,
  fallbackPolicy?: LearningJobPolicyPreview,
): string {
  if (!job) return 'job=missing'
  const policy = job.policy || fallbackPolicy || {}
  const attempts = job.attempts ?? '-'
  const maxAttempts = job.max_attempts ?? policy.max_attempts ?? '-'
  const shared = job.shared_memory?.counts
  return [
    `job=${job.status || job.job_status || '-'}`,
    `attempts=${attempts}/${maxAttempts}`,
    `retryable=${learningBoolLabel(job.retryable)}`,
    `cancel=${job.cancel_requested ? 'requested' : 'no'}`,
    job.elapsed_ms !== undefined ? `elapsed=${formatMs(job.elapsed_ms)}` : '',
    job.insight_count !== undefined ? `insights=${job.insight_count}` : '',
    shared ? `shared=${shared.archived ?? 0}/${shared.promoted ?? 0}/${shared.conflicts ?? 0}` : '',
    policy.mode ? `mode=${policy.mode}` : '',
    policy.source ? `source=${policy.source}` : '',
  ].filter(Boolean).join(' | ')
}

function learningCanCancel(job?: LearningJobPreview | null): boolean {
  const status = learningJobStatus(job)
  return learningLiveQueueAvailable(job)
    && !job?.cancel_requested
    && (status === 'queued' || status === 'running')
}

function learningCanRetry(job?: LearningJobPreview | null): boolean {
  const status = learningJobStatus(job)
  return learningLiveQueueAvailable(job)
    && (status === 'error' || status === 'cancelled' || status === 'canceled')
    && job?.retryable !== false
}

function learningControlBoundary(job?: LearningJobPreview | null): string {
  if (!job) return ''
  const status = learningJobStatus(job)
  if (isDurableReplayLearningJob(job) && (status === 'queued' || status === 'running' || job.retryable)) {
    return 'live queue unavailable: durable replay cannot be controlled'
  }
  if (job.cancel_requested && status === 'running') {
    return 'cancel requested: running jobs stop at learning step boundaries'
  }
  if (job.error) return `error=${job.error}`
  return ''
}

function learningControlIdleSummary(job?: LearningJobPreview | null): string {
  if (!job) return ''
  if (learningCanCancel(job) || learningCanRetry(job)) return 'live queue control ready'
  const reason = job.reason ? `reason=${job.reason}` : ''
  return reason || `control=${learningLiveQueueAvailable(job) ? 'idle' : 'unavailable'}`
}

function learningControlResultSummary(kind: 'cancel' | 'retry', job?: LearningJobPreview | null): string {
  return [
    `${kind}=accepted`,
    `job=${job?.status || '-'}`,
    job?.reason ? `reason=${job.reason}` : '',
  ].filter(Boolean).join(' | ')
}

function learningJobStatus(job?: LearningJobPreview | null): string {
  return String(job?.status || job?.job_status || job?.state || '').toLowerCase()
}

function learningLiveQueueAvailable(job?: LearningJobPreview | null): boolean {
  if (!job || learningJobStatus(job) === 'missing') return false
  return !isDurableReplayLearningJob(job)
}

function isDurableReplayLearningJob(job?: LearningJobPreview | null): boolean {
  const source = String(job?.source || job?.policy?.source || '')
  return source.includes('session_store_learning_history') || source.includes('durable_event_replay')
}

function learningBoolLabel(value: boolean | undefined): string {
  if (value === undefined) return '-'
  return value ? 'yes' : 'no'
}

function learningStatusSummary(preview?: LearningPreview | null, fallback = ''): string {
  const latest = preview?.latest
  const job = preview?.job
  if (!latest && job) {
    return [
      `job=${job.status || job.job_status || '-'}`,
      preview?.count !== undefined ? `events=${preview.count}` : '',
    ].filter(Boolean).join(' | ')
  }
  if (!latest) return preview?.count ? `events=${preview.count}` : fallback || 'waiting for learning event'
  return [
    latest.event || latest.state || 'learning',
    latest.state ? `state=${latest.state}` : '',
    job?.status ? `job=${job.status}` : '',
    preview?.count !== undefined ? `events=${preview.count}` : '',
  ].filter(Boolean).join(' | ')
}

function learningMetricsSummary(metrics: Record<string, number | string | boolean>): string {
  const keys = [
    'async',
    'elapsed_ms',
    'trajectory_steps',
    'skill_count',
    'generated_skills',
    'knowledge_items',
    'error_count',
  ]
  return keys
    .filter((key) => metrics[key] !== undefined)
    .map((key) => `${metricLabel(key)}=${formatMetricValue(key, metrics[key])}`)
    .join(' | ') || 'metrics=none'
}

function externalAgentBootSummary({
  onboardingUrl,
  readinessUrl,
  quickstartUrl,
  evidenceUrl,
  handoffUrl,
  adviceUrl,
  metricsUrl,
  learningUrl,
}: {
  onboardingUrl: string
  readinessUrl: string
  quickstartUrl: string
  evidenceUrl: string
  handoffUrl: string
  adviceUrl: string
  metricsUrl: string
  learningUrl: string
}): string {
  const ready = [
    onboardingUrl ? 'onboarding' : '',
    readinessUrl ? 'readiness' : '',
    quickstartUrl ? 'quickstart' : '',
    evidenceUrl ? 'evidence' : '',
    handoffUrl ? 'handoff' : '',
    adviceUrl ? 'advice' : '',
    metricsUrl ? 'metrics' : '',
    learningUrl ? 'learning' : '',
  ].filter(Boolean)
  return ready.length > 0 ? `ready=${ready.join('/')}` : 'waiting for session'
}

function evidenceBundleSummary(
  preview?: EvidenceBundlePreview | null,
  state: 'idle' | 'loading' | 'error' = 'idle',
): string {
  if (state === 'loading') return '正在刷新证据包'
  if (state === 'error') return '证据包暂不可用，请刷新详情'
  if (!preview) return '等待证据包'
  const counts = preview.counts || {}
  const advice = preview.runtime_advice?.priority || preview.runtime_advice?.status || '-'
  const maker = preview.maker_mcp
    ? `maker=${preview.maker_mcp.readiness || '-'}:${preview.maker_mcp.tool_count ?? 0}`
    : 'maker=-'
  const setup = preview.maker_setup
    ? `setup=${preview.maker_setup.readiness || '-'}:${preview.maker_setup.blockers?.length ?? 0}`
    : 'setup=-'
  const audit = preview.maker_tool_audit
    ? `audit=${preview.maker_tool_audit.ok ? 'ok' : 'review'}:${preview.maker_tool_audit.remote_tool_count ?? 0}`
    : 'audit=-'
  const context = preview.latest_context_sync?.revision !== undefined
    ? `ctx=rev ${preview.latest_context_sync.revision}`
    : `ctx=${counts.context_sync ?? 0}`
  const resume = preview.resume_drill
    ? `resume=${preview.resume_drill.status || '-'}:${preview.resume_drill.capability_levels?.durable_handoff?.status || '-'}`
    : 'resume=-'
  const metrics = `metrics=${counts.runtime_metrics ?? 0}`
  const learning = preview.learning_latest?.state || preview.learning_latest?.event || `learning=${counts.learning ?? 0}`
  const layerLatest = preview.layer_summary?.latest_by_layer || {}
  const layerState = layerLatest.runtime?.state || layerLatest.agent?.state || layerLatest.learning?.state
  const layers = `layers=${preview.layer_summary?.event_count ?? counts.layer ?? 0}${layerState ? `/${layerState}` : ''}`
  const guard = preview.maker_guard_latest?.decision || `guard=${counts.maker_guard ?? 0}`
  const probe = preview.llm_probe_latest?.status || `probe=${counts.llm_probe ?? 0}`
  const proof = preview.llm_call_proof
    ? `api=${preview.llm_call_proof.conclusion || '-'}:${preview.llm_call_proof.evidence_source || '-'}`
    : 'api=-'
  const feedbackLatest = preview.llm_feedback_summary?.latest_run
  const feedback = preview.llm_feedback_summary
    ? `feedback=${preview.llm_feedback_summary.total_runs ?? 0}/${feedbackLatest?.failure_type || (feedbackLatest?.ok ? 'ok' : '-')}`
    : 'feedback=-'
  return [`advice=${advice}`, maker, setup, audit, context, resume, layers, metrics, learning, guard, probe, proof, feedback].filter(Boolean).join(' | ')
}

function userFacingWorkbenchStatus(value?: string): string {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/tool[_\s-]?selection|candidate|候选工具|可选工具|工具筛选|Tool context ranked/i.test(text)) {
    return '正在判断下一步'
  }
  if (text === 'Session created') return '会话已创建，正在等待模型响应'
  if (text === 'Task finished') return '任务已完成'
  if (text === 'Canceling task') return '正在停止任务'
  if (text === 'Runtime contract degraded') return '运行契约部分可用，正在继续处理'
  return text
}

function externalAgentBootLines({
  quickstartMarkdownUrl,
  quickstartUrl,
  onboardingMarkdownUrl,
  onboardingUrl,
  evidenceMarkdownUrl,
  readinessUrl,
  evidenceUrl,
  handoffUrl,
  adviceUrl,
  metricsUrl,
  learningUrl,
  communication,
  quickstartSurface,
}: {
  quickstartMarkdownUrl: string
  quickstartUrl: string
  onboardingMarkdownUrl: string
  onboardingUrl: string
  evidenceMarkdownUrl: string
  readinessUrl: string
  evidenceUrl: string
  handoffUrl: string
  adviceUrl: string
  metricsUrl: string
  learningUrl: string
  communication: Record<string, string>
  quickstartSurface: QuickstartSurface
}): string[] {
  const lines = [
    `surface=${quickstartSurface}`,
    onboardingMarkdownUrl ? `1. Read Onboarding MD: ${onboardingMarkdownUrl}` : onboardingUrl ? `1. Read Onboarding JSON: ${onboardingUrl}` : '',
    readinessUrl ? `2. Check Runtime Readiness: ${readinessUrl}` : '',
    quickstartMarkdownUrl ? `3. Read Quickstart MD: ${quickstartMarkdownUrl}` : quickstartUrl ? `3. Read Quickstart JSON: ${quickstartUrl}` : '',
    evidenceMarkdownUrl ? `4. Read Evidence MD: ${evidenceMarkdownUrl}` : evidenceUrl ? `4. Pull Evidence Bundle: ${evidenceUrl}` : '',
    handoffUrl ? `5. Pull Handoff Bundle only if evidence is insufficient: ${handoffUrl}` : '',
    adviceUrl ? `6. Check Runtime Advice: ${adviceUrl}` : '',
    communication.maker_briefing ? `7. Use Maker Briefing: ${API_BASE}${communication.maker_briefing}` : '',
    communication.maker_guard ? `8. Verify Maker Guard: ${API_BASE}${communication.maker_guard}` : '',
    metricsUrl ? `9. Inspect Runtime Metrics: ${metricsUrl}` : '',
    learningUrl ? `10. 查看学习状态: ${learningUrl}` : '',
    communication.context_sync ? `11. Pull Context Sync: ${API_BASE}${communication.context_sync}` : '',
    communication.resume_drill ? `12. Check Resume Drill: ${API_BASE}${communication.resume_drill}` : '',
    communication.project_writeback ? `13. Plan Project Writeback: ${API_BASE}${communication.project_writeback}` : '',
    communication.llm_probe_history ? `14. Check LLM Probe History: ${API_BASE}${communication.llm_probe_history}` : '',
    communication.llm_feedback_summary ? `15. Read LLM Feedback Summary: ${API_BASE}${communication.llm_feedback_summary}` : '',
    communication.maker_setup_status ? `16. Check Maker Setup Doctor: ${API_BASE}${communication.maker_setup_status}` : '',
    communication.maker_tool_audit ? `17. Audit Maker Tools: ${API_BASE}${communication.maker_tool_audit}` : '',
  ]
  return lines.filter(Boolean)
}

function handoffContextSummary(preview: HandoffPreview): string {
  const latest = preview.latest_context_sync || {}
  const snapshot = latest.snapshot || {}
  const revision = latest.revision !== undefined ? `rev ${latest.revision}` : 'no rev'
  const task = snapshot.task ? String(snapshot.task) : 'no task'
  const lastTool = latest.last_tool || snapshot.last_tool || '-'
  const plan = latest.plan_verdict || snapshot.plan_validation?.verdict || '-'
  const goal = latest.goal_overall || snapshot.goal_checklist?.overall || '-'
  const artifacts = latest.artifact_count ?? snapshot.artifact_count ?? 0
  return `${revision} | ${task} | tool=${lastTool} | plan=${plan} | goal=${goal} | artifacts=${artifacts}`
}

function handoffSkillSummary(preview: HandoffPreview): string {
  const summary = preview.skill_summary || {}
  const registry = summary.registry?.state || '-'
  const graph = summary.graph_summary || {}
  const manifest = summary.manifest_summary || {}
  const skills = graph.total_skills ?? manifest.total_skills ?? '-'
  const conflicts = manifest.total_conflicts ?? graph.total_conflicts ?? 0
  return `registry=${registry} | skills=${skills} | conflicts=${conflicts}`
}

function handoffRuntimeSummary(preview: HandoffPreview): string {
  return runtimeMetricsSummary(preview.runtime_metrics_summary)
}

function handoffMakerSummary(preview: HandoffPreview): string {
  const briefing = preview.maker_briefing || {}
  const template = briefing.selected_template || {}
  const tools = (briefing.suggested_tools || []).filter(Boolean).slice(0, 2).join('/')
  return [
    `ready=${briefing.readiness || '-'}`,
    `auth=${briefing.authority || '-'}`,
    `flow=${template.id || '-'}`,
    tools ? `tools=${tools}` : '',
  ].filter(Boolean).join(' | ')
}

function handoffGuardSummary(preview: HandoffPreview): string {
  const guard = preview.maker_guard_latest
  if (!guard) return 'no guard decision'
  const template = guard.selected_template || {}
  const tools = (guard.suggested_tools && guard.suggested_tools.length > 0
    ? guard.suggested_tools
    : guard.allowed_tools || []
  ).filter(Boolean).slice(0, 2).join('/')
  return [
    `decision=${guard.decision || '-'}`,
    `tool=${guard.tool || '-'}`,
    `auth=${guard.authority || '-'}`,
    template.id ? `flow=${template.id}` : '',
    tools ? `tools=${tools}` : '',
    guard.reason ? `reason=${guard.reason}` : '',
  ].filter(Boolean).join(' | ')
}

function handoffAdviceSummary(preview: HandoffPreview): string {
  const advice = preview.runtime_advice || {}
  const reasons = (advice.reasons || []).filter(Boolean).slice(0, 1).join(' / ')
  return [
    `status=${advice.status || '-'}`,
    `priority=${advice.priority || '-'}`,
    advice.next_action ? `next=${advice.next_action}` : '',
    reasons ? `why=${reasons}` : '',
  ].filter(Boolean).join(' | ')
}

function quickstartAdviceSummary(preview: QuickstartPreview): string {
  const advice = preview.runtime_advice || {}
  const reasons = (advice.reasons || []).filter(Boolean).slice(0, 1).join(' / ')
  return [
    `status=${advice.status || '-'}`,
    `priority=${advice.priority || '-'}`,
    advice.next_action ? `next=${advice.next_action}` : '',
    reasons ? `why=${reasons}` : '',
  ].filter(Boolean).join(' | ')
}

function quickstartMakerSummary(preview: QuickstartPreview): string {
  const maker = preview.maker || {}
  const briefing = preview.maker_briefing || {}
  const template = briefing.selected_template || {}
  const tools = (briefing.suggested_tools || []).filter(Boolean).slice(0, 2).join('/')
  return [
    `ready=${maker.readiness || '-'}`,
    `auth=${briefing.authority || '-'}`,
    `flow=${template.id || '-'}`,
    tools ? `tools=${tools}` : '',
  ].filter(Boolean).join(' | ')
}

function quickstartSurfaceSummary(preview: QuickstartPreview): string {
  const surface = preview.surface || {}
  const memory = (surface.memory_files || []).filter(Boolean).slice(0, 2).join('/')
  return [
    `surface=${surface.id || '-'}`,
    surface.label ? `label=${surface.label}` : '',
    memory ? `memory=${memory}` : '',
    surface.start_rule ? `start=${surface.start_rule}` : '',
  ].filter(Boolean).join(' | ')
}

function quickstartLlmSummary(preview: QuickstartPreview): string {
  return llmProbeSummary(preview.llm_probe)
}

function handoffLlmSummary(preview: HandoffPreview): string {
  return llmProbeSummary(preview.llm_probe_latest)
}

function llmProbeSummary(probe?: {
  status?: string
  ok?: boolean | null
  provider?: string
  runtime_kind?: string
  llm_class?: string
  model?: string
  endpoint?: string
  base_url?: string
  elapsed_ms?: number
  total_tokens?: number
  error_type?: string
  error?: string
}): string {
  if (!probe) return 'probe=not_run | next=POST /llm/probe'
  const target = probe.endpoint || probe.base_url || ''
  return [
    `probe=${probe.status || (probe.ok ? 'ok' : 'not_run')}`,
    probe.provider ? `provider=${probe.provider}` : '',
    probe.model ? `model=${probe.model}` : '',
    target ? `endpoint=${target}` : '',
    typeof probe.elapsed_ms === 'number' ? `elapsed=${formatMs(probe.elapsed_ms)}` : '',
    typeof probe.total_tokens === 'number' ? `tokens=${probe.total_tokens}` : '',
    probe.error_type ? `error_type=${probe.error_type}` : '',
    probe.error ? `error=${probe.error}` : '',
  ].filter(Boolean).join(' | ')
}

function withQueryParam(path: string, key: string, value: string): string {
  if (!path) return path
  const [base, query = ''] = path.split('?')
  const params = new URLSearchParams(query)
  params.set(key, value)
  const queryText = params.toString()
  return queryText ? `${base}?${queryText}` : base
}

function handoffLearningSummary(preview: HandoffPreview): string {
  const latest = preview.learning_latest
  if (!latest) return 'no learning event'
  const metrics = latest.metrics || {}
  const asyncText = metrics.async !== undefined ? `async=${metrics.async}` : ''
  const elapsed = typeof metrics.elapsed_ms === 'number' ? `elapsed=${formatMs(metrics.elapsed_ms)}` : ''
  return [latest.event || latest.state || 'learning', latest.detail || '', asyncText, elapsed]
    .filter(Boolean)
    .join(' | ')
}

function makerGuardLabel(decision: string): string {
  switch (decision) {
    case 'pass':
      return 'Aligned'
    case 'warn':
      return 'Check'
    case 'block':
      return 'Blocked'
    default:
      return decision || 'Guard'
  }
}

function planValidationLabel(verdict: NonNullable<AgentWorkbenchState['planValidation']['verdict']>): string {
  switch (verdict) {
    case 'pass':
      return 'Validation passed'
    case 'warn':
      return 'Needs review'
    case 'fail':
      return 'Validation failed'
    default:
      return verdict
  }
}

function runtimeContractLabel(readiness: string): string {
  switch (readiness) {
    case 'ready':
      return 'Maker-ready'
    case 'disconnected':
      return 'Disconnected'
    case 'degraded':
      return 'Degraded'
    default:
      return readiness || 'Unknown'
  }
}

function makerStepStatusLabel(status?: string): string {
  switch (status) {
    case 'ready':
      return 'ok'
    case 'warn':
      return '!'
    case 'blocked':
      return 'x'
    default:
      return '-'
  }
}

function skillSyncLabel(status: 'ok' | 'changed' | 'review'): string {
  switch (status) {
    case 'review':
      return 'Needs review'
    case 'changed':
      return 'Updated'
    default:
      return 'Aligned'
  }
}

function commitLabel(committed?: boolean | null): string {
  if (committed === true) return 'Committed'
  if (committed === false) return 'Not committed'
  if (committed === null) return 'Unknown'
  return 'No write'
}

function commitClass(committed?: boolean | null): string {
  if (committed === true) return 'ok'
  if (committed === false) return 'no'
  if (committed === null) return 'unknown'
  return 'none'
}

function commitDetail(commit: AgentWorkbenchState['commitState']): string {
  const parts = []
  if (commit.reconcileStatus) parts.push(commit.reconcileStatus)
  if (commit.remoteLookupTool) parts.push(`via ${commit.remoteLookupTool}`)
  if (commit.remoteLookupAttempts !== undefined) parts.push(`${commit.remoteLookupAttempts} lookup`)
  return parts.join(' / ')
}
