interface CockpitHeaderProps {
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
  makerDestination?: 'maker' | 'forum'
  onToggleMakerDestination?: () => void
  onOpenTools?: () => void
  onOpenMakerSetup?: () => void
}

export default function CockpitHeader({
  makerVersion = '0.0.19',
  mcpStatus,
  makerDestination = 'maker',
  onToggleMakerDestination,
  onOpenTools,
  onOpenMakerSetup,
}: CockpitHeaderProps) {
  const mcpConnected = Boolean(mcpStatus?.connected)

  return (
    <header className="cockpit-header">
      <div className="cockpit-actions">
        {onOpenMakerSetup && (
          <button className="topbar-button primary" type="button" onClick={onOpenMakerSetup}>
            Maker接入
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
        <StatusPill
          label="Maker MCP"
          value={mcpConnected ? `已连接 · ${mcpStatus?.tool_count ?? 0} 个工具` : '未连接'}
          tone={mcpConnected ? 'mint' : 'warning'}
          title={mcpStatus?.last_error || mcpStatus?.remote_identity?.summary || `@taptap/maker ${makerVersion}`}
        />
      </div>
    </header>
  )
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
