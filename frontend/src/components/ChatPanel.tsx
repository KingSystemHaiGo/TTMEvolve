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
  projectName = '未选择项目',
  modelSummary = '模型未选择',
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
        return queueCount > 0 ? `运行中 / 排队 ${queueCount}` : '运行中'
      case 'approval':
        return '等待确认'
      case 'done':
        return '已完成'
      case 'error':
        return '需要处理'
      default:
        return '就绪'
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
          ? `${item.content.slice(0, 24000)}\n\n[已截断，原文件约 ${item.content.length} 字符]`
          : item.content
        return `【文件 ${index + 1}: ${item.path}】\n${content}`
      })
      .join('\n\n')
    const task = `请先阅读这些用户选中的项目文件，再回答或执行用户指令。\n\n${contextText}\n\n【用户指令】\n${visibleText}`
    sendMessage(task, visibleText)
    onClearContextSnippets?.()
  }

  return (
    <div className="chat-panel">
      <div className="chat-context-header" aria-label="当前上下文">
        <div className="chat-context-item">
          <span>项目</span>
          <strong>{projectName}</strong>
        </div>
        <div className="chat-context-item">
          <span>模型</span>
          <strong>{modelSummary}</strong>
        </div>
        <div className="chat-context-item compact">
          <span>配置</span>
          <strong>{configSummary}</strong>
        </div>
      </div>
      <div className="chat-conversation-bar" aria-label="对话操作">
        <div className="chat-conversation-status">
          <span className={`chat-status-dot stage-${workbench.stage}`} />
          <span className={`chat-stage-pill stage-${workbench.stage}`}>{stageLabel}</span>
          {activity && <span className="chat-activity-label">{activity.title}</span>}
        </div>
        <div className="chat-conversation-actions">
          <button className="chat-mini-button" type="button" onClick={startNewConversation}>
            新对话
          </button>
          <button ref={historyButtonRef} className="chat-mini-button" type="button" onClick={toggleHistory}>
            {historyOpen ? '关闭历史' : '历史'}
          </button>
          {onCollapse && (
            <button className="panel-collapse-button" onClick={onCollapse} title="收起 Agent 面板">
              ‹
            </button>
          )}
        </div>
      </div>
      {historyOpen && (
        <div ref={historyRef} className="chat-history-popover">
          <div className="chat-history-head">
            <div>
              <strong>历史对话</strong>
              <span>选择一条记录可带回当前对话；按 Esc 或点击空白处也能关闭。</span>
            </div>
            <button type="button" onClick={() => setHistoryOpen(false)} aria-label="收起历史对话">
              关闭
            </button>
          </div>
          <div className="chat-history-list">
            {historyLoading ? (
              <div className="chat-history-empty">正在读取...</div>
            ) : sessions.length ? (
              sessions.slice(0, 12).map((session) => (
                <button
                  type="button"
                  key={session.session_id || session.task}
                  onClick={() => {
                    addMessage({
                      role: 'system',
                      content: `历史会话：${session.task || session.session_id || '未命名'}\n状态：${sessionStatusLabel(session.status)}\n需要继续时，可以直接描述要接着做什么。`,
                    })
                    setHistoryOpen(false)
                  }}
                >
                  <strong>{session.task || '未命名对话'}</strong>
                  <span>{sessionStatusLabel(session.status)}</span>
                </button>
              ))
            ) : (
              <div className="chat-history-empty">暂无历史对话</div>
            )}
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-title">说说你想做什么</div>
            <p>这里是和 Agent 交流的地方。文件、素材、设置都在下方按钮里，主对话保持干净。</p>
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
          const content = `加入上下文文件：\n${paths.map((path) => `- ${path}`).join('\n')}`
          addMessage({ role: 'system', content })
          sendMessage(content)
        }}
      />

      {contextSnippets.length > 0 && (
        <div className="chat-context-basket" aria-label="已加入上下文的文件">
          <div>
            <strong>已加入下次提问</strong>
            <span>{contextSnippets.length} 个文件会随下一条消息发送给 Agent</span>
          </div>
          <div className="chat-context-list">
            {contextSnippets.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => onRemoveContextSnippet?.(item.id)}
                title="点击移除"
              >
                {item.path}
              </button>
            ))}
          </div>
          <button type="button" className="chat-context-clear" onClick={onClearContextSnippets}>
            清空
          </button>
        </div>
      )}

      <div className="chat-tool-strip" aria-label="辅助工具">
        <button
          type="button"
          className={activeWorkspaceDrawer === 'files' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('files')}
        >
          文件
        </button>
        <button
          type="button"
          className={activeWorkspaceDrawer === 'assets' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('assets')}
        >
          素材
        </button>
        <button
          type="button"
          className={activeWorkspaceDrawer === 'settings' ? 'active' : ''}
          onClick={() => onOpenWorkspaceDrawer?.('settings')}
        >
          设置
        </button>
      </div>

      {approval && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-title">需要你确认</div>
            <div className="modal-body">{approval.message}</div>
            <div className="modal-actions">
              <button className="danger" onClick={() => respondApproval(false)}>
                拒绝
              </button>
              <button className="primary" onClick={() => respondApproval(true)}>
                允许
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
      title: '等待确认',
      detail: 'Agent 需要你确认下一步操作。',
    }
  }
  if (!isLoading && workbench.stage !== 'running') return null
  if (queueCount > 0) {
    return {
      title: '正在排队',
      detail: `已有任务在运行，后续 ${queueCount} 条消息会自动继续。`,
    }
  }
  if (workbench.currentTool) {
    return {
      title: '正在调用工具',
      detail: readableStatus(workbench.currentStatus) || `正在执行 ${workbench.currentTool}`,
    }
  }
  if (workbench.currentThought) {
    return {
      title: '正在思考',
      detail: '模型已经开始分析你的请求，稍后会整理成回答。',
    }
  }
  const status = readableStatus(workbench.currentStatus)
  if (!status) {
    return {
      title: '正在准备',
      detail: 'Agent 正在准备下一步。',
    }
  }
  if (status === '正在选择合适能力' || status.includes('Tool context ranked')) {
    return {
      title: '正在选择合适能力',
      detail: '正在判断下一步该怎么做。',
    }
  }
  if (status.includes('创建会话') || status.includes('连接') || status.includes('验证')) {
    return {
      title: '正在连接模型',
      detail: status,
    }
  }
  if (status.includes('完成') || workbench.finalOutput) {
    return {
      title: '正在整理回答',
      detail: 'Agent 正在把结果整理成可读回复。',
    }
  }
  return {
    title: '正在等待响应',
    detail: status || '请求已发送给模型，正在等待第一段响应。',
  }
}

function readableStatus(value?: string): string {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text.startsWith('候选工具')) return '正在选择合适能力'
  if (text === 'Tool context ranked') return '正在选择合适能力'
  if (text === 'Session created') return '会话已创建，正在等待模型响应。'
  if (text === 'Task finished') return '任务已完成，正在整理最终回复。'
  if (text === 'Canceling task') return '正在停止当前任务。'
  if (text.startsWith('Queued:')) return text.replace('Queued:', '已排队：')
  if (text.startsWith('已排队')) return text
  if (text === 'Runtime contract degraded') return '运行契约部分可用，正在继续处理。'
  if (text === 'Context synced') return '上下文已同步，正在继续。'
  if (text.startsWith('Context synced after')) {
    return text.replace('Context synced after', '工具调用后已同步上下文：')
  }
  return text
}


function sessionStatusLabel(value?: string): string {
  switch (String(value || '').toLowerCase()) {
    case 'done':
      return '已完成'
    case 'running':
      return '运行中'
    case 'error':
      return '异常'
    case 'canceled':
      return '已取消'
    default:
      return value || '未知'
  }
}
