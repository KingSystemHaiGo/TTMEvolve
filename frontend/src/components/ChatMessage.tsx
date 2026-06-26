import { marked } from 'marked'
import { Message } from '../App'

interface Props {
  message: Message
}

export default function ChatMessage({ message }: Props) {
  const time = new Date(message.timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  if (message.role === 'event') {
    const eventType = message.eventType || 'unknown'
    const summary = eventSummary(eventType, message.content, message.isFail)
    return (
      <div className={`event event-${eventType}${message.isFail ? ' fail' : ''}`}>
        <span className="event-dot" />
        <span className="event-summary">{summary}</span>
        <span className="event-time">{time}</span>
        {message.isFail && (
          <details className="event-details">
            <summary>查看详情</summary>
            <pre>{message.content}</pre>
          </details>
        )}
      </div>
    )
  }

  if (message.role === 'user') {
    return (
      <div className="message-row message-row-user">
        <div className="user-bubble">
          <div className="user-bubble-content">{message.content}</div>
          <div className="user-bubble-time">{time}</div>
        </div>
      </div>
    )
  }

  if (message.role === 'assistant') {
    return (
      <article className="assistant-answer">
        <div className="assistant-answer-meta">
          <span>Agent</span>
          <time>{time}</time>
        </div>
        <div
          className="assistant-markdown"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
        />
        {message.usage && <MessageUsageBar usage={message.usage} />}
      </article>
    )
  }

  return (
    <div className={`message message-${message.role}`}>
      <div className="message-header">
        <span className="message-role">{roleLabel(message.role)}</span>
        <span className="message-time">{time}</span>
      </div>
      <div className="message-content">{message.content}</div>
    </div>
  )
}

function MessageUsageBar({ usage }: { usage: NonNullable<Message['usage']> }) {
  const items = [
    usage.total_tokens !== undefined ? `Token ${usage.total_tokens}` : '',
    usage.token_count !== undefined ? `上下文 ${usage.token_count}` : '',
    usage.generate_ms !== undefined ? `耗时 ${formatDuration(usage.generate_ms)}` : '',
    usage.tokens_per_sec !== undefined ? `${usage.tokens_per_sec} tok/s` : '',
    usage.endpoint || '',
  ].filter(Boolean)

  if (!items.length) return null
  return (
    <div className="assistant-answer-usage" title={usage.error_type || usage.mode || usage.phase || ''}>
      {items.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </div>
  )
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value)) return '等待中'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

function roleLabel(role: Message['role']): string {
  switch (role) {
    case 'user':
      return '你'
    case 'assistant':
      return 'Agent'
    case 'system':
      return '系统'
    case 'event':
      return '事件'
    default:
      return role
  }
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    status: '正在处理',
    thinking: '正在思考',
    decision: '下一步',
    action: '准备动作',
    tool_call: '正在调用工具',
    observation: '工具返回',
    error: '出错了',
    approval_request: '等待确认',
    rescue_triggered: '触发修复',
    rescue_action: '正在修复',
    rescue_applied: '修复完成',
    rescue_distilled: '经验沉淀',
    unknown: '事件',
  }
  return map[type] || type
}

function eventSummary(type: string, content: string, isFail?: boolean): string {
  if (isFail) return `${eventLabel(type)}失败`
  if (type === 'tool_call') {
    const firstLine = content.split('\n').map((line) => line.trim()).find(Boolean)
    return firstLine ? `正在调用工具：${firstLine}` : '正在调用工具'
  }
  if (type === 'observation') return '工具调用完成'
  if (type === 'action') return compactLine(content) || '准备下一步'
  return compactLine(content) || eventLabel(type)
}

function compactLine(content: string): string {
  return content
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 72)
}

function renderMarkdown(content: string): string {
  return marked.parse(escapeHtml(content), {
    async: false,
    breaks: true,
    gfm: true,
  }) as string
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
