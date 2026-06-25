import { useMemo } from 'react'
import type { Provider } from '../App'

interface CockpitHeaderProps {
  provider: Provider
  profile?: string
  projectRoot?: string
  makerVersion?: string
  mcpStatus?: {
    connected?: boolean
    tool_count?: number
    remote_identity?: {
      status?: string
      summary?: string
      missing?: string[]
      last_call_id_fields?: string[]
    }
    last_error?: string | null
    last_call?: {
      tool?: string
      ok?: boolean
      elapsed_ms?: number
      error?: string
    } | null
  } | null
  makerSetup?: {
    readiness?: string
    blockers?: string[]
    warnings?: string[]
    project?: {
      root?: string
      maker_initialized?: boolean
      project_id?: string
    }
    auth?: {
      tap_auth_present?: boolean
      pat_present?: boolean
    }
    tool_audit?: {
      ok?: boolean
      remote_tool_count?: number
    }
  } | null
  makerDestination?: 'maker' | 'forum'
  onToggleMakerDestination?: () => void
  onOpenTools?: () => void
  onOpenMakerSetup?: () => void
  health?: {
    status?: string
    provider?: string
    runtime_kind?: string
    model?: string
    base_url?: string
    api_key_set?: boolean
    llm_class?: string
    llm_configured?: boolean
    model_exists?: boolean
    llama_cpp_available?: boolean
    model_path?: string
    llm_loaded?: boolean
    last_call_stats?: {
      total_tokens?: number
      tokens_per_sec?: number
      generate_ms?: number
      mode?: string
      endpoint?: string
      http_status?: number
      request_id?: string
    }
    last_probe?: {
      ok?: boolean
      elapsed_ms?: number
      last_call_stats?: {
        total_tokens?: number
        tokens_per_sec?: number
        generate_ms?: number
        endpoint?: string
        http_status?: number
        error_type?: string
      }
    }
  } | null
  usage?: {
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
  } | null
  agentRunning?: boolean
  runElapsedMs?: number
}

export default function CockpitHeader({
  provider,
  profile = 'default',
  projectRoot = '.',
  makerVersion = '0.0.19',
  mcpStatus,
  makerSetup,
  makerDestination = 'maker',
  onToggleMakerDestination,
  onOpenTools,
  onOpenMakerSetup,
  health,
  usage,
  agentRunning = false,
  runElapsedMs,
}: CockpitHeaderProps) {
  const projectName = useMemo(() => {
    const root = makerSetup?.project?.root || projectRoot || '.'
    const normalized = root.replace(/\\/g, '/').replace(/\/$/, '')
    return normalized.split('/').pop() || root
  }, [makerSetup?.project?.root, projectRoot])

  const mcpConnected = Boolean(mcpStatus?.connected)
  const setupReady = makerSetup?.readiness === 'ready'
  const isApiRuntime = health?.runtime_kind === 'api'
  const runtimeReady = isApiRuntime
    ? health?.llm_configured !== false && health?.api_key_set !== false
    : Boolean(health?.model_exists && health?.llama_cpp_available)
  const liveTotalTokens = usage?.total_tokens
  const healthTotalTokens = health?.last_call_stats?.total_tokens
  const probeStats = health?.last_probe?.last_call_stats
  const probeTotalTokens = probeStats?.total_tokens
  const contextTokens = usage?.token_count
  const tokenValue = liveTotalTokens !== undefined
    ? `${liveTotalTokens} token`
    : contextTokens !== undefined
      ? `上下文 ${contextTokens}`
      : agentRunning
        ? '统计中'
        : healthTotalTokens !== undefined
          ? `${healthTotalTokens} token`
          : probeTotalTokens !== undefined
            ? `${probeTotalTokens} token`
            : '暂无调用'
  const liveLatency = usage?.generate_ms
  const healthLatency = health?.last_call_stats?.generate_ms
  const probeLatency = probeStats?.generate_ms ?? health?.last_probe?.elapsed_ms
  const latencyValue = liveLatency !== undefined
    ? formatDuration(liveLatency)
    : agentRunning && runElapsedMs !== undefined
      ? `等待 ${formatDuration(runElapsedMs)}`
      : healthLatency !== undefined
        ? formatDuration(healthLatency)
        : probeLatency !== undefined
          ? formatDuration(probeLatency)
          : '等待中'
  const usageTitle = [
    usage?.endpoint || health?.last_call_stats?.endpoint || probeStats?.endpoint,
    usage?.phase ? `phase=${usage.phase}` : '',
    usage?.tokens_per_sec !== undefined
      ? `${usage.tokens_per_sec} tok/s`
      : probeStats?.tokens_per_sec !== undefined
        ? `${probeStats.tokens_per_sec} tok/s`
        : '',
    usage?.error_type || probeStats?.error_type ? `错误=${usage?.error_type || probeStats?.error_type}` : '',
  ].filter(Boolean).join(' | ')

  return (
    <header className="cockpit-header">
      <div className="cockpit-actions">
        {onOpenMakerSetup && (
          <button className="topbar-button primary" type="button" onClick={onOpenMakerSetup}>
            Maker 接入
          </button>
        )}
        {onOpenTools && (
          <button className="topbar-button" type="button" onClick={onOpenTools}>
            可用工具
          </button>
        )}
        {onToggleMakerDestination && (
          <button className="topbar-button" type="button" onClick={onToggleMakerDestination}>
            {makerDestination === 'forum' ? '回到 Maker' : '制造论坛'}
          </button>
        )}
      </div>

      <div className="cockpit-status" aria-label="运行状态">
        <StatusPill label="项目" value={projectName} tone={setupReady ? 'mint' : 'warning'} />
        <StatusPill
          label="Maker MCP"
          value={mcpConnected ? `已连接 · ${mcpStatus?.tool_count ?? 0} 工具` : '未连接'}
          tone={mcpConnected ? 'mint' : 'warning'}
          title={mcpStatus?.last_error || mcpStatus?.remote_identity?.summary || `@taptap/maker ${makerVersion}`}
        />
        <StatusPill
          label="模型"
          value={`${health?.provider || provider} · ${health?.model || '未选择'}`}
          tone={runtimeReady ? 'blue' : 'warning'}
          title={health?.base_url || health?.model_path || ''}
        />
        <StatusPill label="Token" value={tokenValue} tone="neutral" title={usageTitle} />
        <StatusPill label="耗时" value={latencyValue} tone="neutral" title={usageTitle} />
        <StatusPill label="配置" value={profile} tone="neutral" />
      </div>
    </header>
  )
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value)) return '等待中'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

function StatusPill({
  label,
  value,
  tone,
  title,
}: {
  label: string
  value: string
  tone: 'mint' | 'blue' | 'neutral' | 'warning'
  title?: string
}) {
  return (
    <div className={`status-pill status-pill-${tone}`} title={title}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
