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

interface LearningPreview {
  count?: number
  latest?: LearningEventPreview | null
}

interface EvidenceBundlePreview {
  version?: string
  session_id?: string
  task?: string
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
  layer_summary?: {
    event_count?: number
    latest_by_layer?: Record<string, {
      state?: string
      event?: string
      source_layer?: string
      target_layer?: string
    }>
  }
  runtime_metrics_summary?: RuntimeMetricsSummary
  learning_latest?: LearningEventPreview | null
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
        <LayerPill label="Runtime" layer={state.layers.runtime} />
        <LayerPill label="Learning" layer={state.layers.learning} />
      </div>

      <div className="workbench-topline">
        <div>
          <span className="workbench-label">Status</span>
          <strong>{stageLabel(state.stage)}</strong>
        </div>
        <div>
          <span className="workbench-label">Turn</span>
          <strong>{state.iteration === null ? '-' : state.iteration + 1}</strong>
        </div>
        <div>
          <span className="workbench-label">Tools</span>
          <strong>{activeTools}/{completedTools + failedTools}</strong>
        </div>
      </div>

      <div className="workbench-latency">
        <Metric label="First" value={formatMs(state.latency.firstResponseMs)} />
        <Metric label="LLM" value={formatMs(state.latency.lastLlmMs)} />
        <Metric label="Tool" value={formatMs(state.latency.lastToolMs)} />
        <Metric label="Total" value={formatMs(state.latency.totalMs)} />
      </div>

      <div className="workbench-current">
        <span>{state.currentStatus || 'Waiting for task'}</span>
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
            <span>Acceptance</span>
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
        <span>Maker First Action</span>
        <strong>{briefing.authority || '-'}</strong>
        {template.id && <small>{template.id}</small>}
      </div>
      {briefing.recommendedFirstAction && (
        <div className="workbench-maker-briefing-action">
          <span>Next</span>
          <strong>{briefing.recommendedFirstAction}</strong>
        </div>
      )}
      <div className="workbench-maker-briefing-grid">
        <Metric label="Ready" value={briefing.readiness || '-'} />
        <Metric label="Template" value={template.status || '-'} />
        <Metric label="Tools" value={String(tools.length)} />
        <Metric label="Warnings" value={String(warnings.length)} />
      </div>
      {tools.length > 0 && (
        <div className="workbench-maker-briefing-line">
          <span>Tools</span>
          <strong>{tools.join(' / ')}</strong>
        </div>
      )}
      {(briefing.recommendedEndpoint || endpointText) && (
        <div className="workbench-maker-briefing-line">
          <span>Evidence</span>
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
        <span>First Action Guard</span>
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
          <span>Endpoint</span>
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
  const learningPath = communication.learning_status || (
    state.sessionId
      ? `/sessions/${state.sessionId}/learning?steps=20`
      : ''
  )
  const learningUrl = learningPath ? `${API_BASE}${learningPath}` : ''
  const tokenRules = contract.tokenEfficiency?.rules || []
  const status = readiness === 'ready'
    ? 'ready'
    : readiness === 'disconnected'
      ? 'offline'
      : 'degraded'

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
    setEvidencePreview(null)
    setEvidencePreviewState('idle')
    setEvidenceCopyState('idle')
  }, [state.sessionId])

  const applyEvidenceBundle = useCallback((data: EvidenceBundlePreview) => {
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
    })
    setLearningPreviewState('idle')
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
      })
      setLearningPreviewState('idle')
    } catch {
      setLearningPreviewState('error')
    }
  }, [learningUrl])

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

  return (
    <div className={`workbench-runtime-contract contract-${status}`}>
      <div className="workbench-contract-head">
        <span>Runtime Contract</span>
        <strong>{runtimeContractLabel(readiness)}</strong>
        {contract.version && <small>{contract.version}</small>}
      </div>
      <div className="workbench-contract-grid">
        <Metric label="MakerMCP" value={String(readiness)} />
        <Metric label="Tools" value={String(maker.tool_count || 0)} />
        <Metric label="Identity" value={String(remote.status || '-')} />
        <Metric label="Rules" value={String(tokenRules.length)} />
      </div>
      {topTools.length > 0 && (
        <div className="workbench-contract-line">
          <span>Maker tools</span>
          <strong>{topTools.map((tool) => tool.name).filter(Boolean).slice(0, 4).join(' / ')}</strong>
        </div>
      )}
      {(onboardingUrl || readinessUrl || quickstartUrl || handoffUrl || adviceUrl) && (
        <div className="workbench-external-agent">
          <div className="workbench-external-agent-head">
            <span>External Agent Boot</span>
            <strong>{externalAgentBootSummary({ onboardingUrl, readinessUrl, quickstartUrl, evidenceUrl, handoffUrl, adviceUrl, metricsUrl, learningUrl })}</strong>
            <div className="workbench-external-agent-actions">
              {onboardingMarkdownUrl && (
                <button type="button" onClick={copyOnboardingMarkdown}>
                  {onboardingCopyState === 'copied'
                    ? 'Copied'
                    : onboardingCopyState === 'error'
                      ? 'Copy failed'
                      : 'Copy Onboarding'}
                </button>
              )}
              {evidenceUrl && (
                <button type="button" onClick={() => loadEvidenceBundle('manual')}>
                  {evidencePreviewState === 'loading'
                    ? 'Loading'
                    : evidencePreviewState === 'error'
                      ? 'Retry'
                      : 'Evidence'}
                </button>
              )}
              {evidenceMarkdownUrl && (
                <button type="button" onClick={copyEvidenceMarkdown}>
                  {evidenceCopyState === 'copied'
                    ? 'Copied'
                    : evidenceCopyState === 'error'
                      ? 'Copy failed'
                      : 'Copy Evidence'}
                </button>
              )}
              <button type="button" onClick={copyExternalAgentBoot}>
                {externalBootCopyState === 'copied'
                  ? 'Copied'
                  : externalBootCopyState === 'error'
                    ? 'Copy failed'
                    : 'Copy Boot'}
              </button>
            </div>
          </div>
          {evidenceUrl && (
            <div className="workbench-external-agent-evidence">
              <span>Bundle</span>
              <strong>{evidenceBundleSummary(evidencePreview, evidencePreviewState)}</strong>
            </div>
          )}
          {onboardingUrl && (
            <div className="workbench-external-agent-evidence workbench-external-agent-onboarding">
              <span>Onboarding</span>
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
      {quickstartUrl && (
        <div className="workbench-quickstart">
          <div className="workbench-quickstart-head">
            <span>LLM Quickstart</span>
            <div>
              <button type="button" onClick={loadQuickstartPreview}>
                {quickstartPreviewState === 'loading'
                  ? 'Loading'
                  : quickstartPreviewState === 'error'
                    ? 'Retry'
                    : quickstartPreview
                      ? 'Refresh'
                      : 'Preview'}
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
          <span>Runtime</span>
          <strong>{communication.runtime_metrics}</strong>
        </div>
      )}
      {metricsUrl && (
        <div className="workbench-runtime-metrics">
          <div className="workbench-runtime-metrics-head">
            <span>Runtime Metrics</span>
            <strong>{runtimeMetricsSummary(runtimeMetricsPreview?.summary)}</strong>
            <button type="button" onClick={() => loadRuntimeMetrics('manual')}>
              {runtimeMetricsState === 'loading'
                ? 'Loading'
                : runtimeMetricsState === 'error'
                  ? 'Retry'
                  : 'Refresh'}
            </button>
          </div>
          <div className="workbench-runtime-metrics-grid">
            <Metric label="Events" value={String(runtimeMetricsPreview?.count ?? '-')} />
            <Metric label="Tokens" value={String(runtimeMetricsPreview?.summary?.llm_total_tokens ?? '-')} />
            <Metric label="Cache" value={runtimeTokenCacheSummary(runtimeMetricsPreview?.summary)} />
            <Metric label="Rank" value={runtimeRankingSummary(runtimeMetricsPreview?.summary)} />
          </div>
          {runtimeMetricsPreview?.latest && (
            <small>{runtimeLatestMetricSummary(runtimeMetricsPreview.latest)}</small>
          )}
        </div>
      )}
      {communication.llm_probe && (
        <div className="workbench-contract-line">
          <span>LLM Probe</span>
          <strong>{communication.llm_probe}</strong>
        </div>
      )}
      {communication.llm_probe_history && (
        <div className="workbench-contract-line">
          <span>Probe History</span>
          <strong>{communication.llm_probe_history}</strong>
        </div>
      )}
      {communication.runtime_advice && (
        <div className="workbench-contract-line">
          <span>Advice</span>
          <strong>{communication.runtime_advice}</strong>
        </div>
      )}
      {adviceUrl && (
        <div className={`workbench-runtime-advice advice-${advicePreview?.priority || advicePreview?.status || 'unknown'}`}>
          <div className="workbench-runtime-advice-head">
            <span>Runtime Advice</span>
            <strong>{runtimeAdviceSummary(advicePreview)}</strong>
            <button type="button" onClick={() => loadRuntimeAdvice('manual')}>
              {advicePreviewState === 'loading'
                ? 'Loading'
                : advicePreviewState === 'error'
                  ? 'Retry'
                  : 'Refresh'}
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
          <span>Learning</span>
          <strong>{communication.learning_status}</strong>
        </div>
      )}
      {learningUrl && (
        <div className={`workbench-learning-status learning-${learningPreview?.latest?.state || state.layers.learning.status || 'idle'}`}>
          <div className="workbench-learning-status-head">
            <span>Learning Status</span>
            <strong>{learningStatusSummary(learningPreview, state.layers.learning.detail)}</strong>
            <button type="button" onClick={() => loadLearningStatus('manual')}>
              {learningPreviewState === 'loading'
                ? 'Loading'
                : learningPreviewState === 'error'
                  ? 'Retry'
                  : 'Refresh'}
            </button>
          </div>
          {learningPreview?.latest?.detail && <small>{learningPreview.latest.detail}</small>}
          {learningPreview?.latest?.metrics && (
            <code>{learningMetricsSummary(learningPreview.latest.metrics)}</code>
          )}
        </div>
      )}
      {warningCodes.length > 0 && (
        <div className="workbench-contract-line">
          <span>Codes</span>
          <strong>{warningCodes.join(' / ')}</strong>
        </div>
      )}
      {handoffUrl && (
        <div className="workbench-handoff">
          <div className="workbench-handoff-head">
            <span>Agent Handoff</span>
            <div>
              <button type="button" onClick={loadHandoffPreview}>
                {handoffPreviewState === 'loading'
                  ? 'Loading'
                  : handoffPreviewState === 'error'
                    ? 'Retry'
                    : handoffPreview
                      ? 'Refresh'
                      : 'Preview'}
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
      return 'health'
    case 'repair_status':
      return 'repair'
    case 'error_count':
      return 'errors'
    case 'token_usage_ratio':
      return 'tokens'
    case 'context_window_ratio':
      return 'ctx'
    case 'context_saturation':
      return 'ctx_state'
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
      return 'tool_phase'
    case 'tool_candidates':
      return 'candidates'
    case 'tool_selected':
      return 'selected'
    case 'tool_ranking_ms':
      return 'rank_ms'
    case 'tool_rank_cache_hit':
      return 'rank_hit'
    case 'tool_rank_cache_size':
      return 'rank_cache'
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
      return 'Idle'
    case 'running':
      return 'Running'
    case 'approval':
      return 'Approval'
    case 'error':
      return 'Needs care'
    case 'done':
      return 'Done'
    default:
      return stage
  }
}

function toolStatusLabel(status: 'running' | 'ok' | 'error'): string {
  switch (status) {
    case 'running':
      return 'running'
    case 'ok':
      return 'ok'
    case 'error':
      return 'error'
    default:
      return status
  }
}

function goalOverallLabel(overall?: AgentWorkbenchState['goalChecklist']['overall']): string {
  switch (overall) {
    case 'done':
      return 'All criteria met'
    case 'warn':
      return 'Needs review'
    case 'fail':
      return 'Needs repair'
    default:
      return 'In progress'
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

function runtimeMetricsSummary(summary?: RuntimeMetricsSummary): string {
  if (!summary) return 'waiting for metrics'
  const latency = summary.max_latency || {}
  const retrieval = summary.retrieval || {}
  return [
    latency.phase ? `${latency.phase}=${formatMs(latency.elapsed_ms)}` : 'latency=-',
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
  const candidates = ranking.candidate_count ?? '-'
  const hit = ranking.cache_hit === undefined ? '-' : ranking.cache_hit ? 'hit' : 'miss'
  return `${selected}/${candidates}/${hit}`
}

function runtimeLatestMetricSummary(metric: RuntimeMetricLatest): string {
  return [
    `latest=${metric.kind || '-'}`,
    metric.phase ? `phase=${metric.phase}` : '',
    typeof metric.iteration === 'number' ? `iter=${metric.iteration + 1}` : '',
    typeof metric.elapsed_ms === 'number' ? `elapsed=${formatMs(metric.elapsed_ms)}` : '',
    typeof metric.total_tokens === 'number' ? `tokens=${metric.total_tokens}` : '',
    typeof metric.token_count === 'number' ? `ctx_tokens=${metric.token_count}` : '',
    typeof metric.context_build_ms === 'number' ? `ctx=${formatMs(metric.context_build_ms)}` : '',
    typeof metric.selected_count === 'number' ? `selected=${metric.selected_count}` : '',
    typeof metric.candidate_count === 'number' ? `candidates=${metric.candidate_count}` : '',
    metric.cache_hit !== undefined ? `cache=${metric.cache_hit ? 'hit' : 'miss'}` : '',
  ].filter(Boolean).join(' | ')
}

function learningStatusSummary(preview?: LearningPreview | null, fallback = ''): string {
  const latest = preview?.latest
  if (!latest) return preview?.count ? `events=${preview.count}` : fallback || 'waiting for learning event'
  return [
    latest.event || latest.state || 'learning',
    latest.state ? `state=${latest.state}` : '',
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
  if (state === 'loading') return 'refreshing compact evidence'
  if (state === 'error') return 'bundle unavailable; use detail refresh'
  if (!preview) return 'waiting for compact evidence'
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
  return [`advice=${advice}`, maker, setup, audit, context, layers, metrics, learning, guard, probe, proof, feedback].filter(Boolean).join(' | ')
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
    learningUrl ? `10. Watch Learning Status: ${learningUrl}` : '',
    communication.context_sync ? `11. Pull Context Sync: ${API_BASE}${communication.context_sync}` : '',
    communication.llm_probe_history ? `12. Check LLM Probe History: ${API_BASE}${communication.llm_probe_history}` : '',
    communication.llm_feedback_summary ? `13. Read LLM Feedback Summary: ${API_BASE}${communication.llm_feedback_summary}` : '',
    communication.maker_setup_status ? `14. Check Maker Setup Doctor: ${API_BASE}${communication.maker_setup_status}` : '',
    communication.maker_tool_audit ? `15. Audit Maker Tools: ${API_BASE}${communication.maker_tool_audit}` : '',
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
