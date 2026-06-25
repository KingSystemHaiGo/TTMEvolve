import { useEffect, useMemo, useState } from 'react'
import { AssetItem, AssetType, useAssets } from '../hooks/useAssets'
import { useFs } from '../hooks/useFs'

const API_BASE = 'http://127.0.0.1:7345'

interface AssetLibraryProps {
  rootPath?: string
  onSelect: (path: string) => void
  onAddToContext?: (path: string, content: string) => void
  onClose?: () => void
  refreshKey?: number
}

type AssetCategory = 'all' | 'image' | 'audio' | 'video' | 'document'
type ViewMode = 'grid' | 'list'

const CATEGORY_META: Array<{
  id: AssetCategory
  label: string
  extensions?: string
}> = [
  { id: 'all', label: '全部' },
  { id: 'image', label: '图片' },
  { id: 'audio', label: '音频' },
  { id: 'video', label: '视频' },
  { id: 'document', label: '文档', extensions: '.md,.json,.txt,.lua,.css,.js,.ts,.tsx,.html,.xml,.yml,.yaml' },
]

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function extensionOf(path: string): string {
  return path.split('.').pop()?.toLowerCase() || ''
}

function assetLabel(type: AssetType, path: string): string {
  if (type === 'image') return '图片'
  if (type === 'audio') return '音频'
  if (type === 'video') return '视频'
  const ext = extensionOf(path)
  if (ext === 'md') return 'Markdown'
  if (ext === 'json') return 'JSON'
  if (['lua', 'js', 'ts', 'tsx', 'css', 'html'].includes(ext)) return '代码'
  return '文档'
}

function assetInitial(type: AssetType, path: string): string {
  return assetLabel(type, path).slice(0, 1)
}

function isDocument(asset: AssetItem): boolean {
  return asset.type === 'unknown'
}

function AssetPreview({ asset }: { asset: AssetItem }) {
  const src = `${API_BASE}/preview/file?path=${encodeURIComponent(asset.path)}`
  if (asset.type === 'image') return <img src={src} alt={asset.name} />
  if (asset.type === 'audio') return <audio src={src} controls />
  if (asset.type === 'video') return <video src={src} controls />
  return <span>{assetInitial(asset.type, asset.path)}</span>
}

export default function AssetLibrary({
  rootPath = '.',
  onSelect,
  onAddToContext,
  onClose,
  refreshKey,
}: AssetLibraryProps) {
  const [assets, setAssets] = useState<AssetItem[]>([])
  const [loading, setLoading] = useState(false)
  const [category, setCategory] = useState<AssetCategory>('all')
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [selectedPath, setSelectedPath] = useState('')
  const [readerText, setReaderText] = useState('')
  const [readerError, setReaderError] = useState('')
  const { listAssets } = useAssets()
  const { readFile } = useFs()

  const categoryMeta = CATEGORY_META.find((item) => item.id === category) || CATEGORY_META[0]

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listAssets(rootPath, categoryMeta.extensions).then((res) => {
      if (cancelled) return
      const nextAssets = res.ok && res.assets ? res.assets : []
      setAssets(nextAssets)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [rootPath, listAssets, refreshKey, categoryMeta.extensions])

  const filteredAssets = useMemo(() => {
    const text = query.trim().toLowerCase()
    const byCategory = category === 'all'
      ? assets
      : category === 'document'
        ? assets.filter((asset) => isDocument(asset))
        : assets.filter((asset) => asset.type === category)
    if (!text) return byCategory
    return byCategory.filter((asset) =>
      asset.name.toLowerCase().includes(text) || asset.path.toLowerCase().includes(text)
    )
  }, [assets, category, query])

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.path === selectedPath) || null,
    [assets, selectedPath]
  )

  const selectAsset = async (asset: AssetItem) => {
    setSelectedPath(asset.path)
    setReaderText('')
    setReaderError('')
    if (!isDocument(asset)) return
    const res = await readFile(asset.path)
    if (res.ok) {
      setReaderText(res.content || '')
    } else {
      setReaderError(res.error || '读取失败')
    }
  }

  return (
    <div className="asset-library resource-browser">
      <div className="resource-browser-toolbar">
        <div>
          <strong>素材库</strong>
        </div>
        <div className="resource-toolbar-actions">
          <button type="button" onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}>
            {viewMode === 'grid' ? '列表' : '网格'}
          </button>
          {onClose && (
            <button type="button" onClick={onClose} title="关闭">
              关闭
            </button>
          )}
        </div>
      </div>
      <div className="asset-category-rail">
        {CATEGORY_META.map((item) => (
          <button
            type="button"
            key={item.id}
            className={category === item.id ? 'active' : ''}
            onClick={() => setCategory(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="resource-search-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索素材名称或路径"
        />
      </div>
      <div className="asset-library-body">
        <div className={`asset-collection ${viewMode}`}>
          {loading ? (
            <div className="resource-empty">正在扫描素材...</div>
          ) : filteredAssets.length ? (
            filteredAssets.map((asset) => (
              <button
                type="button"
                className={`asset-card ${selectedPath === asset.path ? 'active' : ''}`}
                key={asset.path}
                onClick={() => void selectAsset(asset)}
                title={asset.path}
              >
                <span className="asset-thumb">
                  <AssetPreview asset={asset} />
                </span>
                <span className="asset-card-main">
                  <strong>{asset.name}</strong>
                  <small>{assetLabel(asset.type, asset.path)} · {formatSize(asset.size)}</small>
                </span>
              </button>
            ))
          ) : (
            <div className="resource-empty">当前分类没有素材</div>
          )}
        </div>
        <div className="asset-inspector">
          {selectedAsset ? (
            <>
              <div className="asset-inspector-head">
                <div>
                  <strong title={selectedAsset.path}>{selectedAsset.name}</strong>
                  <span>{selectedAsset.path}</span>
                </div>
                <button type="button" onClick={() => onSelect(selectedAsset.path)}>
                  打开
                </button>
              </div>
              <div className="asset-inspector-preview">
                {isDocument(selectedAsset) ? (
                  readerError ? (
                    <div className="resource-empty danger">{readerError}</div>
                  ) : (
                    <pre>{readerText || '正在读取文档...'}</pre>
                  )
                ) : (
                  <AssetPreview asset={selectedAsset} />
                )}
              </div>
              {isDocument(selectedAsset) && !readerError && (
                <button
                  type="button"
                  className="asset-context-button"
                  onClick={() => onAddToContext?.(selectedAsset.path, readerText)}
                  disabled={!readerText}
                >
                  加入对话上下文
                </button>
              )}
            </>
          ) : (
            <div className="resource-empty">选择一个素材查看详情。</div>
          )}
        </div>
      </div>
    </div>
  )
}
