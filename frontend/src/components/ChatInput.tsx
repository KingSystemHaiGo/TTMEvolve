import { useEffect, useRef, useState } from 'react'

interface Props {
  onSend: (text: string) => void
  onAttachFiles?: (paths: string[]) => void
  onCancel?: () => void
  disabled?: boolean
  isLoading?: boolean
  queueCount?: number
  permissionProfile?: string
  onPermissionProfileChange?: (profile: string) => void
}

export default function ChatInput({
  onSend,
  onAttachFiles,
  onCancel,
  disabled = false,
  isLoading = false,
  queueCount = 0,
  permissionProfile = 'default',
  onPermissionProfileChange,
}: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!disabled) inputRef.current?.focus()
  }, [disabled, isLoading])

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  const handleAttach = async () => {
    const electronFiles = (window as any).electronAPI?.files
    if (electronFiles?.openDialog) {
      const paths = await electronFiles.openDialog()
      if (Array.isArray(paths) && paths.length > 0) {
        onAttachFiles?.(paths)
      }
      return
    }
    fileInputRef.current?.click()
  }

  const handleWebFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return
    onAttachFiles?.(Array.from(files).map((file) => file.name))
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="chat-input">
      <button
        className="chat-add-button"
        type="button"
        disabled={disabled}
        aria-label="添加上下文文件 / Add context files"
        title="添加上下文文件 / Add context files"
        onClick={handleAttach}
      >
        +
      </button>
      <input
        ref={fileInputRef}
        className="chat-file-input"
        type="file"
        multiple
        onChange={(event) => handleWebFiles(event.target.files)}
      />
      <input
        ref={inputRef}
        type="text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => event.key === 'Enter' && handleSend()}
        disabled={disabled}
        placeholder={isLoading ? '继续输入，会自动排队... / Keep typing, it will queue...' : '提出目标、问题，或直接开始做游戏... / Ask or start building...'}
      />
      <select
        className="chat-permission-select"
        value={permissionProfile}
        onChange={(event) => onPermissionProfileChange?.(event.target.value)}
        title="选择 Agent 本次会话可使用的最大权限 / Select max permission for this session"
        aria-label="权限模式 / Permission mode"
        disabled={disabled || isLoading}
      >
        <option value="safe">只读 / Read-only</option>
        <option value="default">默认 / Default</option>
        <option value="autonomous">自动 / Autonomous</option>
      </select>
      {isLoading && onCancel && (
        <button className="chat-stop-button" type="button" onClick={onCancel}>
          停止 / Stop
        </button>
      )}
      <button className="chat-send-button" onClick={handleSend} disabled={disabled || !text.trim()}>
        {isLoading ? '排队 / Queue' : '发送 / Send'}{queueCount > 0 ? ` ${queueCount}` : ''}
      </button>
    </div>
  )
}
