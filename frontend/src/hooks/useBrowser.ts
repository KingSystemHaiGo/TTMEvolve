import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE = 'http://127.0.0.1:7345'

export interface BrowserInfo {
  ok: boolean
  url?: string
  title?: string
  loading?: boolean
  viewport?: { width: number; height: number }
  error?: string
}

export interface BrowserLog {
  type: string
  text: string
  location?: Record<string, unknown>
  time?: number
}

export interface BrowserLogsResult {
  ok: boolean
  logs?: BrowserLog[]
  error?: string
}

export interface ScreenshotResult {
  ok: boolean
  data?: string
  mime?: string
  error?: string
}

async function postJson(path: string, body: Record<string, unknown>) {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return resp.json()
}

async function getJson(path: string) {
  const resp = await fetch(`${API_BASE}${path}`)
  return resp.json()
}

export function useBrowser() {
  const [info, setInfo] = useState<BrowserInfo | null>(null)
  const [screenshot, setScreenshot] = useState<ScreenshotResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<number | null>(null)

  const clearPoll = useCallback(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const fetchScreenshot = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/browser/screenshot`)
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        setScreenshot({ ok: false, error: data.error || `HTTP ${resp.status}` })
        return
      }
      const blob = await resp.blob()
      const reader = new FileReader()
      reader.onloadend = () => {
        setScreenshot({
          ok: true,
          data: reader.result as string,
          mime: resp.headers.get('Content-Type') || 'image/jpeg',
        })
      }
      reader.readAsDataURL(blob)
    } catch (e) {
      setScreenshot({ ok: false, error: String(e) })
    }
  }, [])

  const fetchInfo = useCallback(async () => {
    try {
      const data: BrowserInfo = await getJson('/browser/info')
      setInfo(data)
      if (!data.ok && data.error) {
        setError(data.error)
      }
    } catch (e) {
      setInfo({ ok: false, error: String(e) })
    }
  }, [])

  const startPolling = useCallback(() => {
    clearPoll()
    fetchScreenshot()
    fetchInfo()
    intervalRef.current = window.setInterval(() => {
      fetchScreenshot()
      fetchInfo()
    }, 5000)
  }, [clearPoll, fetchScreenshot, fetchInfo])

  const stopPolling = useCallback(() => {
    clearPoll()
  }, [clearPoll])

  useEffect(() => {
    return () => clearPoll()
  }, [clearPoll])

  const navigate = useCallback(async (url: string) => {
    setError(null)
    try {
      const data = await postJson('/browser/navigate', { url })
      if (!data.ok) {
        setError(data.error || '导航失败')
        return data
      }
      await fetchInfo()
      await fetchScreenshot()
      return data
    } catch (e) {
      const err = String(e)
      setError(err)
      return { ok: false, error: err }
    }
  }, [fetchInfo, fetchScreenshot])

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const data = await postJson('/browser/refresh', {})
      if (!data.ok) setError(data.error || '刷新失败')
      await fetchInfo()
      await fetchScreenshot()
      return data
    } catch (e) {
      const err = String(e)
      setError(err)
      return { ok: false, error: err }
    }
  }, [fetchInfo, fetchScreenshot])

  const evaluate = useCallback(async (script: string) => {
    setError(null)
    try {
      const data = await postJson('/browser/evaluate', { script })
      if (!data.ok) setError(data.error || '执行失败')
      return data
    } catch (e) {
      const err = String(e)
      setError(err)
      return { ok: false, error: err }
    }
  }, [])

  const click = useCallback(async (selector: string) => {
    setError(null)
    try {
      const data = await postJson('/browser/click', { selector })
      if (!data.ok) setError(data.error || '点击失败')
      return data
    } catch (e) {
      const err = String(e)
      setError(err)
      return { ok: false, error: err }
    }
  }, [])

  const clickAt = useCallback(async (x: number, y: number) => {
    setError(null)
    try {
      const data = await postJson('/browser/click_at', { x, y })
      if (!data.ok) setError(data.error || '点击失败')
      window.setTimeout(() => {
        void fetchInfo()
        void fetchScreenshot()
      }, 350)
      return data
    } catch (e) {
      const err = String(e)
      setError(err)
      return { ok: false, error: err }
    }
  }, [fetchInfo, fetchScreenshot])

  return {
    info,
    screenshot,
    error,
    navigate,
    refresh,
    evaluate,
    click,
    clickAt,
    startPolling,
    stopPolling,
    fetchInfo,
    fetchScreenshot,
  }
}
