import { MouseEvent, useEffect, useRef, useState } from 'react'
import { useBrowser } from '../hooks/useBrowser'
import { isTauri, openExternalUrl } from '../lib/tauri'

const PREVIEW_URL_KEY = 'ttmevolve.preview.url'
const MAKER_DEFAULT_URL = 'https://maker.taptap.cn/'

interface BrowserPreviewProps {
  initialUrl?: string
}

interface MakerBrowserApi {
  show: () => Promise<unknown>
  hide: () => Promise<unknown>
  setBounds: (rect: { x: number; y: number; width: number; height: number }) => Promise<unknown>
  navigate: (url: string) => Promise<unknown>
  reload: () => Promise<unknown>
  setDarkMode?: (enabled: boolean, options?: { reload?: boolean }) => Promise<unknown>
}

function electronMakerBrowser(): MakerBrowserApi | null {
  return ((window as any).electronAPI?.makerBrowser as MakerBrowserApi | undefined) || null
}

function savedPreviewUrl(initialUrl: string): string {
  return localStorage.getItem(PREVIEW_URL_KEY) || initialUrl
}

function isMakerUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.hostname.endsWith('taptap.cn')
  } catch {
    return false
  }
}

export default function BrowserPreview({ initialUrl = '' }: BrowserPreviewProps) {
  const nativeBrowser = electronMakerBrowser()
  if (nativeBrowser) {
    return <NativeBrowserPreview initialUrl={initialUrl} api={nativeBrowser} />
  }
  if (isTauri()) {
    return <TauriWebPreview initialUrl={initialUrl} />
  }
  return <ScreenshotBrowserPreview initialUrl={initialUrl} />
}

function TauriWebPreview({ initialUrl }: BrowserPreviewProps) {
  const firstUrl = savedPreviewUrl(initialUrl || MAKER_DEFAULT_URL)
  const [url, setUrl] = useState(firstUrl)
  const [mode, setMode] = useState<'diagnostic' | 'iframe'>('diagnostic')
  const [openError, setOpenError] = useState('')
  const makerUrl = isMakerUrl(url)

  useEffect(() => {
    localStorage.setItem(PREVIEW_URL_KEY, url)
  }, [url])

  const openExternal = async () => {
    setOpenError('')
    try {
      await openExternalUrl(url)
    } catch (err) {
      setOpenError(String(err))
    }
  }

  return (
    <div className="browser-preview tauri-browser-preview">
      <div className="tauri-browser-topbar">
        <span>{mode === 'diagnostic' ? '诊断预览' : '网页预览'}</span>
        <button type="button" onClick={() => setUrl(MAKER_DEFAULT_URL)}>
          Maker
        </button>
        <button type="button" onClick={openExternal}>
          外部打开
        </button>
        <button
          type="button"
          onClick={() => setMode((current) => (current === 'diagnostic' ? 'iframe' : 'diagnostic'))}
        >
          {mode === 'diagnostic' ? '尝试内嵌' : '诊断预览'}
        </button>
      </div>

      {openError && <div className="browser-error">{openError}</div>}

      {mode === 'diagnostic' ? (
        <div className="tauri-diagnostic-preview">
          {makerUrl && (
            <div className="tauri-preview-notice">
              <strong>Maker 页面拒绝内嵌</strong>
              <span>
                TapTap Maker 不允许在 Tauri iframe 中直接打开。请用“外部打开”进入完整 Maker 页面；下方诊断预览用于查看截图和基本交互状态。
              </span>
            </div>
          )}
          <ScreenshotBrowserPreview initialUrl={url} />
        </div>
      ) : (
        <iframe
          className="tauri-browser-frame"
          src={url}
          title="TapTap Maker preview"
          onLoad={() => localStorage.setItem(PREVIEW_URL_KEY, url)}
        />
      )}
    </div>
  )
}

function NativeBrowserPreview({ initialUrl, api }: { initialUrl: string; api: MakerBrowserApi }) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let frame = 0
    const syncBounds = () => {
      const host = hostRef.current
      if (!host) return
      const rect = host.getBoundingClientRect()
      api.setBounds({
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      }).catch((err) => setError(String(err)))
    }
    const schedule = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(syncBounds)
    }

    api.show().then(schedule).catch((err) => setError(String(err)))
    const firstUrl = savedPreviewUrl(initialUrl)
    if (firstUrl) {
      api.navigate(firstUrl).catch((err) => setError(String(err)))
    }

    const resizeObserver = new ResizeObserver(schedule)
    if (hostRef.current) resizeObserver.observe(hostRef.current)
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)

    return () => {
      window.cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      window.removeEventListener('resize', schedule)
      window.removeEventListener('scroll', schedule, true)
      api.hide().catch(() => undefined)
    }
  }, [api, initialUrl])

  return (
    <div className="browser-preview native-browser-preview">
      {error && <div className="browser-error">{error}</div>}
      <div ref={hostRef} className="native-browser-host">
        <div className="native-browser-label">Maker 预览</div>
      </div>
    </div>
  )
}

function ScreenshotBrowserPreview({ initialUrl = '' }: BrowserPreviewProps) {
  const {
    info,
    screenshot,
    error,
    navigate,
    clickAt,
    startPolling,
    stopPolling,
  } = useBrowser()

  const [hasLoadedPage, setHasLoadedPage] = useState(false)
  const [isClicking, setIsClicking] = useState(false)
  const imageRef = useRef<HTMLImageElement | null>(null)

  useEffect(() => {
    startPolling()
    return () => stopPolling()
  }, [startPolling, stopPolling])

  useEffect(() => {
    const firstUrl = savedPreviewUrl(initialUrl)
    if (!firstUrl) return
    setHasLoadedPage(true)
    navigate(firstUrl)
  }, [initialUrl, navigate])

  const handlePreviewClick = async (event: MouseEvent<HTMLImageElement>) => {
    const image = imageRef.current
    if (!image || !screenshot?.ok || !info?.viewport) return
    const rect = image.getBoundingClientRect()
    const x = ((event.clientX - rect.left) / rect.width) * info.viewport.width
    const y = ((event.clientY - rect.top) / rect.height) * info.viewport.height
    setIsClicking(true)
    try {
      await clickAt(x, y)
    } finally {
      setIsClicking(false)
    }
  }

  return (
    <div className="browser-preview">
      {error && hasLoadedPage && <div className="browser-error">{error}</div>}

      <div className={`browser-screenshot ${isClicking ? 'is-clicking' : ''}`}>
        {hasLoadedPage && screenshot?.ok && screenshot.data ? (
          <img
            ref={imageRef}
            src={screenshot.data}
            alt={info?.title || info?.url || '浏览器预览'}
            onClick={handlePreviewClick}
            draggable={false}
          />
        ) : (
          <div className="browser-placeholder">
            <p>正在打开 Maker 诊断预览</p>
            <p className="browser-muted">如果站点拒绝内嵌，请使用右上角“外部打开”。</p>
          </div>
        )}
      </div>
    </div>
  )
}
