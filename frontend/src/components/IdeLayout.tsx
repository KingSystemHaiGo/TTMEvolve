import { useCallback, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'
import EditorTabs from './EditorTabs'
import PreviewPane from './PreviewPane'

interface IdeLayoutProps {
  rootPath?: string
  activePath: string
  openFiles: string[]
  contents: Record<string, string>
  modified: Set<string>
  onFileSelect: (path: string) => void
  onFileChange: (path: string, value: string) => void
  onFileClose: (path: string) => void
  onFileSave: (path: string) => void
  refreshKey?: number
}

const EDITOR_WIDTH_KEY = 'ttmevolve.ide.editor.width'
const MIN_EDITOR_WIDTH = 360
const MAX_EDITOR_WIDTH = 620
const HANDLE_WIDTH = 8

function savedEditorWidth(): number {
  const value = Number(localStorage.getItem(EDITOR_WIDTH_KEY))
  if (!Number.isFinite(value) || value <= 0) return 440
  return Math.min(MAX_EDITOR_WIDTH, Math.max(MIN_EDITOR_WIDTH, value))
}

export default function IdeLayout({
  activePath,
  openFiles,
  contents,
  modified,
  onFileSelect,
  onFileChange,
  onFileClose,
  onFileSave,
}: IdeLayoutProps) {
  const [editorWidth, setEditorWidth] = useState(savedEditorWidth)
  const [editorOpen, setEditorOpen] = useState(true)
  const hasOpenFile = openFiles.length > 0
  const showEditor = hasOpenFile && editorOpen

  const gridTemplateColumns = useMemo(
    () => showEditor
      ? `minmax(0, 1fr) ${HANDLE_WIDTH}px ${editorWidth}px`
      : 'minmax(0, 1fr)',
    [editorWidth, showEditor]
  )

  const startEditorResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = editorWidth
    const onMove = (moveEvent: PointerEvent) => {
      const next = Math.min(
        MAX_EDITOR_WIDTH,
        Math.max(MIN_EDITOR_WIDTH, startWidth - (moveEvent.clientX - startX))
      )
      setEditorWidth(next)
      localStorage.setItem(EDITOR_WIDTH_KEY, String(Math.round(next)))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.classList.remove('is-resizing')
    }
    document.body.classList.add('is-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [editorWidth])

  return (
    <div className="ide-layout ide-layout-stage preview-only-layout" style={{ gridTemplateColumns }}>
      <div className="ide-stage">
        <PreviewPane activePath={activePath} content={contents[activePath] ?? ''} />
        {hasOpenFile && !showEditor && (
          <button className="editor-reopen-button" type="button" onClick={() => setEditorOpen(true)}>
            打开代码
          </button>
        )}
      </div>

      {showEditor && (
        <>
          <div
            className="ide-resize-handle"
            onPointerDown={startEditorResize}
            title="调整代码面板宽度"
          />
          <div className="ide-editor">
            <div className="editor-dock-head">
              <strong>代码</strong>
              <button type="button" onClick={() => setEditorOpen(false)}>收起</button>
            </div>
            <EditorTabs
              openFiles={openFiles}
              activePath={activePath}
              contents={contents}
              modified={modified}
              onSelect={onFileSelect}
              onClose={onFileClose}
              onChange={onFileChange}
              onSave={onFileSave}
            />
          </div>
        </>
      )}
    </div>
  )
}
