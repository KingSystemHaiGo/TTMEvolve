import { MouseEvent, useEffect, useRef, useState } from 'react'
import { useBrowser } from '../hooks/useBrowser'

const PREVIEW_URL_KEY = 'ttmevolve.preview.url'

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

export default function BrowserPreview({ initialUrl = '' }: BrowserPreviewProps) {
  const nativeBrowser = electronMakerBrowser()
  if (nativeBrowser) {
    return <NativeBrowserPreview initialUrl={initialUrl} api={nativeBrowser} />
  }
  return <ScreenshotBrowserPreview initialUrl={initialUrl} />
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
            <p>正在打开 Maker 预览</p>
            <p className="browser-muted">页面加载后可直接点击预览区域。</p>
          </div>
        )}
      </div>
    </div>
  )
}
