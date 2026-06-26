import { useRef, useCallback, useEffect, useState } from 'react'
import { Message, Provider } from '../App'

const API_BASE = 'http://127.0.0.1:7345'

export interface ApprovalRequest {
  actionId: string
  message: string
}

export interface UseBackendReturn {
  sendMessage: (task: string, displayText?: string) => void
  cancelCurrent: () => Promise<void>
  resetConversation: () => void
  isLoading: boolean
  approval: ApprovalRequest | null
  respondApproval: (allowed: boolean) => Promise<void>
  workbench: AgentWorkbenchState
  queueCount: number
}

export interface LlmUsagePayload {
  phase?: string
  provider?: string
  mode?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  token_count?: number
  generate_ms?: number
  tokens_per_sec?: number
  endpoint?: string
  http_status?: number
  error_type?: string
}

export type WorkbenchStage = 'idle' | 'running' | 'approval' | 'error' | 'done'
export type WorkbenchLayerName = 'agent' | 'runtime' | 'learning'
export type WorkbenchLayerStatus = 'idle' | 'active' | 'done' | 'error'

export interface WorkbenchLayer {
  status: WorkbenchLayerStatus
  detail: string
  event?: string
  sourceLayer?: string
  targetLayer?: string
  correlationId?: string
  cause?: string
  metrics?: Record<string, unknown>
  timestamp?: number
}

export interface WorkbenchToolRun {
  id: string
  tool: string
  params: Record<string, unknown>
  status: 'running' | 'ok' | 'error'
  source?: string
  observation?: unknown
  timestamp: number
  elapsedMs?: number
  progressElapsedMs?: number
  heartbeatCount?: number
  progressStatus?: string
  idempotencyKey?: string
  committed?: boolean | null
  observedAt?: number
}

export interface WorkbenchToolPreflight {
  tool?: string
  ok?: boolean
  alternatives?: Array<{
    name?: string
    source?: string
    reason?: string
  }>
  suggestedNextStep?: string
}

export interface WorkbenchPlanValidation {
  tool?: string
  verdict?: 'pass' | 'warn' | 'fail'
  summary?: string
  nextCheck?: string
  issues?: Array<{
    code?: string
    message?: string
    suggested_fix?: string
  }>
}

export interface WorkbenchGoalCriterion {
  id?: string
  label?: string
  status?: 'done' | 'pending' | 'warn' | 'fail'
  evidence?: string[]
  next_check?: string
  source?: string
  template_id?: string
}

export interface WorkbenchGoalChecklist {
  overall?: 'active' | 'done' | 'warn' | 'fail'
  counts?: Record<string, number>
  criteria?: WorkbenchGoalCriterion[]
  nextFocus?: string
}

export interface WorkbenchSkillSync {
  ok?: boolean
  changed?: boolean
  state?: string
  compatibilityStatus?: string
  signature?: string
  manifestSummary?: Record<string, number | string>
  exportPlanSummary?: Record<string, number | string>
  graphSummary?: Record<string, number | string>
  conflicts?: Array<{
    type?: string
    skill_id?: string
    version?: string
  }>
  actionsPreview?: Array<{
    action?: string
    skill_id?: string
    target?: string
    reason?: string
    needs_review?: boolean
  }>
}

export interface WorkbenchContextSync {
  revision?: number
  changed?: boolean
  signature?: string
  previousSignature?: string
  reason?: string
  diffKeys?: string[]
  snapshot?: {
    session_id?: string
    task?: string
    iteration?: number
    trajectory_steps?: number
    last_tool?: string
    last_action?: {
      tool?: string
      params_keys?: string[]
      done?: boolean
    }
    plan_validation?: {
      verdict?: 'pass' | 'warn' | 'fail'
      summary?: string
      next_check?: string
      issues_count?: number
    }
    goal_checklist?: {
      overall?: 'active' | 'done' | 'warn' | 'fail'
      counts?: Record<string, number>
      next_focus?: string
    }
    commit_state?: WorkbenchCommitState
    skill_sync?: {
      ok?: boolean
      state?: string
      signature?: string
      compatibility_status?: string
      changed?: boolean
    }
    artifact_refs?: Array<Record<string, unknown>>
    artifact_count?: number
  }
}

export interface WorkbenchRuntimeContract {
  version?: string
  purpose?: string
  makerMcp?: {
    readiness?: 'ready' | 'degraded' | 'disconnected' | string
    connected?: boolean
    tool_count?: number
    top_tools?: Array<{
      name?: string
      description?: string
      params?: string[]
    }>
    first_action_checklist?: Array<{
      id?: string
      label?: string
      status?: 'ready' | 'warn' | 'blocked' | string
      why?: string
      evidence?: string
      action?: string
      sample_tools?: string[]
    }>
    task_templates?: Array<{
      id?: string
      label?: string
      status?: 'ready' | 'warn' | 'blocked' | string
      when?: string
      authority?: string[]
      steps?: string[]
      acceptance_criteria?: string[]
      token_strategy?: string
      suggested_tools?: string[]
    }>
    remote_identity?: {
      status?: string
      missing?: string[]
      summary?: string
    }
  }
  layers?: Record<string, {
    owns?: string[]
    emits?: string[]
  }>
  communication?: Record<string, string>
  tokenEfficiency?: {
    rules?: string[]
    available_mechanisms?: string[]
  }
  warnings?: string[]
  warningCodes?: string[]
  externalAgents?: {
    compatible_surfaces?: string[]
    attach_sequence?: string[]
    handoff_rule?: string
  }
}

export interface WorkbenchMakerBriefing {
  version?: string
  task?: string
  readiness?: string
  connected?: boolean
  warningCodes?: string[]
  authority?: string
  selectedTemplate?: {
    id?: string
    label?: string
    status?: string
    acceptanceCriteria?: string[]
  }
  recommendedFirstAction?: string
  recommendedEndpoint?: string
  suggestedTools?: string[]
  checklist?: Array<{
    id?: string
    status?: string
    evidence?: string
    action?: string
  }>
  evidenceEndpoints?: Record<string, string>
  tokenRule?: string
}

export interface WorkbenchMakerGuard {
  decision?: 'pass' | 'warn' | 'block' | 'skip' | string
  tool?: string
  reason?: string
  authority?: string
  allowedTools?: string[]
  suggestedTools?: string[]
  recommendedFirstAction?: string
  recommendedEndpoint?: string
}

export interface WorkbenchLlmProbe {
  status?: string
  ok?: boolean | null
  provider?: string
  runtimeKind?: string
  llmClass?: string
  model?: string
  baseUrl?: string
  endpoint?: string
  elapsedMs?: number
  totalTokens?: number
  generateMs?: number
  httpStatus?: number
  errorType?: string
  error?: string
  outputPreview?: string
}

export interface WorkbenchLatency {
  firstResponseMs?: number
  lastLlmMs?: number
  lastToolMs?: number
  totalMs?: number
}

export interface WorkbenchCommitState {
  idempotencyKey?: string
  tool?: string
  committed?: boolean | null
  observedAt?: number
  reconcileStatus?: string
  remoteLookupTool?: string
  remoteLookupAttempts?: number
}

export interface AgentWorkbenchState {
  sessionId: string | null
  stage: WorkbenchStage
  currentStatus: string
  currentThought: string
  currentTool: string
  lastError: string
  finalOutput: string
  iteration: number | null
  toolRuns: WorkbenchToolRun[]
  layers: Record<WorkbenchLayerName, WorkbenchLayer>
  latency: WorkbenchLatency
  commitState: WorkbenchCommitState
  toolPreflight: WorkbenchToolPreflight
  planValidation: WorkbenchPlanValidation
  goalChecklist: WorkbenchGoalChecklist
  skillSync: WorkbenchSkillSync
  contextSync: WorkbenchContextSync
  runtimeContract: WorkbenchRuntimeContract
  makerBriefing: WorkbenchMakerBriefing
  makerGuard: WorkbenchMakerGuard
  llmProbe: WorkbenchLlmProbe
}

const emptyWorkbench: AgentWorkbenchState = {
  sessionId: null,
  stage: 'idle',
  currentStatus: '',
  currentThought: '',
  currentTool: '',
  lastError: '',
  finalOutput: '',
  iteration: null,
  toolRuns: [],
  latency: {},
  commitState: {},
  toolPreflight: {},
  planValidation: {},
  goalChecklist: {},
  skillSync: {},
  contextSync: {},
  runtimeContract: {},
  makerBriefing: {},
  makerGuard: {},
  llmProbe: {},
  layers: {
    agent: { status: 'idle', detail: '推理/规划' },
    runtime: { status: 'idle', detail: '工具/MCP' },
    learning: { status: 'idle', detail: '经验/反思' },
  },
}

function formatDuration(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

export function useBackend(
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void,
  setLoading: (loading: boolean) => void,
  provider: Provider,
  model?: string,
  baseUrl?: string,
  apiKey?: string,
  profile?: string,
  onFileTreeRefresh?: () => void,
  onUsage?: (usage: LlmUsagePayload) => void,
): UseBackendReturn {
  const eventSourceRef = useRef<EventSource | null>(null)
  const isLoadingRef = useRef(false)
  const cancelRequestedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const pendingQueueRef = useRef<Array<{ task: string; displayText?: string }>>([])
  const [approval, setApproval] = useState<ApprovalRequest | null>(null)
  const [workbench, setWorkbench] = useState<AgentWorkbenchState>(emptyWorkbench)
  const [queueCount, setQueueCount] = useState(0)

  const fetchRuntimeContract = useCallback(async (sessionId: string) => {
    try {
      const resp = await fetch(
        `${API_BASE}/agent/runtime-contract?session_id=${encodeURIComponent(sessionId)}`
      )
      const data = await resp.json()
      const makerMcp = data.maker_mcp || {}
      const tokenEfficiency = data.token_efficiency || {}
      const warnings = Array.isArray(data.warnings) ? data.warnings.slice(0, 4) : []
      const warningCodes = Array.isArray(data.warning_codes) ? data.warning_codes.slice(0, 4) : []
      const topTools = Array.isArray(makerMcp.top_tools)
        ? makerMcp.top_tools.slice(0, 6)
        : []
      const firstActionChecklist = Array.isArray(makerMcp.first_action_checklist)
        ? makerMcp.first_action_checklist.slice(0, 6)
        : []
      const taskTemplates = Array.isArray(makerMcp.task_templates)
        ? makerMcp.task_templates.slice(0, 5)
        : []
      const readiness = typeof makerMcp.readiness === 'string'
        ? makerMcp.readiness
        : 'unknown'
      setWorkbench((prev) => ({
        ...prev,
        runtimeContract: {
          version: data.version,
          purpose: data.purpose,
          makerMcp: {
            readiness,
            connected: Boolean(makerMcp.connected),
            tool_count: Number(makerMcp.tool_count || 0),
            top_tools: topTools,
            first_action_checklist: firstActionChecklist,
            task_templates: taskTemplates,
            remote_identity: makerMcp.remote_identity || {},
          },
          layers: data.layers || {},
          communication: data.communication || {},
          tokenEfficiency,
          warnings,
          warningCodes,
          externalAgents: data.external_agents || {},
        },
        layers: {
          ...prev.layers,
          runtime: {
            ...prev.layers.runtime,
            status: readiness === 'ready' ? 'done' : readiness === 'disconnected' ? 'error' : 'active',
            detail: readiness === 'ready'
                          ? '运行契约就绪'
              : readiness === 'disconnected'
                          ? 'MakerMCP 契约断开'
                : 'Runtime contract degraded',
            event: 'runtime_contract',
            metrics: {
              ...(prev.layers.runtime.metrics || {}),
              contract_tools: Number(makerMcp.tool_count || 0),
              contract_warnings: warnings.length,
              contract_warning_codes: warningCodes.length,
              maker_checklist_ready: firstActionChecklist.filter((item: any) => item.status === 'ready').length,
              maker_checklist_warn: firstActionChecklist.filter((item: any) => item.status === 'warn').length,
              maker_templates: taskTemplates.length,
              maker_templates_warn: taskTemplates.filter((item: any) => item.status === 'warn').length,
            },
          },
        },
      }))
    } catch (err: any) {
      setWorkbench((prev) => ({
        ...prev,
        runtimeContract: {
          warnings: [`Runtime contract unavailable: ${err.message || err}`],
        },
        layers: {
          ...prev.layers,
          runtime: {
            ...prev.layers.runtime,
            status: 'error',
            detail: 'Runtime contract unavailable',
            event: 'runtime_contract',
          },
        },
      }))
    }
  }, [])

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  const respondApproval = useCallback(
    async (allowed: boolean) => {
      if (!approval || !sessionIdRef.current) return
      try {
        const resp = await fetch(
          `${API_BASE}/sessions/${sessionIdRef.current}/approve`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action_id: approval.actionId,
              allowed,
            }),
          }
        )
        const data = await resp.json()
        if (data.error) {
          throw new Error(data.error)
        }
        setApproval(null)
        setWorkbench((prev) => ({
          ...prev,
          stage: prev.stage === 'approval' ? 'running' : prev.stage,
        }))
      } catch (err: any) {
        addMessage({ role: 'system', content: `Approval failed: ${err.message}` })
      }
    },
    [approval, addMessage]
  )

  const startTask = useCallback(
    async (task: string, announceUser = true, displayText?: string) => {
      isLoadingRef.current = true
      cancelRequestedRef.current = false
      setLoading(true)
      setApproval(null)
      setWorkbench({
        ...emptyWorkbench,
        stage: 'running',
        currentStatus: '正在创建会话',
      })
      if (announceUser) {
        addMessage({ role: 'user', content: displayText || task })
      }

      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const runQueuedNext = () => {
        const next = pendingQueueRef.current.shift()
        setQueueCount(pendingQueueRef.current.length)
        if (next) {
          window.setTimeout(() => {
            void startTask(next.task, false, next.displayText)
          }, 0)
        }
      }

      try {
        const resp = await fetch(`${API_BASE}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            task,
            provider,
            profile,
            model,
            base_url: baseUrl,
            api_key: apiKey,
          }),
        })
        const data = await resp.json()
        if (data.error) {
          throw new Error(data.error)
        }

        const sessionId = data.session_id
        sessionIdRef.current = sessionId
        setWorkbench((prev) => ({
          ...prev,
          sessionId,
          stage: 'running',
          currentStatus: 'Session created',
        }))
        void fetchRuntimeContract(sessionId)
        let assistantText = ''
        let hadOutput = false
        let finalMessageCommitted = false

        const es = new EventSource(`${API_BASE}/sessions/${sessionId}/events`)
        eventSourceRef.current = es

        const commitAssistantMessage = (content: string) => {
          const text = content.trim()
          if (!text || finalMessageCommitted) return
          finalMessageCommitted = true
          addMessage({
            role: 'assistant',
            content: text,
          })
        }

        const appendEvent = (
          eventType: string,
          content: string,
          extra?: Partial<Omit<Message, 'id' | 'timestamp' | 'role' | 'content' | 'eventType'>>
        ) => {
          addMessage({
            role: 'event',
            eventType,
            content,
            source: extra?.source,
            isFail: extra?.isFail,
          })
        }

        es.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data)
            const type = event.type
            const payload = event.payload || {}
            const source = event.source || 'local'

            switch (type) {
              case 'status': {
                if (payload.message && !payload.done) {
                  setWorkbench((prev) => ({
                    ...prev,
                    stage: 'running',
                    currentStatus: payload.message,
                  }))
                }
                if (payload.done) {
                  const wasCanceled = Boolean(payload.canceled)
                  const finalOutput = hadOutput
                    ? assistantText
                    : payload.message || 'Task completed.'
                  setWorkbench((prev) => ({
                    ...prev,
                    stage: wasCanceled ? 'idle' : (prev.lastError ? 'error' : 'done'),
                    currentStatus: payload.message || 'Task finished',
                    finalOutput: wasCanceled ? '' : finalOutput,
                    currentTool: '',
                  }))
                  if (!wasCanceled && (hadOutput || payload.message)) {
                    commitAssistantMessage(finalOutput)
                  } else if (wasCanceled) {
                    addMessage({ role: 'system', content: 'Current task canceled.' })
                  }
                  es.close()
                  isLoadingRef.current = false
                  cancelRequestedRef.current = false
                  setLoading(false)
                  setApproval(null)
                  runQueuedNext()
                }
                break
              }
              case 'thought': {
                if (payload.thought) {
                  setWorkbench((prev) => ({
                    ...prev,
                    stage: 'running',
                    currentThought: payload.thought,
                    iteration: typeof payload.iteration === 'number' ? payload.iteration : prev.iteration,
                    layers: {
                      ...prev.layers,
                      agent: { status: 'active', detail: '正在推理' },
                    },
                  }))
                }
                break
              }
              case 'tool_selection': {
                const tools = Array.isArray(payload.tools) ? payload.tools : []
                const names = tools.map((tool: any) => tool.name).filter(Boolean).slice(0, 4)
                const stats = payload.stats && typeof payload.stats === 'object' ? payload.stats : {}
                setWorkbench((prev) => ({
                  ...prev,
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: 'active',
                      detail: payload.phase === 'action'
                          ? '动作工具已排序'
                        : 'Tool context ranked',
                      event: 'tool_selection',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        tool_phase: payload.phase || 'think',
                        tool_candidates: stats.candidate_count,
                        tool_selected: stats.selected_count ?? tools.length,
                        tool_ranking_ms: stats.ranking_ms,
                        tool_rank_cache_hit: stats.cache_hit,
                        tool_rank_cache_size: stats.cache_size,
                      },
                    },
                  },
                  currentStatus: names.length > 0 ? `候选工具：${names.join(', ')}` : prev.currentStatus,
                }))
                break
              }
              case 'tool_preflight': {
                const alternatives = Array.isArray(payload.alternatives)
                  ? payload.alternatives.slice(0, 3)
                  : []
                const ok = Boolean(payload.ok)
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: ok
                    ? `工具预检通过：${payload.tool || 'unknown'}`
                    : `工具预检失败：${payload.tool || 'unknown'}`,
                  toolPreflight: {
                    tool: payload.tool,
                    ok,
                    alternatives,
                    suggestedNextStep:
                      typeof payload.suggested_next_step === 'string'
                        ? payload.suggested_next_step
                        : undefined,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: ok ? 'active' : 'error',
                      detail: ok ? '工具预检通过' : '工具预检失败',
                      event: 'tool_preflight',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        alternatives: alternatives.length,
                      },
                    },
                  },
                }))
                break
              }
              case 'llm_usage': {
                onUsage?.(payload)
                break
              }
              case 'context_budget': {
                onUsage?.({
                  phase: 'context_budget',
                  token_count: payload.token_count,
                })
                setWorkbench((prev) => ({
                  ...prev,
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: 'active',
                      detail: 'Context budget fitted',
                      event: 'context_budget',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        token_usage_ratio: payload.token_usage_ratio,
                        context_window_ratio: payload.context_window_ratio,
                        compression_applied: payload.compression_applied,
                        dropped_parts: payload.dropped_parts,
                        truncated_chars: payload.truncated_chars,
                        token_cache_hits: payload.token_cache_hits,
                        token_cache_misses: payload.token_cache_misses,
                        token_cache_size: payload.token_cache_size,
                        agents_md_hits: payload.agents_md_hits,
                        cold_recall_hits: payload.cold_recall_hits,
                        agents_md_ms: payload.agents_md_ms,
                        cold_recall_ms: payload.cold_recall_ms,
                        context_build_ms: payload.context_build_ms,
                      },
                    },
                  },
                }))
                break
              }
              case 'maker_briefing': {
                const selectedTemplate = payload.selected_template && typeof payload.selected_template === 'object'
                  ? payload.selected_template
                  : {}
                const checklist = Array.isArray(payload.checklist)
                  ? payload.checklist.slice(0, 6)
                  : []
                const suggestedTools = Array.isArray(payload.suggested_tools)
                  ? payload.suggested_tools.filter(Boolean).slice(0, 4)
                  : []
                const warningCodes = Array.isArray(payload.warning_codes)
                  ? payload.warning_codes.filter(Boolean).slice(0, 4)
                  : []
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: payload.recommended_first_action || prev.currentStatus,
                  makerBriefing: {
                    version: payload.version,
                    task: payload.task,
                    readiness: payload.readiness,
                    connected: Boolean(payload.connected),
                    warningCodes,
                    authority: payload.authority,
                    selectedTemplate: {
                      id: selectedTemplate.id,
                      label: selectedTemplate.label,
                      status: selectedTemplate.status,
                      acceptanceCriteria: Array.isArray(selectedTemplate.acceptance_criteria)
                        ? selectedTemplate.acceptance_criteria.slice(0, 3)
                        : [],
                    },
                    recommendedFirstAction: payload.recommended_first_action,
                    recommendedEndpoint: payload.recommended_endpoint,
                    suggestedTools,
                    checklist,
                    evidenceEndpoints: payload.evidence_endpoints || {},
                    tokenRule: payload.token_rule,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: payload.connected ? 'active' : 'error',
                      detail: payload.connected
                          ? 'Maker 首步已生成'
                        : 'Maker briefing reports disconnected authority',
                      event: 'maker_briefing',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        maker_briefing_tools: suggestedTools.length,
                        maker_briefing_warnings: warningCodes.length,
                        maker_briefing_checklist: checklist.length,
                      },
                    },
                  },
                }))
                break
              }
              case 'maker_briefing_guard': {
                const allowedTools = Array.isArray(payload.allowed_tools)
                  ? payload.allowed_tools.filter(Boolean).slice(0, 8)
                  : []
                const suggestedTools = Array.isArray(payload.suggested_tools)
                  ? payload.suggested_tools.filter(Boolean).slice(0, 4)
                  : []
                const decision = typeof payload.decision === 'string' ? payload.decision : 'warn'
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: payload.reason || prev.currentStatus,
                  makerGuard: {
                    decision,
                    tool: payload.tool,
                    reason: payload.reason,
                    authority: payload.authority,
                    allowedTools,
                    suggestedTools,
                    recommendedFirstAction: payload.recommended_first_action,
                    recommendedEndpoint: payload.recommended_endpoint,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: decision === 'block' ? 'error' : decision === 'warn' ? 'active' : 'done',
                      detail: decision === 'block'
                          ? 'Maker 首步被阻止'
                        : decision === 'warn'
                          ? 'Maker 首步需检查'
                          : 'Maker first action aligned',
                      event: 'maker_briefing_guard',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        maker_guard_decision: decision,
                        maker_guard_allowed_tools: allowedTools.length,
                      },
                    },
                  },
                }))
                break
              }
              case 'llm_probe': {
                const stats = payload.last_call_stats && typeof payload.last_call_stats === 'object'
                  ? payload.last_call_stats
                  : {}
                const ok = Boolean(payload.ok)
                const elapsedMs = typeof payload.elapsed_ms === 'number' ? payload.elapsed_ms : undefined
                const totalTokens = typeof stats.total_tokens === 'number' ? stats.total_tokens : undefined
                onUsage?.({
                  phase: 'llm_probe',
                  provider: payload.provider,
                  total_tokens: totalTokens,
                  generate_ms: stats.generate_ms,
                  tokens_per_sec: stats.tokens_per_sec,
                  endpoint: stats.endpoint,
                  http_status: stats.http_status,
                  error_type: stats.error_type,
                })
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: ok ? 'LLM 提供方已验证' : 'LLM 提供方验证失败',
                  llmProbe: {
                    status: ok ? 'ok' : 'error',
                    ok,
                    provider: payload.provider,
                    runtimeKind: payload.runtime_kind,
                    llmClass: payload.llm_class,
                    model: payload.model,
                    baseUrl: payload.base_url,
                    endpoint: stats.endpoint,
                    elapsedMs,
                    totalTokens,
                    generateMs: stats.generate_ms,
                    httpStatus: stats.http_status,
                    errorType: stats.error_type,
                    error: payload.error,
                    outputPreview: payload.output_preview,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: ok ? 'done' : 'error',
                        detail: ok ? '工具调用完成' : '工具调用失败',
                      event: 'llm_probe',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        llm_probe_ok: ok,
                        llm_probe_provider: payload.provider,
                        llm_probe_model: payload.model,
                        llm_probe_endpoint: stats.endpoint,
                        llm_probe_elapsed_ms: elapsedMs,
                        llm_probe_total_tokens: totalTokens,
                        llm_probe_error_type: stats.error_type,
                      },
                    },
                  },
                }))
                break
              }
              case 'latency': {
                const elapsedMs = typeof payload.elapsed_ms === 'number' ? payload.elapsed_ms : undefined
                setWorkbench((prev) => {
                  const nextLatency = { ...prev.latency }
                  if (payload.phase === 'first_response') {
                    nextLatency.firstResponseMs = elapsedMs
                  } else if (payload.phase === 'llm_think' || payload.phase === 'llm_action') {
                    nextLatency.lastLlmMs = elapsedMs
                  } else if (payload.phase === 'tool_call') {
                    nextLatency.lastToolMs = elapsedMs
                  } else if (payload.phase === 'session_total') {
                    nextLatency.totalMs = elapsedMs
                  }

                  let nextRuns = prev.toolRuns
                  if (payload.phase === 'tool_call' && payload.tool) {
                    nextRuns = [...prev.toolRuns]
                    const index = [...nextRuns]
                      .reverse()
                      .findIndex((run) => run.tool === payload.tool && run.elapsedMs === undefined)
                    const realIndex = index >= 0 ? nextRuns.length - 1 - index : -1
                    if (realIndex >= 0) {
                      nextRuns[realIndex] = {
                        ...nextRuns[realIndex],
                        elapsedMs,
                      }
                    }
                  }

                  return {
                    ...prev,
                    latency: nextLatency,
                    toolRuns: nextRuns,
                  }
                })
                break
              }
              case 'tool_progress': {
                const elapsedMs = typeof payload.elapsed_ms === 'number' ? payload.elapsed_ms : undefined
                const heartbeatCount =
                  typeof payload.heartbeat_count === 'number' ? payload.heartbeat_count : undefined
                const toolName = payload.tool || 'unknown'
                setWorkbench((prev) => {
                  const nextRuns = [...prev.toolRuns]
                  const index = [...nextRuns]
                    .reverse()
                    .findIndex((run) => run.tool === toolName && run.status === 'running')
                  const realIndex = index >= 0 ? nextRuns.length - 1 - index : -1
                  if (realIndex >= 0) {
                    nextRuns[realIndex] = {
                      ...nextRuns[realIndex],
                      progressElapsedMs: elapsedMs,
                      heartbeatCount,
                      progressStatus: payload.status || 'running',
                    }
                  }
                  return {
                    ...prev,
                    stage: 'running',
                    currentTool: toolName,
                    currentStatus: `工具仍在运行：${toolName} ${formatDuration(elapsedMs)}`,
                    layers: {
                      ...prev.layers,
                      runtime: {
                        ...prev.layers.runtime,
                        status: 'active',
                        detail: `正在运行 ${toolName}`,
                        event: 'tool_progress',
                        metrics: {
                          ...(prev.layers.runtime.metrics || {}),
                          elapsed_ms: elapsedMs,
                          heartbeat_count: heartbeatCount,
                        },
                      },
                    },
                    toolRuns: nextRuns,
                  }
                })
                break
              }
              case 'action': {
                const action = payload.action
                if (action && action.done) {
                  assistantText = action.output || assistantText
                  hadOutput = true
                } else if (action?.tool) {
                  appendEvent(
                    'decision',
                    `准备调用 ${action.tool}`,
                    { source }
                  )
                  setWorkbench((prev) => ({
                    ...prev,
                    stage: 'running',
                    currentTool: action.tool,
                    iteration: typeof payload.iteration === 'number' ? payload.iteration : prev.iteration,
                    layers: {
                      ...prev.layers,
                      agent: { status: 'done', detail: '已选择动作' },
                      runtime: { status: 'active', detail: '准备调用工具' },
                    },
                  }))
                }
                if (action?._parse_error) {
                  appendEvent(
                    'action',
                    JSON.stringify(action, null, 2),
                    { source, isFail: true }
                  )
                }
                break
              }
              case 'tool_call': {
                const body = `${payload.tool || ''}\n${JSON.stringify(
                  payload.params || {},
                  null,
                  2
                )}`
                appendEvent('tool_call', body, { source })
                setWorkbench((prev) => {
                  const nextRun: WorkbenchToolRun = {
                    id: `${Date.now()}-${prev.toolRuns.length}`,
                    tool: payload.tool || 'unknown',
                    params: payload.params || {},
                    status: 'running',
                    source,
                    timestamp: Date.now(),
                  }
                  return {
                    ...prev,
                    stage: 'running',
                    currentTool: payload.tool || prev.currentTool,
                    layers: {
                      ...prev.layers,
                      runtime: { status: 'active', detail: payload.tool || 'Tool running' },
                    },
                    toolRuns: [...prev.toolRuns, nextRun].slice(-8),
                  }
                })
                break
              }
              case 'observation': {
                const observation = payload.observation
                const ok = observation && observation.ok
                const idempotencyKey =
                  observation && typeof observation.idempotency_key === 'string'
                    ? observation.idempotency_key
                    : undefined
                const observedAt =
                  observation && typeof observation.observed_at === 'number'
                    ? observation.observed_at
                    : undefined
                const reconcileStatus =
                  observation && typeof observation.reconcile_status === 'string'
                    ? observation.reconcile_status
                    : undefined
                const remoteLookupTool =
                  observation && typeof observation.remote_lookup_tool === 'string'
                    ? observation.remote_lookup_tool
                    : undefined
                const remoteLookupAttempts =
                  observation && Array.isArray(observation.remote_lookup_attempts)
                    ? observation.remote_lookup_attempts.length
                    : undefined
                const committed =
                  observation && Object.prototype.hasOwnProperty.call(observation, 'committed')
                    ? (observation.committed as boolean | null)
                    : undefined
                if (!ok) {
                  appendEvent(
                    'observation',
                    JSON.stringify(observation, null, 2),
                    { source, isFail: true }
                  )
                }
                setWorkbench((prev) => {
                  const nextRuns = [...prev.toolRuns]
                  const index = [...nextRuns]
                    .reverse()
                    .findIndex((run) => run.tool === (payload.tool || run.tool) && run.status === 'running')
                  const realIndex = index >= 0 ? nextRuns.length - 1 - index : -1
                  if (realIndex >= 0) {
                    nextRuns[realIndex] = {
                      ...nextRuns[realIndex],
                      status: ok ? 'ok' : 'error',
                      observation,
                      idempotencyKey,
                      committed,
                      observedAt,
                    }
                  }
                  return {
                    ...prev,
                    stage: ok ? prev.stage : 'error',
                    lastError: ok ? prev.lastError : JSON.stringify(observation),
                    currentTool: ok ? '' : prev.currentTool,
                    layers: {
                      ...prev.layers,
                      runtime: {
                        status: ok ? 'done' : 'error',
                        detail: ok ? '工具调用完成' : '工具调用失败',
                      },
                    },
                    toolRuns: nextRuns,
                    commitState: idempotencyKey
                      ? {
                          idempotencyKey,
                          tool: payload.tool,
                          committed,
                          observedAt,
                          reconcileStatus,
                          remoteLookupTool,
                          remoteLookupAttempts,
                        }
                      : prev.commitState,
                  }
                })
                if (ok && onFileTreeRefresh) {
                  const obsStr = JSON.stringify(observation)
                  if (
                    observation.tool === 'write_file' ||
                    observation.tool === 'delete_file' ||
                    observation.path ||
                    /write|delete|create|save|move|rename/.test(obsStr)
                  ) {
                    onFileTreeRefresh()
                  }
                }
                break
              }
              case 'goal_checklist': {
                const criteria = Array.isArray(payload.criteria)
                  ? payload.criteria.filter((item: any) => item && typeof item === 'object')
                  : []
                const makerCriteria = criteria.filter((item: any) => item.source === 'maker_template')
                const overall = ['active', 'done', 'warn', 'fail'].includes(payload.overall)
                  ? payload.overall
                  : undefined
                setWorkbench((prev) => ({
                  ...prev,
                  goalChecklist: {
                    overall,
                    counts: payload.counts || {},
                    criteria,
                    nextFocus:
                      typeof payload.next_focus === 'string'
                        ? payload.next_focus
                        : undefined,
                  },
                  layers: {
                    ...prev.layers,
                    agent: {
                      ...prev.layers.agent,
                      status: overall === 'fail' ? 'error' : overall === 'done' ? 'done' : 'active',
                      detail:
                        overall === 'done'
                          ? '验收清单完成'
                          : overall === 'fail'
                            ? '验收清单失败'
                            : '正在检查验收清单',
                      event: 'goal_checklist',
                      metrics: {
                        ...(prev.layers.agent.metrics || {}),
                        goal_done: payload.counts?.done || 0,
                        goal_pending: payload.counts?.pending || 0,
                        goal_warn: payload.counts?.warn || 0,
                        goal_fail: payload.counts?.fail || 0,
                        maker_goal_templates: makerCriteria.length,
                      },
                    },
                  },
                }))
                break
              }
              case 'skill_sync': {
                const conflicts = Array.isArray(payload.conflicts)
                  ? payload.conflicts.slice(0, 4)
                  : []
                const actionsPreview = Array.isArray(payload.actions_preview)
                  ? payload.actions_preview.slice(0, 4)
                  : []
                const compatibilityStatus =
                  typeof payload.compatibility_status === 'string'
                    ? payload.compatibility_status
                    : undefined
                const hasWarning =
                  compatibilityStatus === 'needs_review'
                  || conflicts.length > 0
                  || actionsPreview.some((item: any) => item.needs_review)
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: hasWarning
                          ? '技能同步需检查'
                    : payload.changed
                          ? '技能图已更新'
                      : prev.currentStatus,
                  skillSync: {
                    ok: payload.ok,
                    changed: Boolean(payload.changed),
                    state: payload.state,
                    compatibilityStatus,
                    signature: payload.signature,
                    manifestSummary: payload.manifest_summary || {},
                    exportPlanSummary: payload.export_plan_summary || {},
                    graphSummary: payload.graph_summary || {},
                    conflicts,
                    actionsPreview,
                  },
                  layers: {
                    ...prev.layers,
                    learning: {
                      ...prev.layers.learning,
                      status: hasWarning ? 'error' : payload.changed ? 'active' : 'done',
                      detail: hasWarning
                          ? '技能同步需检查'
                        : payload.changed
                          ? '技能图已更新'
                          : 'Skill graph aligned',
                      event: 'skill_sync',
                      metrics: {
                        ...(prev.layers.learning.metrics || {}),
                        skill_total: payload.graph_summary?.total_skills || payload.manifest_summary?.total_skills || 0,
                        skill_conflicts: conflicts.length,
                        skill_actions: payload.export_plan_summary?.total_actions || 0,
                      },
                    },
                  },
                }))
                break
              }
              case 'context_sync': {
                const snapshot = payload.snapshot && typeof payload.snapshot === 'object'
                  ? payload.snapshot
                  : {}
                const diffKeys = Array.isArray(payload.diff_keys)
                  ? payload.diff_keys.slice(0, 8)
                  : []
                const revision = Number(payload.revision || 0)
                const artifactCount = Number(snapshot.artifact_count || 0)
                const lastTool =
                  typeof snapshot.last_tool === 'string'
                    ? snapshot.last_tool
                    : undefined
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: lastTool
                    ? `Context synced after ${lastTool}`
                    : prev.currentStatus,
                  contextSync: {
                    revision,
                    changed: Boolean(payload.changed),
                    signature: payload.signature,
                    previousSignature: payload.previous_signature,
                    reason: payload.reason,
                    diffKeys,
                    snapshot,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: 'active',
                      detail: lastTool
                        ? `Context synced: ${lastTool}`
                        : 'Context synced',
                      event: 'context_sync',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        context_revision: revision,
                        context_diff_keys: diffKeys.length,
                        context_artifacts: artifactCount,
                      },
                    },
                  },
                }))
                break
              }
              case 'plan_validation': {
                const issues = Array.isArray(payload.issues) ? payload.issues.slice(0, 3) : []
                const verdict = ['pass', 'warn', 'fail'].includes(payload.verdict)
                  ? payload.verdict
                  : undefined
                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus: payload.summary || prev.currentStatus,
                  planValidation: {
                    tool: payload.tool,
                    verdict,
                    summary: payload.summary,
                    nextCheck:
                      typeof payload.next_check === 'string'
                        ? payload.next_check
                        : undefined,
                    issues,
                  },
                  layers: {
                    ...prev.layers,
                    runtime: {
                      ...prev.layers.runtime,
                      status: verdict === 'fail' ? 'error' : 'done',
                      detail:
                        verdict === 'pass'
                          ? '计划验证通过'
                          : verdict === 'warn'
                          ? '计划需复核'
                            : 'Plan validation failed',
                      event: 'plan_validation',
                      metrics: {
                        ...(prev.layers.runtime.metrics || {}),
                        plan_verdict: verdict || 'unknown',
                        issue_count: issues.length,
                      },
                    },
                  },
                }))
                break
              }
              case 'commit_reconcile': {
                const observation = payload.observation || {}
                const idempotencyKey =
                  typeof payload.idempotency_key === 'string'
                    ? payload.idempotency_key
                    : typeof observation.idempotency_key === 'string'
                      ? observation.idempotency_key
                      : undefined
                const committed =
                  Object.prototype.hasOwnProperty.call(payload, 'committed')
                    ? (payload.committed as boolean | null)
                    : Object.prototype.hasOwnProperty.call(observation, 'committed')
                      ? (observation.committed as boolean | null)
                      : null
                const observedAt =
                  typeof observation.observed_at === 'number'
                    ? observation.observed_at
                    : undefined
                const reconcileStatus =
                  typeof observation.reconcile_status === 'string'
                    ? observation.reconcile_status
                    : typeof payload.status === 'string'
                      ? payload.status
                      : undefined
                const remoteLookupTool =
                  typeof observation.remote_lookup_tool === 'string'
                    ? observation.remote_lookup_tool
                    : undefined
                const remoteLookupAttempts =
                  Array.isArray(observation.remote_lookup_attempts)
                    ? observation.remote_lookup_attempts.length
                    : undefined

                setWorkbench((prev) => ({
                  ...prev,
                  currentStatus:
                    payload.status === 'checking'
                          ? '正在确认写入状态'
                      : prev.currentStatus,
                  commitState: idempotencyKey
                    ? {
                        idempotencyKey,
                        tool: payload.tool,
                        committed,
                        observedAt,
                        reconcileStatus,
                        remoteLookupTool,
                        remoteLookupAttempts,
                      }
                    : prev.commitState,
                }))
                break
              }
              case 'output': {
                assistantText = payload.output || ''
                hadOutput = true
                setWorkbench((prev) => ({
                  ...prev,
                  finalOutput: assistantText,
                }))
                break
              }
              case 'layer': {
                const layer = payload.layer as WorkbenchLayerName
                const nextStatus = payload.state as WorkbenchLayerStatus
                if (layer && ['agent', 'runtime', 'learning'].includes(layer)) {
                  setWorkbench((prev) => ({
                    ...prev,
                    layers: {
                      ...prev.layers,
                      [layer]: {
                        status: ['idle', 'active', 'done', 'error'].includes(nextStatus) ? nextStatus : 'idle',
                        detail: payload.detail || prev.layers[layer].detail,
                        event: payload.event,
                        sourceLayer: payload.source_layer,
                        targetLayer: payload.target_layer,
                        correlationId: payload.correlation_id,
                        cause: payload.cause,
                        metrics: payload.metrics || {},
                        timestamp: payload.timestamp,
                      },
                    },
                  }))
                }
                break
              }
              case 'error': {
                appendEvent('error', payload.message || 'Unknown error', {
                  source,
                  isFail: true,
                })
                setWorkbench((prev) => ({
                  ...prev,
                  stage: payload.fatal || payload.done ? 'error' : prev.stage,
                  lastError: payload.message || 'Unknown error',
                }))
                if (payload.fatal || payload.done) {
                  es.close()
                  isLoadingRef.current = false
                  setLoading(false)
                  setApproval(null)
                  runQueuedNext()
                }
                break
              }
              case 'approval_request': {
                setApproval({
                  actionId: payload.action_id || '',
                  message: payload.message || 'Agent requests approval.',
                })
                setWorkbench((prev) => ({
                  ...prev,
                  stage: 'approval',
                  currentStatus: '等待审批',
                }))
                break
              }
              default: {
                appendEvent(type, JSON.stringify(payload, null, 2), { source })
              }
            }
          } catch (err) {
            console.error('SSE parse error', err, e.data)
          }
        }

        es.onerror = () => {
          if (cancelRequestedRef.current) {
            es.close()
            isLoadingRef.current = false
            cancelRequestedRef.current = false
            setLoading(false)
            setApproval(null)
            runQueuedNext()
            return
          }
          if (isLoadingRef.current) {
            addMessage({ role: 'system', content: 'Connection lost.' })
          }
          setWorkbench((prev) => ({
            ...prev,
            stage: 'error',
            lastError: 'Connection lost.',
          }))
          es.close()
          isLoadingRef.current = false
          setLoading(false)
          setApproval(null)
          runQueuedNext()
        }
      } catch (err: any) {
        addMessage({ role: 'system', content: `Failed to send: ${err.message}` })
        setWorkbench((prev) => ({
          ...prev,
          stage: 'error',
          lastError: err.message,
        }))
        isLoadingRef.current = false
        setLoading(false)
        setApproval(null)
        runQueuedNext()
      }
    },
    [addMessage, setLoading, provider, profile, model, baseUrl, apiKey, onFileTreeRefresh, onUsage, fetchRuntimeContract]
  )

  const sendMessage = useCallback(
    (task: string, displayText?: string) => {
      if (isLoadingRef.current) {
        pendingQueueRef.current.push({ task, displayText })
        setQueueCount(pendingQueueRef.current.length)
        addMessage({ role: 'user', content: displayText || task })
        setWorkbench((prev) => ({
          ...prev,
          currentStatus: `Queued: ${pendingQueueRef.current.length}`,
        }))
        return
      }
      void startTask(task, true, displayText)
    },
    [addMessage, startTask]
  )

  const cancelCurrent = useCallback(async () => {
    const sessionId = sessionIdRef.current
    if (!sessionId || !isLoadingRef.current) return
    cancelRequestedRef.current = true
    setApproval(null)
    setWorkbench((prev) => ({
      ...prev,
      currentStatus: 'Canceling task',
      lastError: '',
    }))
    try {
      const resp = await fetch(`${API_BASE}/sessions/${sessionId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      const data = await resp.json()
      if (!resp.ok || data.error) {
        throw new Error(data.error || `Cancel failed: ${resp.status}`)
      }
    } catch (err: any) {
      cancelRequestedRef.current = false
      addMessage({ role: 'system', content: `Cancel failed: ${err.message}` })
      setWorkbench((prev) => ({
        ...prev,
        lastError: err.message,
      }))
    }
  }, [addMessage])

  const resetConversation = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    isLoadingRef.current = false
    cancelRequestedRef.current = false
    sessionIdRef.current = null
    pendingQueueRef.current = []
    setQueueCount(0)
    setApproval(null)
    setWorkbench(emptyWorkbench)
    setLoading(false)
  }, [setLoading])

  return {
    sendMessage,
    cancelCurrent,
    resetConversation,
    isLoading: isLoadingRef.current,
    approval,
    respondApproval,
    workbench,
    queueCount,
  }
}
