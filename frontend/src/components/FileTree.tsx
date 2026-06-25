import { useCallback, useEffect, useMemo, useState } from 'react'
import { FsItem, useFs } from '../hooks/useFs'

interface FileTreeProps {
  rootPath?: string
  onSelect: (path: string) => void
  onAddToContext?: (path: string, content: string) => void
  onClose?: () => void
  refreshKey?: number
}

interface TreeNodeProps {
  name: string
  path: string
  isDir: boolean
  selectedPath: string
  showHidden: boolean
  onOpen: (path: string) => void
  refreshKey?: number
  depth?: number
}

const TEXT_EXTS = new Set([
  'txt',
  'md',
  'markdown',
  'json',
  'lua',
  'js',
  'jsx',
  'ts',
  'tsx',
  'css',
  'html',
  'xml',
  'yml',
  'yaml',
  'toml',
  'ini',
  'csv',
  'log',
  'gitignore',
])

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'])
const AUDIO_EXTS = new Set(['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'])
const VIDEO_EXTS = new Set(['mp4', 'webm', 'mov', 'mkv'])
const NOISE_DIRS = new Set(['.git', 'node_modules', '.venv', '__pycache__', 'dist', 'build', '.pytest_cache'])

function extensionOf(path: string): string {
  const name = path.split('/').pop() || path
  if (name === '.gitignore') return 'gitignore'
  return name.split('.').pop()?.toLowerCase() || ''
}

function isHiddenItem(name: string): boolean {
  return name.startsWith('.') || NOISE_DIRS.has(name)
}

function isTextFile(path: string): boolean {
  return TEXT_EXTS.has(extensionOf(path))
}

function fileKind(path: string, isDir = false): string {
  if (isDir) return '目录'
  const ext = extensionOf(path)
  if (IMAGE_EXTS.has(ext)) return '图片'
  if (AUDIO_EXTS.has(ext)) return '音频'
  if (VIDEO_EXTS.has(ext)) return '视频'
  if (ext === 'md' || ext === 'markdown') return 'MD'
  if (ext === 'json') return 'JSON'
  if (['lua', 'js', 'jsx', 'ts', 'tsx', 'css', 'html'].includes(ext)) return '代码'
  return TEXT_EXTS.has(ext) ? '文本' : '文件'
}

function fileMark(path: string, isDir = false): string {
  if (isDir) return '□'
  const kind = fileKind(path)
  if (kind === '代码') return '</>'
  return kind.slice(0, 1)
}

function visibleItems(items: FsItem[], showHidden: boolean): FsItem[] {
  if (showHidden) return items
  return items.filter((item) => !isHiddenItem(item.name))
}

function TreeNode({
  name,
  path,
  isDir,
  selectedPath,
  showHidden,
  onOpen,
  refreshKey,
  depth = 0,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 1 && !isHiddenItem(name))
  const [children, setChildren] = useState<FsItem[]>([])
  const [loading, setLoading] = useState(false)
  const { listFiles } = useFs()

  useEffect(() => {
    if (!isDir || !expanded) return
    let cancelled = false
    setLoading(true)
    listFiles(path).then((res) => {
      if (cancelled) return
      setChildren(res.ok && res.items ? visibleItems(res.items, showHidden) : [])
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [expanded, path, listFiles, refreshKey, isDir, showHidden])

  const handleClick = useCallback(() => {
    if (isDir) {
      setExpanded((value) => !value)
    } else {
      onOpen(path)
    }
  }, [isDir, onOpen, path])

  return (
    <div className="resource-tree-node">
      <button
        type="button"
        className={`resource-tree-row ${selectedPath === path ? 'active' : ''}`}
        onClick={handleClick}
        style={{ paddingLeft: 10 + depth * 14 }}
        title={path}
      >
        <span className="resource-tree-caret">{isDir ? (expanded ? '▾' : '▸') : ''}</span>
        <span className={`resource-file-mark ${isDir ? 'is-dir' : ''}`}>{fileMark(path, isDir)}</span>
        <span className="resource-tree-main">
          <span className="resource-tree-name">{name}</span>
        </span>
        <span className={`resource-state-dot ${isDir ? 'is-dir' : isTextFile(path) ? 'is-text' : 'is-media'}`} title={fileKind(path, isDir)} />
      </button>
      {isDir && expanded && (
        <div className="resource-tree-children">
          {loading ? (
            <div className="resource-tree-loading" style={{ paddingLeft: 28 + depth * 14 }}>
              正在读取...
            </div>
          ) : children.length ? (
            children.map((item) => (
              <TreeNode
                key={`${path}/${item.name}`}
                name={item.name}
                path={path ? `${path}/${item.name}` : item.name}
                isDir={item.is_dir}
                selectedPath={selectedPath}
                showHidden={showHidden}
                onOpen={onOpen}
                refreshKey={refreshKey}
                depth={depth + 1}
              />
            ))
          ) : (
            <div className="resource-tree-loading" style={{ paddingLeft: 28 + depth * 14 }}>
              空目录
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function FileTree({
  rootPath = '.',
  onSelect,
  onAddToContext,
  onClose,
  refreshKey,
}: FileTreeProps) {
  const [rootItems, setRootItems] = useState<FsItem[]>([])
  const [localRefresh, setLocalRefresh] = useState(0)
  const [query, setQuery] = useState('')
  const [showHidden, setShowHidden] = useState(false)
  const [selectedPath, setSelectedPath] = useState('')
  const [contextLoading, setContextLoading] = useState(false)
  const [contextError, setContextError] = useState('')
  const { listFiles, readFile } = useFs()

  const triggerKey = refreshKey ?? localRefresh

  useEffect(() => {
    let cancelled = false
    listFiles(rootPath).then((res) => {
      if (cancelled) return
      setRootItems(res.ok && res.items ? res.items : [])
    })
    return () => {
      cancelled = true
    }
  }, [rootPath, listFiles, triggerKey])

  const filteredRootItems = useMemo(() => {
    const text = query.trim().toLowerCase()
    const items = visibleItems(rootItems, showHidden)
    if (!text) return items
    return items.filter((item) => item.name.toLowerCase().includes(text))
  }, [query, rootItems, showHidden])

  const openFile = useCallback((path: string) => {
    setSelectedPath(path)
    setContextError('')
    onSelect(path)
  }, [onSelect])

  const addSelectedToContext = useCallback(async () => {
    if (!selectedPath || !isTextFile(selectedPath)) return
    setContextLoading(true)
    setContextError('')
    const res = await readFile(selectedPath)
    setContextLoading(false)
    if (!res.ok) {
      setContextError(res.error || '读取失败')
      return
    }
    onAddToContext?.(selectedPath, res.content || '')
  }, [onAddToContext, readFile, selectedPath])

  return (
    <div className="file-tree resource-browser resource-browser-files">
      <div className="resource-browser-toolbar">
        <div>
          <strong>项目文件</strong>
        </div>
        <div className="resource-toolbar-actions">
          <button type="button" onClick={() => setLocalRefresh((value) => value + 1)} title="刷新">
            刷新
          </button>
          {onClose && (
            <button type="button" onClick={onClose} title="关闭">
              关闭
            </button>
          )}
        </div>
      </div>
      <div className="resource-search-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索"
        />
      </div>
      <div className="resource-file-filters">
        <button type="button" className={!showHidden ? 'active' : ''} onClick={() => setShowHidden(false)}>
          常用文件
        </button>
        <button type="button" className={showHidden ? 'active' : ''} onClick={() => setShowHidden(true)}>
          显示隐藏
        </button>
      </div>
      <div className="file-tree-body resource-list resource-list-only">
        {filteredRootItems.length ? (
          filteredRootItems.map((item) => (
            <TreeNode
              key={item.name}
              name={item.name}
              path={rootPath === '.' ? item.name : `${rootPath}/${item.name}`}
              isDir={item.is_dir}
              selectedPath={selectedPath}
              showHidden={showHidden}
              onOpen={openFile}
              refreshKey={triggerKey}
            />
          ))
        ) : (
          <div className="resource-empty">当前目录暂无文件</div>
        )}
      </div>
      <div className="resource-file-actionbar">
        <div>
          <strong>{selectedPath || '未选择'}</strong>
          <span>{selectedPath ? fileKind(selectedPath) : '点文件打开'}</span>
          {contextError && <span className="danger">{contextError}</span>}
        </div>
        <button type="button" onClick={() => selectedPath && onSelect(selectedPath)} disabled={!selectedPath}>
          打开
        </button>
        <button
          type="button"
          onClick={addSelectedToContext}
          disabled={!selectedPath || !isTextFile(selectedPath) || contextLoading}
        >
          {contextLoading ? '加入中' : '加入对话'}
        </button>
      </div>
    </div>
  )
}
