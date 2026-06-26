import { useEffect, useRef, useState } from 'react'
import ChatInput from './ChatInput'
import ChatMessage from './ChatMessage'
import { useBackend, type LlmUsagePayload } from '../hooks/useBackend'
import type { ContextSnippet, Message, Provider, ProviderPreset, WorkspaceDrawerKind } from '../App'

interface Props {
  messages: Message[]
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => void
  provider: Provider
  onProviderChange: (provider: Provider) => void
  providerPresets?: ProviderPreset[]
  model?: string
  baseUrl?: string
  apiKey?: string
  apiKeySet?: boolean
  onModelChange?: (value: string) => void
  onBaseUrlChange?: (value: string) => void
  onApiKeyChange?: (value: string) => void
  onApiKeySetChange?: (value: boolean) => void
  configLoading?: boolean
  onFileTreeRefresh?: () => void
  onCollapse?: () => void
  onOpenWorkspaceDrawer?: (kind: WorkspaceDrawerKind) => void
  activeWorkspaceDrawer?: WorkspaceDrawerKind | null
  onClearMessages?: () => void
  contextSnippets?: ContextSnippet[]
  onRemoveContextSnippet?: (id: string) => void
  onClearContextSnippets?: () => void
  onUsage?: (usage: LlmUsagePayload) => void
  onRunningChange?: (running: boolean) => void
  permissionProfile?: string
  onPermissionProfileChange?: (profile: string) => void
  projectName?: string
  modelSummary?: string
  configSummary?: string
}

interface SessionSummary {
  session_id?: string
  task?: string
  status?: string
  updated_at?: number
}

export default function ChatPanel({
  messages,
  addMessage,
  provider,
  model = '',
  baseUrl = '',
  apiKey = '',
  onFileTreeRefresh,
  onCollapse,
  onOpenWorkspaceDrawer,
  activeWorkspaceDrawer,
  onClearMessages,
  contextSnippets = [],
  onRemoveContextSnippet,
  onClearContextSnippets,
  onUsage,
  onRunningChange,
  permissionProfile = 'default',
  onPermissionProfileChange,
  projectName = '未选择项目 / No project',
  modelSummary = '模型未选择 / No model',
  configSummary = 'default',
}: Props) {
  const [isLoading, setIsLoading] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const historyRef = useRef<HTMLDivElement>(null)
  const historyButtonRef = useRef<HTMLButtonElement>(null)

  const setPanelLoading = (loading: boolean) => {
    setIsLoading(loading)
    onRunningChange?.(loading)
  }

  const { sendMessage, cancelCurrent, resetConversation, approval, respondApproval, workbench, queueCount } = useBackend(
    addMessage,
    setPanelLoading,
    provider,
    model,
    baseUrl,
    apiKey,
    permissionProfile,
    onFileTreeRefresh,
    onUsage
  )

  const startNewConversation = () => {
    resetConversation()
    onClearMessages?.()
    setHistoryOpen(false)
  }

  const toggleHistory = async () => {
    const nextOpen = !historyOpen
    setHistoryOpen(nextOpen)
    if (!nextOpen) return
    setHistoryLoading(true)
    try {
      const response = await fetch('http://127.0.0.1:7345/sessions')
      const data = await response.json()
      setSessions(Array.isArray(data.sessions) ? data.sessions : [])
    } catch {
      setSessions([])
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (!historyOpen) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null
      if (!target) return
      if (historyRef.current?.contains(target)) return
      if (historyButtonRef.current?.contains(target)) return
      setHistoryOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHistoryOpen(false)
    }
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [historyOpen])

  const stageLabel = (() => {
    switch (workbench.stage) {
      case 'running':
        return queueCount > 0 ? `运行中 / Queue ${queueCount}` : '运行中 / Running'
      case 'approval':
        return '等待确认 / Approval'
      case 'done':
        return '已完成 / Done'
      case 'error':
        return '需要处理 / Needs action'
      default:
        return '就绪 / Ready'
    }
  })()

  const activity = currentActivityLabel(workbench, isLoading, queueCount)

  const sendWithContext = (text: string) => {
    const visibleText = text.trim()
    if (!contextSnippets.length) {
      sendMessage(visibleText)
      return
    }
    const contextText = contextSnippets
      .map((item, index) => {
        const content = item.content.length > 24000
          ? `${item.content.slice(0, 24000)}\n\n[已截断 / Truncated, original length ${item.content.length} chars]`
          : item.content
        return `[File ${index + 1}: ${item.path}]\n${content}`
      })
      .join('\n\n')
    const task = `请先阅读这些用户选中的项目文件，再回答或执行用户指令。\n\n${contextText}\n\n[用户指令 / User request]\n${visibleText}`
    sendMessage(task, visibleText)
    onClearContextSnippets?.()
  }

  return (
    <div className="chat-panel">
      <div className="chat-context-header" aria-label="当前上下文 / Current context">
        <div className="chat-context-item">
          <span>项目 / Project</span>
          <strong>{projectName}</strong>
        </div>
        <div className="chat-context-item">
          <span>模型 / Model</span>
          <strong>{modelSummary}</strong>
        </div>
        <div className="chat-context-item compact">
          <span>配置 / Config</span>
          <strong>{configSummary}</strong>
        </div>
      </div>

      <div className="chat-conversation-bar" aria-label="对话操作 / Conversation actions">
        <div className="chat-conversation-status">
          <span className={`chat-status-dot stage-${workbench.stage}`} />
          <span className={`chat-stage-pill stage-${workbench.stage}`}>{stageLabel}</span>
          {activity && <span className="chat-activity-label">{activity.title}</span>}
        </div>
        <div className="chat-conversation-actions">
          <button className="chat-mini-button" type="button" onClick={startNewConversation}>
            新对话 / New
          </button>
          <button ref={historyButtonRef} className="chat-mini-button" type="button" onClick={toggleHistory}>
            {historyOpen ? '关闭历史 / Close' : '历史 / History'}
          </button>
          {onCollapse && (
            <button className="panel-collapse-button" onClick={onCollapse} title="收起 Agent 面板 / Collapse Agent panel">
              -
            </button>
          )}
        </div>
      </div>

      {historyOpen && (
        <div ref={historyRef} className="chat-history-popover">
          <div className="chat-history-head">
            <div>
              <strong>历史对话 / History</strong>
              <span>按 Esc、点击空白处，或点右上角 X 关闭。/ Esc, outside click, or X closes this panel.</span>
            </div>
            <button
              type="button"
              className="chat-history-close"
              onClick={() => setHistoryOpen(false)}
              aria-label="关闭历史对话 / Close history"
              title="关闭历史 / Close history"
            >
              x
            </button>
          </div>
          <div className="chat-history-list">
            {historyLoading ? (
              <div className="chat-history-empty">正在读取 / Loading...</div>
            ) : sessions.length ? (
              sessions.slice(0, 12).map((session) => (
                <button
                  type="button"
                  key={session.session_id || session.task}
                  onClick={() => {
                    addMessage({
                      role: 'system',
                      content: `历史会话 / History: ${session.task || session.session_id || '未命名 / Untitled'}\n状态 / Status: ${sessionStatusLabel(session.status)}\n需要继续时，直接描述要接着做什么。/ To continue, describe the next step.`,
                    })
                    setHistoryOpen(false)
                  }}
                >
                  <strong>{session.task || '未命名对话 / Untitled'}</strong>
                  <span>{sessionStatusLabel(session.status)}</span>
                </button>
              ))
            ) : (
              <div className="chat-history-empty">暂无历史对话 / No history yet</div>
            )}
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-title">说说你想做什么 / What should we do?</div>
            <p>主对话只显示用户可读的回答和关键进度；候选工具、调试细节放在 Workbench。/ The main chat stays user-facing; internal tool ranking lives in Workbench.</p>
          </div>
        )}
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
        {activity && (
          <div className="assistant-working" aria-live="polite">
            <div className="assistant-working-head">
              <span className="assistant-working-pulse" />
              <strong>{activity.title}</strong>
              <span className="assistant-working-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
            <div className="assistant-working-detail">{activity.detail}</div>
          </div>
        )}
      </div>

      <ChatInput
        onSend={sendWithContext}
        onCancel={cancelCurrent}
        isLoading={isLoading}
        queueCount={queueCount}
        permissionProfile={permissionProfile}
        onPermissionProfileChange={onPermissionProfileChange}
        onAttachFiles={(paths) => {
          const content = `加入上下文文件 / Added context files:\n${paths.map((path) => `- ${path}`).join('\n')}`
          addMessage({ role: 'system', content })
          sendMessage(content)
        }}
      />

      {contextSnippets.length > 0 && (
        <div className="chat-context-basket" aria-label="已加入上下文的文件 / Context files">
          <div>
            <strong>已加入下次提问 / Added to next message</strong>
            <span>{contextSnippets.length} 个文件会随下一条消息发送给 Agent / files queued</span>
          </div>
          <div className="chat-context-list">
            {contextSnippets.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => onRemoveContextSnippet?.(item.id)}
                title="点击移除 / Remove"
              >
                {item.path}
              </button>
            ))}
          </div>
          <button type="button" className="chat-context-clear" onClick={onClearContextSnippets}>
            清空 / Clear
          </button>
        </div>
      )}

      <div className="chat-tool-strip" aria-label="辅助工具 / Auxiliary tools">
        <button
          type="button"
          className={activeWorkspaceDrawer === 'files' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('files')}
        >
          文件 / Files
        </button>
        <button
          type="button"
          className={activeWorkspaceDrawer === 'assets' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('assets')}
        >
          素材 / Assets
        </button>
        <button
          type="button"
          className={activeWorkspaceDrawer === 'settings' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('settings')}
        >
          设置 / Settings
        </button>
      </div>

      {approval && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-title">需要你确认 / Approval required</div>
            <div className="modal-body">{approval.message}</div>
            <div className="modal-actions">
              <button className="danger" onClick={() => respondApproval(false)}>
                拒绝 / Deny
              </button>
              <button className="primary" onClick={() => respondApproval(true)}>
                允许 / Allow
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function currentActivityLabel(
  workbench: ReturnType<typeof useBackend>['workbench'],
  isLoading: boolean,
  queueCount: number
): { title: string; detail: string } | null {
  if (workbench.stage === 'approval') {
    return {
      title: '等待确认 / Approval needed',
      detail: 'Agent 需要你确认下一步操作。/ The agent needs approval before continuing.',
    }
  }
  if (!isLoading && workbench.stage !== 'running') return null
  if (queueCount > 0) {
    return {
      title: '正在排队 / Queued',
      detail: `已有任务在运行，后续 ${queueCount} 条消息会自动继续。/ ${queueCount} message(s) will run next.`,
    }
  }
  if (workbench.currentTool) {
    return {
      title: '正在调用工具 / Running tool',
      detail: readableStatus(workbench.currentStatus) || `正在执行 / Running ${workbench.currentTool}`,
    }
  }
  if (workbench.currentThought) {
    return {
      title: '正在思考 / Thinking',
      detail: '模型已经开始分析请求，稍后会整理成回答。/ The model is reasoning and will respond shortly.',
    }
  }
  const status = readableStatus(workbench.currentStatus)
  if (!status) {
    return {
      title: '正在准备 / Preparing',
      detail: 'Agent 正在准备下一步。/ Preparing the next step.',
    }
  }
  if (/tool[_\s-]?selection|candidate|候选工具|可选工具|工具筛选|Tool context ranked/i.test(status)) {
    return {
      title: '正在判断下一步 / Choosing next action',
      detail: '内部候选工具已移到 Workbench，主对话只显示可读进度。/ Tool ranking stays in Workbench.',
    }
  }
  if (/Session created|会话/.test(status)) {
    return {
      title: '正在连接模型 / Connecting model',
      detail: status,
    }
  }
  if (/Task finished|完成/.test(status) || workbench.finalOutput) {
    return {
      title: '正在整理回答 / Preparing answer',
      detail: 'Agent 正在把结果整理成可读回复。/ Preparing the final response.',
    }
  }
  return {
    title: '正在等待响应 / Waiting',
    detail: status,
  }
}

function readableStatus(value?: string): string {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/tool[_\s-]?selection|candidate|候选工具|可选工具|工具筛选|Tool context ranked/i.test(text)) {
    return '正在判断下一步 / Choosing next action'
  }
  if (text === 'Session created') return '会话已创建，正在等待模型响应。/ Session created, waiting for model.'
  if (text === 'Task finished') return '任务已完成，正在整理最终回复。/ Task finished, preparing response.'
  if (text === 'Canceling task') return '正在停止当前任务。/ Canceling current task.'
  if (text.startsWith('Queued:')) return text.replace('Queued:', '已排队 / Queued:')
  if (text === 'Runtime contract degraded') return '运行契约部分可用，正在继续处理。/ Runtime contract degraded but usable.'
  if (text === 'Context synced') return '上下文已同步，正在继续。/ Context synced.'
  if (text.startsWith('Context synced after')) {
    return text.replace('Context synced after', '工具调用后已同步上下文 / Context synced after')
  }
  return text
}

function sessionStatusLabel(value?: string): string {
  switch (String(value || '').toLowerCase()) {
    case 'done':
      return '已完成 / Done'
    case 'running':
      return '运行中 / Running'
    case 'error':
      return '异常 / Error'
    case 'canceled':
      return '已取消 / Canceled'
    default:
      return value || '未知 / Unknown'
  }
}
