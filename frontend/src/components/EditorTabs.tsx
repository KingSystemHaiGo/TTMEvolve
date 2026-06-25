import { useCallback, useMemo } from 'react'
import Editor from '@monaco-editor/react'

interface EditorTabsProps {
  openFiles: string[]
  activePath: string
  contents: Record<string, string>
  modified: Set<string>
  onSelect: (path: string) => void
  onClose: (path: string) => void
  onChange: (path: string, value: string) => void
  onSave: (path: string) => void
}

function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase()
  const map: Record<string, string> = {
    js: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    jsx: 'javascript',
    py: 'python',
    json: 'json',
    md: 'markdown',
    html: 'html',
    css: 'css',
    yaml: 'yaml',
    yml: 'yaml',
  }
  return map[ext ?? ''] || 'plaintext'
}

export default function EditorTabs({
  openFiles,
  activePath,
  contents,
  modified,
  onSelect,
  onClose,
  onChange,
  onSave,
}: EditorTabsProps) {
  const activeContent = contents[activePath] ?? ''
  const language = useMemo(() => detectLanguage(activePath), [activePath])

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      if (activePath && value !== undefined) {
        onChange(activePath, value)
      }
    },
    [activePath, onChange]
  )

  const handleEditorMount = useCallback(
    (editor: any, monaco: any) => {
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        if (activePath) onSave(activePath)
      })
    },
    [activePath, onSave]
  )

  return (
    <div className="editor-tabs">
      <div className="editor-tabs-bar">
        {openFiles.length === 0 && (
          <div className="editor-tab-empty">未打开文件</div>
        )}
        {openFiles.map((path) => (
          <div
            key={path}
            className={`editor-tab ${path === activePath ? 'active' : ''}`}
            onClick={() => onSelect(path)}
          >
            <span className="editor-tab-name">
              {modified.has(path) ? '● ' : ''}
              {path.split('/').pop()}
            </span>
            <button
              className="editor-tab-close"
              onClick={(e) => {
                e.stopPropagation()
                onClose(path)
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="editor-tabs-content">
        {activePath ? (
          <Editor
            height="100%"
            language={language}
            value={activeContent}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              wordWrap: 'on',
              automaticLayout: true,
            }}
            onChange={handleEditorChange}
            onMount={handleEditorMount}
          />
        ) : (
          <div className="editor-empty">从左侧文件树选择一个文件开始编辑</div>
        )}
      </div>
    </div>
  )
}
