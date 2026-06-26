import { useState, useCallback, useEffect, useMemo, useRef, type PointerEvent as ReactPointerEvent } from 'react'
import ChatPanel from './components/ChatPanel'
import AssetLibrary from './components/AssetLibrary'
import CockpitHeader from './components/CockpitHeader'
import ElectronTitleBar from './components/ElectronTitleBar'
import FileTree from './components/FileTree'
import IdeLayout from './components/IdeLayout'
import ProviderSelector from './components/ProviderSelector'
import { useFs } from './hooks/useFs'
import { isTauri, makerPreviewNavigate, openExternalUrl } from './lib/tauri'
import './styles/index.css'

export type MessageRole = 'user' | 'assistant' | 'system' | 'event'

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  eventType?: string
  source?: string
  isFail?: boolean
  usage?: MessageUsage
}

export type Provider = string
export type WorkspaceDrawerKind = 'files' | 'assets' | 'tools' | 'settings' | 'maker'

export interface MessageUsage {
  phase?: string
  provider?: string
  mode?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  token_count?: number
  generate_ms?: number
  tokens_per_sec?: number
  endpoint?: string
  http_status?: number
  error_type?: string
  updated_at?: number
}

export interface ProviderPreset {
  id: string
  label: string
  kind: string
  base_url: string
  model: string
  env_var?: string
}

export interface ContextSnippet {
  id: string
  path: string
  content: string
}

interface LiveUsage {
  phase?: string
  provider?: string
  mode?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  token_count?: number
  generate_ms?: number
  tokens_per_sec?: number
  endpoint?: string
  http_status?: number
  error_type?: string
  updated_at?: number
}

const API_BASE = 'http://127.0.0.1:7345'
const MAKER_HOME_URL = 'https://maker.taptap.cn/'
const MAKER_FORUM_URL = 'https://www.taptap.cn/app/810249/topic'
const PREVIEW_URL_KEY = 'ttmevolve.preview.url'
const CHAT_LAYOUT_KEY = 'ttmevolve.chat.width'
const CHAT_COLLAPSED_KEY = 'ttmevolve.chat.collapsed'
const WORKSPACE_PAGE_WIDTH_KEY = 'ttmevolve.workspace.page.width'
const THEME_KEY = 'ttmevolve.theme'
const MIN_CHAT_WIDTH = 420
const MAX_CHAT_WIDTH = 760
const DEFAULT_CHAT_WIDTH = 560
const WORKSPACE_DRAWER_WIDTH = 340
const MIN_WORKSPACE_PAGE_WIDTH = 360
const MAX_WORKSPACE_PAGE_WIDTH = 720
const DEFAULT_WORKSPACE_PAGE_WIDTH = 420

interface AppConfig {
  provider?: Provider
  model?: string
  base_url?: string
  api_key_set?: boolean
  profile?: string
  project_root?: string
  maker_mcp?: {
    args?: string[]
  }
}

interface HealthInfo {
  status?: string
  provider?: string
  runtime_kind?: string
  model?: string
  base_url?: string
  api_key_set?: boolean
  llm_class?: string
  llm_configured?: boolean
  model_exists?: boolean
  llama_cpp_available?: boolean
  model_path?: string
  llm_loaded?: boolean
  llm_params?: {
    n_ctx?: number
    n_gpu_layers?: number
    n_batch?: number
    n_ubatch?: number
    n_threads?: number
    n_threads_batch?: number
    offload_kqv?: boolean
    flash_attn?: boolean
    cache_type_k?: string
    cache_type_v?: string
    kv_cache?: boolean
    notes?: string[]
  }
  last_call_stats?: {
    total_tokens?: number
    tokens_per_sec?: number
    generate_ms?: number
    mode?: string
    endpoint?: string
    http_status?: number
    request_id?: string
  }
  last_probe?: {
    ok?: boolean
    provider?: string
    runtime_kind?: string
    llm_class?: string
    model?: string
    base_url?: string
    elapsed_ms?: number
    error?: string
    output_preview?: string
    last_call_stats?: {
      endpoint?: string
      total_tokens?: number
      generate_ms?: number
      error_type?: string
    }
  }
}

interface McpStatus {
  connected?: boolean
  tool_count?: number
  probe?: MakerMcpProbe
  remote_identity?: {
    status?: string
    summary?: string
    missing?: string[]
    last_call_id_fields?: string[]
  }
  last_error?: string | null
  last_call?: {
    tool?: string
    ok?: boolean
    elapsed_ms?: number
    error?: string
  } | null
}

interface MakerMcpProbe {
  ok?: boolean
  connected?: boolean
  tool_count?: number
  tools_preview?: string[]
  source?: string
  checked_at?: number
  elapsed_ms?: number
  probe_check?: string
  error?: string
}

interface MakerSetupStatus {
  readiness?: 'ready' | 'degraded' | 'blocked' | string
  blockers?: string[]
  warnings?: string[]
  project?: {
    root?: string
    is_app_root?: boolean
    maker_initialized?: boolean
    project_id?: string
    project_bound?: boolean
  }
  agent_root_mcp?: {
    registered?: boolean
    registered_count?: number
    target_count?: number
  }
  auth?: {
    tap_auth_present?: boolean
    pat_present?: boolean
  }
  maker_package?: {
    configured?: string
    latest?: string | null
    npx_available?: boolean
    latest_check?: string
    update_available?: boolean | null
    checked_at?: number
    latest_error?: string
  }
  mcp_probe?: MakerMcpProbe
  tool_audit?: {
    ok?: boolean
    remote_tool_count?: number
    missing_required_proxy_tools?: string[]
  }
  commands?: {
    recommended_next?: string
  }
}

interface MakerPracticeLog {
  kind?: string
  text?: string
  time?: number
}

interface MakerPracticeStatus {
  version?: string
  running?: boolean
  status?: string
  step?: string
  project_dir?: string
  auth_url?: string
  awaiting_input?: boolean
  prompt?: string
  exit_code?: number | null
  error?: string
  logs?: MakerPracticeLog[]
}

interface ToolItem {
  name?: string
  source?: string
  description?: string
  registered?: boolean
  executor_handler?: boolean
  remote_exposed?: boolean
  required_proxy?: boolean
}

const MEDIA_EXTS = new Set([
  'png',
  'jpg',
  'jpeg',
  'gif',
  'svg',
  'webp',
  'bmp',
  'ico',
  'mp3',
  'wav',
  'ogg',
  'flac',
  'aac',
  'm4a',
  'mp4',
  'webm',
  'mov',
  'mkv',
])

function isMediaPath(path: string): boolean {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  return MEDIA_EXTS.has(ext)
}

function appBootPending(
  configLoading: boolean,
  health: HealthInfo | null,
  makerSetup: MakerSetupStatus | null,
  mcpStatus: McpStatus | null,
  startedAt: number,
  now: number
): boolean {
  if (now - startedAt > 45000) return false
  return configLoading || !health || !makerSetup || !mcpStatus
}

function bootStatusText(
  configLoading: boolean,
  health: HealthInfo | null,
  makerSetup: MakerSetupStatus | null,
  mcpStatus: McpStatus | null,
  startedAt: number,
  now: number
): string {
  if (configLoading) return '正在读取本地配置和模型设置...'
  if (!health) return '正在等待 Python App Server 健康检查...'
  if (health.status === 'offline') return '后端暂时离线，正在重试连接...'
  if (!makerSetup) return '正在检查 Maker 项目、授权和工具安装状态...'
  if (!mcpStatus) return '正在检查 Maker MCP 连接和远程工具...'
  const seconds = Math.max(1, Math.round((now - startedAt) / 1000))
  return `已检查 ${seconds} 秒，正在进入工作台...`
}

function makerNeedsAttention(
  makerSetup: MakerSetupStatus | null,
  mcpStatus: McpStatus | null,
  toolAudit: any
): boolean {
  if (!makerSetup || !mcpStatus) return false
  if (makerSetup.readiness && makerSetup.readiness !== 'ready') return true
  if (Array.isArray(makerSetup.blockers) && makerSetup.blockers.length > 0) return true
  if (mcpStatus.connected === false) return true
  if ((mcpStatus.tool_count ?? 0) <= 2) return true
  if (toolAudit?.ok === false) return true
  if (Array.isArray(toolAudit?.missing_required_proxy_tools) && toolAudit.missing_required_proxy_tools.length > 0) return true
  return false
}

function savedClampedWidth(): number {
  const saved = Number(localStorage.getItem(CHAT_LAYOUT_KEY))
  if (!Number.isFinite(saved) || saved <= 0) return DEFAULT_CHAT_WIDTH
  return Math.min(MAX_CHAT_WIDTH, Math.max(MIN_CHAT_WIDTH, saved))
}

function savedWorkspacePageWidth(): number {
  const saved = Number(localStorage.getItem(WORKSPACE_PAGE_WIDTH_KEY))
  if (!Number.isFinite(saved) || saved <= 0) return DEFAULT_WORKSPACE_PAGE_WIDTH
  return Math.min(MAX_WORKSPACE_PAGE_WIDTH, Math.max(MIN_WORKSPACE_PAGE_WIDTH, saved))
}

function projectNameFromPath(path?: string): string {
  const root = path || '.'
  const normalized = root.replace(/\\/g, '/').replace(/\/$/, '')
  return normalized.split('/').pop() || root
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [provider, setProvider] = useState<Provider>('local')
  const [providerPresets, setProviderPresets] = useState<ProviderPreset[]>([])
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiKeySet, setApiKeySet] = useState(false)
  const [configLoading, setConfigLoading] = useState(true)
  const [profile, setProfile] = useState('default')
  const [projectRoot, setProjectRoot] = useState('.')
  const [makerVersion, setMakerVersion] = useState('0.0.19')
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [mcpStatus, setMcpStatus] = useState<McpStatus | null>(null)
  const [makerSetup, setMakerSetup] = useState<MakerSetupStatus | null>(null)
  const [makerPractice, setMakerPractice] = useState<MakerPracticeStatus | null>(null)
  const [chatWidth, setChatWidth] = useState(savedClampedWidth)
  const [chatCollapsed, setChatCollapsed] = useState(
    () => localStorage.getItem(CHAT_COLLAPSED_KEY) === 'true'
  )
  const [workspaceDrawer, setWorkspaceDrawer] = useState<WorkspaceDrawerKind | null>(null)
  const [workspacePage, setWorkspacePage] = useState<WorkspaceDrawerKind | null>(null)
  const [workspacePageWidth, setWorkspacePageWidth] = useState(savedWorkspacePageWidth)
  const [toolsLoading, setToolsLoading] = useState(false)
  const [tools, setTools] = useState<ToolItem[]>([])
  const [toolsError, setToolsError] = useState('')
  const [toolAudit, setToolAudit] = useState<any>(null)
  const [lastAutoAuditProject, setLastAutoAuditProject] = useState('')
  const [makerDestination, setMakerDestination] = useState<'maker' | 'forum'>('maker')
  const [makerRepairing, setMakerRepairing] = useState(false)
  const [pendingMakerRepairAudit, setPendingMakerRepairAudit] = useState(false)
  const [makerIssueAutoOpened, setMakerIssueAutoOpened] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  )
  const [contextSnippets, setContextSnippets] = useState<ContextSnippet[]>([])
  const [bootStartedAt] = useState(() => Date.now())
  const [bootNow, setBootNow] = useState(() => Date.now())

  const [openFiles, setOpenFiles] = useState<string[]>([])
  const [activePath, setActivePath] = useState('')
  const [contents, setContents] = useState<Record<string, string>>({})
  const [modified, setModified] = useState<Set<string>>(new Set())
  const [refreshKey, setRefreshKey] = useState(0)

  const { readFile, writeFile } = useFs()
  const latestAnswerUsageRef = useRef<MessageUsage | null>(null)

  const navigateMakerPreview = useCallback(async (url: string) => {
    const targetUrl = String(url || '').trim()
    if (!targetUrl) return
    localStorage.setItem(PREVIEW_URL_KEY, targetUrl)

    const makerBrowser = (window as any).electronAPI?.makerBrowser
    if (makerBrowser?.navigate) {
      await makerBrowser.navigate(targetUrl)
      return
    }

    if (isTauri()) {
      await makerPreviewNavigate(targetUrl).catch((err) => {
        console.warn('Maker preview is not ready yet; saved URL for next mount.', err)
      })
      return
    }

    await openExternalUrl(targetUrl)
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setBootNow(Date.now()), 500)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const loadConfig = () => {
      attempts += 1
      fetch(`${API_BASE}/config`)
        .then((res) => res.json())
        .then((data: AppConfig) => {
          if (cancelled) return
          if (data.provider) setProvider(data.provider)
          setModel(data.model || '')
          setBaseUrl(data.base_url || '')
          setApiKeySet(Boolean(data.api_key_set))
          if (data.profile) setProfile(data.profile)
          if (data.project_root) setProjectRoot(data.project_root)
          const makerPackage = data.maker_mcp?.args?.find((arg) => arg.startsWith('@taptap/maker@'))
          if (makerPackage) setMakerVersion(makerPackage.replace('@taptap/maker@', ''))
          setConfigLoading(false)
        })
        .catch((err) => {
          console.error('Failed to load config:', err)
          if (cancelled) return
          if (attempts < 80) {
            window.setTimeout(loadConfig, 1500)
          } else {
            setConfigLoading(false)
          }
        })
    }
    loadConfig()
    return () => {
      cancelled = true
    }
  }, [])

  const loadMakerSetup = useCallback((checkLatest = false) => {
    const suffix = checkLatest ? '?check_latest=true' : ''
    return fetch(`${API_BASE}/maker/setup-status${suffix}`)
      .then((res) => res.json())
      .then((data: MakerSetupStatus) => {
        setMakerSetup(data)
        return data
      })
      .catch(() => {
        const fallback = { readiness: 'blocked', blockers: ['backend_offline'] }
        setMakerSetup(fallback)
        return fallback
      })
  }, [])

  useEffect(() => {
    void loadMakerSetup(false)
    const timer = window.setInterval(() => void loadMakerSetup(false), 10000)
    return () => window.clearInterval(timer)
  }, [loadMakerSetup])

  const loadMakerPractice = useCallback(() => {
    return fetch(`${API_BASE}/maker/practice/status`)
      .then((res) => res.json())
      .then((data: MakerPracticeStatus) => {
        setMakerPractice(data)
        return data
      })
      .catch(() => {
        const fallback = { status: 'offline', running: false, logs: [] }
        setMakerPractice(fallback)
        return fallback
      })
  }, [])

  useEffect(() => {
    void loadMakerPractice()
    const timer = window.setInterval(() => void loadMakerPractice(), 1500)
    return () => window.clearInterval(timer)
  }, [loadMakerPractice])

  const openMakerHome = useCallback(async () => {
    await navigateMakerPreview(MAKER_HOME_URL)
    setMakerDestination('maker')
  }, [navigateMakerPreview])

  const openMakerForum = useCallback(async () => {
    await navigateMakerPreview(MAKER_FORUM_URL)
    setMakerDestination('forum')
  }, [navigateMakerPreview])

  const toggleMakerDestination = useCallback(() => {
    if (makerDestination === 'forum') {
      void openMakerHome()
    } else {
      void openMakerForum()
    }
  }, [makerDestination, openMakerForum, openMakerHome])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
    const makerBrowser = (window as any).electronAPI?.makerBrowser
    if (makerBrowser?.setDarkMode) {
      void makerBrowser.setDarkMode(theme === 'dark', { reload: true })
    }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }, [])

  const selectMakerProject = useCallback(async () => {
    const files = (window as any).electronAPI?.files
    const paths = files?.openDirectory ? await files.openDirectory() : []
    const path = Array.isArray(paths) ? paths[0] : ''
    if (!path) return
    const response = await fetch(`${API_BASE}/maker/project/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, create: true }),
    })
    const data = await response.json()
    if (data?.setup_status) {
      setMakerSetup(data.setup_status)
      const nextRoot = data.setup_status.project?.root
      if (nextRoot) setProjectRoot(nextRoot)
    } else {
      void loadMakerSetup(false)
    }
  }, [loadMakerSetup])

  const startMakerInstall = useCallback(async () => {
    const selectedRoot = makerSetup?.project?.root || projectRoot
    const hasSelectedRoot = selectedRoot && selectedRoot !== '.' && !makerSetup?.project?.is_app_root
    const response = await fetch(`${API_BASE}/maker/practice/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(hasSelectedRoot ? { path: selectedRoot } : { project_name: 'smoke-maker-game' }),
        skip_install: false,
        skip_init: true,
      }),
    })
    const data = await response.json()
    if (data?.setup_status) setMakerSetup(data.setup_status)
    if (data?.status) setMakerPractice(data.status)
    void loadMakerSetup(false)
    void loadMakerPractice()
  }, [loadMakerPractice, loadMakerSetup, makerSetup?.project?.is_app_root, makerSetup?.project?.root, projectRoot])

  const startMakerInit = useCallback(async () => {
    const selectedRoot = makerSetup?.project?.root || projectRoot
    const hasSelectedRoot = selectedRoot && selectedRoot !== '.' && !makerSetup?.project?.is_app_root
    const response = await fetch(`${API_BASE}/maker/practice/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(hasSelectedRoot ? { path: selectedRoot } : { project_name: 'smoke-maker-game' }),
        skip_install: true,
        skip_init: false,
        app_selection: '0',
      }),
    })
    const data = await response.json()
    if (data?.setup_status) setMakerSetup(data.setup_status)
    if (data?.status) setMakerPractice(data.status)
    void loadMakerSetup(false)
    void loadMakerPractice()
  }, [loadMakerPractice, loadMakerSetup, makerSetup?.project?.is_app_root, makerSetup?.project?.root, projectRoot])

  const cancelMakerPractice = useCallback(async () => {
    const response = await fetch(`${API_BASE}/maker/practice/cancel`, { method: 'POST' })
    const data = await response.json()
    if (data?.status) setMakerPractice(data.status)
    void loadMakerSetup(false)
  }, [loadMakerSetup])

  const openMakerAuth = useCallback(async (url: string) => {
    const authUrl = String(url || '').trim()
    if (!authUrl) return
    await fetch(`${API_BASE}/maker/auth/prepare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auth_url: authUrl }),
    }).catch(() => undefined)
    await navigateMakerPreview(authUrl)
  }, [navigateMakerPreview])

  useEffect(() => {
    fetch(`${API_BASE}/llm/providers`)
      .then((res) => res.json())
      .then((data: { providers?: ProviderPreset[] }) => setProviderPresets(data.providers || []))
      .catch((err) => console.error('Failed to load providers:', err))
  }, [])

  useEffect(() => {
    let cancelled = false
    const loadHealth = () => {
      fetch(`${API_BASE}/health`)
        .then((res) => res.json())
        .then((data: HealthInfo) => {
          if (!cancelled) setHealth(data)
        })
        .catch(() => {
          if (!cancelled) setHealth({ status: 'offline' })
        })
    }
    loadHealth()
    const timer = window.setInterval(loadHealth, 8000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const loadMcpStatus = () => {
      fetch(`${API_BASE}/mcp/status?probe=false`)
        .then((res) => res.json())
        .then((data: McpStatus) => {
          if (!cancelled) setMcpStatus(data)
        })
        .catch(() => {
          if (!cancelled) setMcpStatus({ connected: false, tool_count: 0, last_error: 'offline' })
        })
    }
    loadMcpStatus()
    const timer = window.setInterval(loadMcpStatus, 8000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const addMessage = useCallback((msg: Omit<Message, 'id' | 'timestamp'>) => {
    setMessages((prev) => [
      ...prev,
      {
        ...msg,
        usage: msg.usage || (msg.role === 'assistant' ? latestAnswerUsageRef.current || undefined : undefined),
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
      },
    ])
  }, [])

  const handleAgentUsage = useCallback((usage: LiveUsage) => {
    const next = { ...usage, updated_at: Date.now() }
    latestAnswerUsageRef.current = {
      ...(latestAnswerUsageRef.current || {}),
      ...next,
      token_count: next.token_count ?? latestAnswerUsageRef.current?.token_count,
      total_tokens: next.total_tokens ?? latestAnswerUsageRef.current?.total_tokens,
      generate_ms: next.generate_ms ?? latestAnswerUsageRef.current?.generate_ms,
      tokens_per_sec: next.tokens_per_sec ?? latestAnswerUsageRef.current?.tokens_per_sec,
      endpoint: next.endpoint || latestAnswerUsageRef.current?.endpoint,
      http_status: next.http_status ?? latestAnswerUsageRef.current?.http_status,
      error_type: next.error_type || latestAnswerUsageRef.current?.error_type,
    }
    setMessages((prev) => {
      const reverseIndex = [...prev].reverse().findIndex((message) => message.role === 'assistant')
      if (reverseIndex < 0) return prev
      const targetIndex = prev.length - 1 - reverseIndex
      return prev.map((message, index) =>
        index === targetIndex
          ? { ...message, usage: latestAnswerUsageRef.current || undefined }
          : message
      )
    })
    if (next.total_tokens !== undefined || next.generate_ms !== undefined || next.endpoint) {
      setHealth((prev) => prev
        ? {
            ...prev,
            last_call_stats: {
              ...(prev.last_call_stats || {}),
              total_tokens: next.total_tokens ?? prev.last_call_stats?.total_tokens,
              generate_ms: next.generate_ms ?? prev.last_call_stats?.generate_ms,
              tokens_per_sec: next.tokens_per_sec ?? prev.last_call_stats?.tokens_per_sec,
              endpoint: next.endpoint || prev.last_call_stats?.endpoint,
              http_status: next.http_status ?? prev.last_call_stats?.http_status,
            },
          }
        : prev
      )
    }
  }, [])

  const handleAgentRunningChange = useCallback((running: boolean) => {
    if (running) {
      latestAnswerUsageRef.current = null
    }
  }, [])

  const handleFileSelect = useCallback(
    async (path: string) => {
      if (isMediaPath(path)) {
        setActivePath(path)
        return
      }
      if (!openFiles.includes(path)) {
        const res = await readFile(path)
        if (!res.ok) {
          addMessage({ role: 'system', content: `无法读取 ${path}: ${res.error}` })
          return
        }
        setContents((prev) => ({ ...prev, [path]: res.content ?? '' }))
        setOpenFiles((prev) => [...prev, path])
      }
      setActivePath(path)
    },
    [openFiles, readFile, addMessage]
  )

  const handleFileChange = useCallback((path: string, value: string) => {
    setContents((prev) => (prev[path] === value ? prev : { ...prev, [path]: value }))
    setModified((prev) => {
      if (prev.has(path)) return prev
      return new Set(prev).add(path)
    })
  }, [])

  const handleFileClose = useCallback((path: string) => {
    setOpenFiles((prev) => {
      const next = prev.filter((p) => p !== path)
      setActivePath((current) => (current === path ? next[next.length - 1] || '' : current))
      return next
    })
    setContents((prev) => {
      const next = { ...prev }
      delete next[path]
      return next
    })
    setModified((prev) => {
      const next = new Set(prev)
      next.delete(path)
      return next
    })
  }, [])

  const handleFileSave = useCallback(
    async (path: string) => {
      const content = contents[path] ?? ''
      const res = await writeFile(path, content)
      if (!res.ok) {
        addMessage({ role: 'system', content: `保存失败 ${path}: ${res.error}` })
        return
      }
      setModified((prev) => {
        const next = new Set(prev)
        next.delete(path)
        return next
      })
      setRefreshKey((v) => v + 1)
    },
    [contents, writeFile, addMessage]
  )

  const addFileToContext = useCallback((path: string, content: string) => {
    const normalized = path.replace(/\\/g, '/')
    setContextSnippets((prev) => {
      const next: ContextSnippet = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        path: normalized,
        content,
      }
      return [next, ...prev.filter((item) => item.path !== normalized)].slice(0, 8)
    })
    addMessage({
      role: 'system',
      content: `已加入下次提问上下文：${normalized}（约 ${content.length} 字符）`,
    })
  }, [addMessage])

  const removeContextSnippet = useCallback((id: string) => {
    setContextSnippets((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const triggerFileTreeRefresh = useCallback(() => setRefreshKey((v) => v + 1), [])

  const loadTools = useCallback(async () => {
    setToolsLoading(true)
    setToolsError('')
    try {
      const [toolsRes, auditRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/mcp/tools`),
        fetch(`${API_BASE}/maker/tool-audit`),
        fetch(`${API_BASE}/mcp/status?probe=true`),
      ])
      const data = await toolsRes.json()
      const audit = await auditRes.json().catch(() => ({}))
      const status = await statusRes.json().catch(() => null)
      setToolAudit(audit)
      if (status) setMcpStatus(status)
      const remoteTools = Array.isArray(audit.remote_tools) ? audit.remote_tools : []
      const requiredTools = Array.isArray(audit.required_proxy_tools) ? audit.required_proxy_tools : []
      const fallbackTools = Array.isArray(data.tools) ? data.tools : Array.isArray(data) ? data : []
      const byName = new Map<string, ToolItem>()
      const pushTool = (tool: any, inferred: Partial<ToolItem> = {}) => {
        const name = String(tool?.name || '').trim()
        if (!name) return
        byName.set(name, { ...byName.get(name), ...tool, ...inferred, name })
      }
      remoteTools.forEach((tool: any) => pushTool(tool, { remote_exposed: true, source: tool?.source || 'Maker MCP' }))
      requiredTools.forEach((tool: any) => pushTool(tool, { required_proxy: true }))
      fallbackTools.forEach((tool: any) => pushTool(tool, { remote_exposed: true, source: tool?.source || 'Maker MCP' }))
      const rawTools = Array.from(byName.values()).sort((a, b) =>
        Number(Boolean(b.required_proxy)) - Number(Boolean(a.required_proxy)) || String(a.name).localeCompare(String(b.name))
      )
      setTools(rawTools)
    } catch (err: any) {
      setToolsError(err?.message || '工具列表读取失败')
    } finally {
      setToolsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (makerIssueAutoOpened || configLoading || !makerSetup || !mcpStatus) return
    if (!makerNeedsAttention(makerSetup, mcpStatus, toolAudit)) return
    setMakerIssueAutoOpened(true)
    setWorkspaceDrawer(null)
    setWorkspacePage('maker')
    void loadTools()
    addMessage({
      role: 'system',
      content: '检测到 Maker MCP 或项目接入还没有完全就绪，已打开 Maker 接入页。请按页面提示完成修复后再开始真实 Maker 任务。',
    })
  }, [
    addMessage,
    configLoading,
    loadTools,
    makerIssueAutoOpened,
    makerSetup,
    mcpStatus,
    toolAudit,
  ])

  const reconnectMcp = useCallback(async () => {
    setToolsLoading(true)
    setToolsError('')
    try {
      const response = await fetch(`${API_BASE}/mcp/reconnect`, { method: 'POST' })
      const data = await response.json()
      if (data?.setup_status) setMakerSetup(data.setup_status)
      if (data?.status) setMcpStatus(data.status)
      if (data?.tool_audit) setToolAudit(data.tool_audit)
      if (!response.ok || data?.ok === false) {
        setToolsError(data?.error || data?.tool_audit?.mcp_error || 'Maker MCP 重连失败')
      }
      await loadTools()
    } catch (err: any) {
      setToolsError(err?.message || 'Maker MCP 重连失败')
    } finally {
      setToolsLoading(false)
    }
  }, [loadTools])

  const hotRepairMakerAccess = useCallback(async () => {
    setToolsLoading(true)
    setToolsError('')
    try {
      const response = await fetch(`${API_BASE}/maker/repair`, { method: 'POST' })
      const data = await response.json()
      if (data?.setup_status) setMakerSetup(data.setup_status)
      if (data?.status) setMcpStatus(data.status)
      if (data?.tool_audit) setToolAudit(data.tool_audit)
      if (!response.ok || data?.ok === false) {
        setToolsError(data?.error || data?.tool_audit?.diagnosis || 'Maker 热修复未完成')
      }
      await loadTools()
      await loadMakerSetup(false)
      return data
    } catch (err: any) {
      setToolsError(err?.message || 'Maker 热修复未完成')
      return { ok: false, error: err?.message || 'Maker 热修复未完成' }
    } finally {
      setToolsLoading(false)
    }
  }, [loadMakerSetup, loadTools])

  const repairMakerAccess = useCallback(async () => {
    if (makerPractice?.running) return
    setMakerRepairing(true)
    try {
      const setup = await loadMakerSetup(true) as MakerSetupStatus
      const blockers = Array.isArray(setup.blockers) ? setup.blockers : []
      const warnings = Array.isArray(setup.warnings) ? setup.warnings : []
      const project = setup.project || {}
      if (blockers.includes('maker_mcp_config_missing') || blockers.includes('npx_missing')) {
        setPendingMakerRepairAudit(true)
        await startMakerInstall()
        return
      }
      if (!project.root || project.is_app_root || warnings.includes('project_root_is_ttmevolve_app_root')) {
        await selectMakerProject()
        return
      }
      if (
        blockers.includes('maker_project_not_initialized')
        || blockers.includes('maker_project_not_bound')
        || !project.maker_initialized
        || project.project_bound === false
      ) {
        setPendingMakerRepairAudit(true)
        await startMakerInit()
        return
      }
      const practice = await loadMakerPractice() as MakerPracticeStatus
      const authUrl = practice?.auth_url || makerPractice?.auth_url || ''
      if (authUrl) {
        await openMakerAuth(authUrl)
        return
      }
      if (blockers.includes('tap_auth_missing')) {
        setPendingMakerRepairAudit(true)
        await startMakerInit()
        return
      }
      await hotRepairMakerAccess()
    } finally {
      setMakerRepairing(false)
    }
  }, [
    hotRepairMakerAccess,
    loadMakerPractice,
    loadMakerSetup,
    makerPractice?.auth_url,
    makerPractice?.running,
    openMakerAuth,
    selectMakerProject,
    startMakerInit,
    startMakerInstall,
  ])

  useEffect(() => {
    if (!pendingMakerRepairAudit || !makerPractice) return
    if (makerPractice.running) return
    const status = String(makerPractice.status || '').toLowerCase()
    if (status === 'ready') {
      setPendingMakerRepairAudit(false)
      void hotRepairMakerAccess()
    } else if (['error', 'canceled', 'offline'].includes(status)) {
      setPendingMakerRepairAudit(false)
      void loadMakerSetup(false)
    }
  }, [
    hotRepairMakerAccess,
    loadMakerSetup,
    makerPractice,
    pendingMakerRepairAudit,
  ])

  const openWorkspaceDrawer = useCallback((kind: WorkspaceDrawerKind) => {
    if (kind === 'tools' || kind === 'settings' || kind === 'maker') {
      if (kind === 'tools') void loadTools()
      setWorkspaceDrawer(null)
      setWorkspacePage((current) => (current === kind ? null : kind))
      return
    }
    setWorkspacePage(null)
    setWorkspaceDrawer((current) => (current === kind ? null : kind))
  }, [loadTools])

  useEffect(() => {
    const project = makerSetup?.project?.root || ''
    const initialized = Boolean(makerSetup?.project?.maker_initialized)
    const practiceReady = makerPractice?.status === 'ready' && !makerPractice?.running
    if (!project || !initialized || !practiceReady || lastAutoAuditProject === project) return
    setLastAutoAuditProject(project)
    void reconnectMcp()
  }, [
    lastAutoAuditProject,
    makerPractice?.running,
    makerPractice?.status,
    makerSetup?.project?.maker_initialized,
    makerSetup?.project?.root,
    reconnectMcp,
  ])

  const activeWorkspaceSurface = workspacePage || workspaceDrawer
  const drawerWidth = WORKSPACE_DRAWER_WIDTH

  const cockpitStyle = useMemo(
    () => ({
      gridTemplateColumns: chatCollapsed
        ? workspaceDrawer
          ? `42px ${drawerWidth}px minmax(0, 1fr)`
          : '42px minmax(0, 1fr)'
        : workspaceDrawer
          ? `${chatWidth}px ${drawerWidth}px minmax(0, 1fr)`
          : `${chatWidth}px minmax(0, 1fr)`,
    }),
    [chatCollapsed, chatWidth, workspaceDrawer]
  )

  const workspacePageStyle = useMemo(
    () => ({
      ['--workspace-page-width' as string]: `${workspacePageWidth}px`,
    }),
    [workspacePageWidth]
  )

  const startChatResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = chatWidth
    const onMove = (moveEvent: PointerEvent) => {
      const next = Math.min(
        MAX_CHAT_WIDTH,
        Math.max(MIN_CHAT_WIDTH, startWidth + moveEvent.clientX - startX)
      )
      setChatWidth(next)
      localStorage.setItem(CHAT_LAYOUT_KEY, String(Math.round(next)))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.classList.remove('is-resizing')
    }
    document.body.classList.add('is-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [chatWidth])

  const startWorkspacePageResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = workspacePageWidth
    const onMove = (moveEvent: PointerEvent) => {
      const next = Math.min(
        MAX_WORKSPACE_PAGE_WIDTH,
        Math.max(MIN_WORKSPACE_PAGE_WIDTH, startWidth + moveEvent.clientX - startX)
      )
      setWorkspacePageWidth(next)
      localStorage.setItem(WORKSPACE_PAGE_WIDTH_KEY, String(Math.round(next)))
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.classList.remove('is-resizing')
    }
    document.body.classList.add('is-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [workspacePageWidth])

  const toggleChatCollapsed = useCallback(() => {
    setChatCollapsed((current) => {
      const next = !current
      localStorage.setItem(CHAT_COLLAPSED_KEY, String(next))
      return next
    })
  }, [])

  return (
    <div className="app-container">
      <ElectronTitleBar />
      {appBootPending(configLoading, health, makerSetup, mcpStatus, bootStartedAt, bootNow) && (
        <div className="app-boot-gate" role="status" aria-live="polite">
          <div className="app-boot-card">
            <div className="app-boot-mark">TTM</div>
            <strong>正在检查桌面运行状态</strong>
            <span>{bootStatusText(configLoading, health, makerSetup, mcpStatus, bootStartedAt, bootNow)}</span>
            <div className="app-boot-progress"><i /></div>
          </div>
        </div>
      )}
      <div className="cockpit-shell maker-shell" style={cockpitStyle}>
        <aside className={`chat-sidebar ${chatCollapsed ? 'collapsed' : ''}`}>
          {chatCollapsed ? (
            <button className="side-rail-button" onClick={toggleChatCollapsed} title="展开 Agent 面板">
              AI
            </button>
          ) : (
            <>
              <ChatPanel
                messages={messages}
                addMessage={addMessage}
                provider={provider}
                onProviderChange={setProvider}
                providerPresets={providerPresets}
                model={model}
                baseUrl={baseUrl}
                apiKey={apiKey}
                apiKeySet={apiKeySet}
                onModelChange={setModel}
                onBaseUrlChange={setBaseUrl}
                onApiKeyChange={setApiKey}
                onApiKeySetChange={setApiKeySet}
                configLoading={configLoading}
                onFileTreeRefresh={triggerFileTreeRefresh}
                onCollapse={toggleChatCollapsed}
                onOpenWorkspaceDrawer={openWorkspaceDrawer}
                activeWorkspaceDrawer={activeWorkspaceSurface}
                onClearMessages={() => setMessages([])}
                contextSnippets={contextSnippets}
                onRemoveContextSnippet={removeContextSnippet}
                onClearContextSnippets={() => setContextSnippets([])}
                onUsage={handleAgentUsage}
                onRunningChange={handleAgentRunningChange}
                permissionProfile={profile}
                onPermissionProfileChange={setProfile}
                projectName={projectNameFromPath(makerSetup?.project?.root || projectRoot)}
                modelSummary={`${health?.provider || provider} · ${health?.model || model || '未选择'}`}
                configSummary={`${profile} · ${health?.runtime_kind || 'runtime'}`}
              />
              <div
                className="shell-resize-handle"
                onPointerDown={startChatResize}
                title="拖动调整 Agent 面板宽度"
              />
            </>
          )}
        </aside>
        {workspaceDrawer && (
          <aside className="workspace-side-drawer" aria-label={workspaceDrawerTitle(workspaceDrawer)}>
            <div className="workspace-side-drawer-body">
              {workspaceDrawer === 'files' ? (
                <FileTree
                  rootPath="."
                  refreshKey={refreshKey}
                  onSelect={(path) => void handleFileSelect(path)}
                  onAddToContext={addFileToContext}
                  onClose={() => setWorkspaceDrawer(null)}
                />
              ) : (
                <AssetLibrary
                  rootPath="."
                  refreshKey={refreshKey}
                  onSelect={(path) => void handleFileSelect(path)}
                  onAddToContext={addFileToContext}
                  onClose={() => setWorkspaceDrawer(null)}
                />
              )}
            </div>
          </aside>
        )}
        <main className="preview-stack">
          <CockpitHeader
            makerVersion={makerVersion}
            mcpStatus={mcpStatus}
            onOpenTools={() => openWorkspaceDrawer('tools')}
            onOpenMakerSetup={() => openWorkspaceDrawer('maker')}
            makerDestination={makerDestination}
            onToggleMakerDestination={toggleMakerDestination}
          />
          <div
            className={`preview-main ${workspacePage ? `with-workspace-page workspace-page-${workspacePage}` : ''}`}
            style={workspacePage ? workspacePageStyle : undefined}
          >
            {workspacePage && (
              <section className="workspace-page-panel" aria-label={workspaceDrawerTitle(workspacePage)}>
                <div className="workspace-page-head">
                  <div>
                    <strong>{workspaceDrawerTitle(workspacePage)}</strong>
                    <span>{workspacePageSubtitle(workspacePage, mcpStatus?.tool_count ?? tools.length)}</span>
                  </div>
                  <button type="button" onClick={() => setWorkspacePage(null)}>关闭</button>
                </div>
                <div className="workspace-page-body">{renderWorkspacePage(workspacePage)}</div>
              </section>
            )}
            {workspacePage && (
              <div
                className="workspace-page-resize-handle"
                onPointerDown={startWorkspacePageResize}
                title="拖动调整页面宽度"
              />
            )}
            <div className="preview-stage-slot">
              <IdeLayout
                rootPath="."
                activePath={activePath}
                openFiles={openFiles}
                contents={contents}
                modified={modified}
                onFileSelect={handleFileSelect}
                onFileChange={handleFileChange}
                onFileClose={handleFileClose}
                onFileSave={handleFileSave}
                refreshKey={refreshKey}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  )

  function renderWorkspacePage(kind: WorkspaceDrawerKind) {
    if (kind === 'tools') {
      const callableTools = tools.filter(toolIsCallable)
      const waitingTools = tools.filter((tool) => !toolIsCallable(tool))
      const missingCount = toolAudit?.missing_required_proxy_tools?.length ?? waitingTools.filter((tool) => tool.required_proxy).length
      return (
        <div className="workspace-tools-page">
          {toolAudit && (
            <div className="tool-audit-summary">
              <div className="tool-metric tool-metric-ready">
                <span>远程暴露</span>
                <strong>{toolAudit.remote_tool_count ?? 0}</strong>
              </div>
              <div className="tool-metric tool-metric-ready">
                <span>Agent 可调</span>
                <strong>{toolCallableCount(tools)}</strong>
              </div>
              <div className={`tool-metric ${missingCount > 0 ? 'tool-metric-warn' : 'tool-metric-ready'}`}>
                <span>待接入</span>
                <strong>{missingCount}</strong>
              </div>
              <button type="button" onClick={reconnectMcp} disabled={toolsLoading}>刷新</button>
            </div>
          )}
          {toolAudit && (
            <div className={`tool-audit-note tool-audit-note-${toolAuditTone(toolAudit)}`}>
              <span>{toolAuditReadinessLabel(toolAudit, makerSetup)}</span>
              <p>{toolAuditDiagnosisText(toolAudit, makerSetup)}</p>
            </div>
          )}
          {toolsLoading ? (
            <div className="tools-empty">正在读取工具列表...</div>
          ) : toolsError ? (
            <div className="tools-empty danger">{toolsError}</div>
          ) : tools.length ? (
            <div className="tool-list-page">
              {callableTools.length > 0 && (
                <ToolGroup title="可调用" tone="ready" tools={callableTools} />
              )}
              {waitingTools.length > 0 && (
                <ToolGroup title="待接入" tone="warn" tools={waitingTools} />
              )}
            </div>
          ) : (
            <div className="tools-empty">暂无工具，先完成 Maker 接入并刷新工具审计。</div>
          )}
        </div>
      )
    }

    if (kind === 'maker') {
      return (
        <div className="maker-onboarding-page">
          <div className="maker-onboarding-grid">
            <MakerStepCard
              step="1"
              title="安装或升级 Maker MCP"
              detail={makerVersionDetail(makerSetup)}
              action={makerPractice?.running ? '正在执行' : '安装 / 升级'}
              disabled={Boolean(makerPractice?.running)}
              onClick={startMakerInstall}
            />
            <MakerStepCard
              step="2"
              title="选择游戏项目目录"
              detail={makerSetup?.project?.root || projectRoot}
              action="选择或新建目录"
              onClick={selectMakerProject}
            />
            <MakerStepCard
              step="3"
              title="初始化 Maker 项目"
              detail={
                makerSetup?.project?.maker_initialized
                  ? makerSetup.project.project_bound
                    ? '当前目录已初始化并绑定项目'
                    : '当前目录配置残缺，尚未绑定真实项目'
                  : '当前目录需要执行 maker init'
              }
              action="初始化 / 继续"
              disabled={Boolean(makerPractice?.running)}
              onClick={startMakerInit}
            />
            <MakerStepCard
              step="4"
              title="授权与工具审计"
              detail={
                toolAudit
                  ? `远程 ${toolAudit.remote_tool_count ?? 0} 个 / 注册 ${toolAudit.registered_tool_count ?? 0} 个 / 缺失 ${toolAudit.missing_required_proxy_tools?.length ?? 0} 个必需代理工具`
                  : mcpStatus?.connected
                    ? `${mcpStatus.tool_count ?? 0} 个远程工具`
                    : 'Maker MCP 未连接或未暴露工具'
              }
              action="重连并审计"
              onClick={() => {
                void loadMakerSetup(true)
                void reconnectMcp()
              }}
            />
          </div>
          <div className="maker-onboarding-status">
            <strong>当前状态：{makerReadinessLabel(makerSetup?.readiness)}</strong>
            <span>{makerAssuranceText(makerSetup, toolAudit)}</span>
            <span>下一步：{makerNextActionLabel(makerSetup?.commands?.recommended_next)}</span>
            <span>{makerMcpProbeText(makerSetup?.mcp_probe || mcpStatus?.probe)}</span>
            <div>
              {makerPractice?.auth_url && (
                <button type="button" onClick={() => openMakerAuth(makerPractice.auth_url || '')}>打开授权页</button>
              )}
              <button
                type="button"
                onClick={repairMakerAccess}
                disabled={toolsLoading || makerRepairing || Boolean(makerPractice?.running)}
              >
                {makerRepairing || makerPractice?.running ? '正在修复' : makerRepairLabel(makerSetup, toolAudit, mcpStatus)}
              </button>
              {makerPractice?.running && <button type="button" onClick={cancelMakerPractice}>停止</button>}
            </div>
          </div>
          <div className="maker-safety-checks">
            {makerSafetyChecks(makerSetup, toolAudit, mcpStatus).map((item) => (
              <div className={`maker-safety-row ${item.ok ? 'ok' : item.warn ? 'warn' : 'fail'}`} key={item.label}>
                <span>{item.ok ? '通过' : item.warn ? '降级' : '待处理'}</span>
                <strong>{item.label}</strong>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
          <div className="maker-onboarding-log">
            {(makerPractice?.logs || []).slice(-80).map((row, index) => (
              <div key={`${row.time || index}-${index}`} title={row.text || ''}>
                <span>{makerLogKindLabel(row.kind)}</span>
                <p>{makerLogText(row.text || '')}</p>
              </div>
            ))}
          </div>
        </div>
      )
    }

    return (
      <div className="workspace-settings-page">
        <ProviderSelector
          provider={provider}
          onChange={setProvider}
          presets={providerPresets}
          model={model}
          baseUrl={baseUrl}
          apiKey={apiKey}
          apiKeySet={apiKeySet}
          onModelChange={setModel}
          onBaseUrlChange={setBaseUrl}
          onApiKeyChange={setApiKey}
          onApiKeySetChange={setApiKeySet}
          disabled={configLoading}
        />
        <div className="settings-secondary">
          <div>
            <strong>界面主题</strong>
            <span>主题切换收进设置页，不占用预览底栏。</span>
          </div>
          <div className="settings-action-grid">
            <button type="button" onClick={toggleTheme}>
              切换为{theme === 'dark' ? '浅色' : '深色'}
            </button>
          </div>
        </div>
      </div>
    )
  }
}

function workspaceDrawerTitle(kind: WorkspaceDrawerKind): string {
  switch (kind) {
    case 'files':
      return '项目文件'
    case 'assets':
      return '素材库'
    case 'tools':
      return '可用工具'
    case 'settings':
      return '设置'
    case 'maker':
      return 'Maker 接入'
    default:
      return '工作区'
  }
}

function workspacePageSubtitle(kind: WorkspaceDrawerKind, toolCount: number): string {
  if (kind === 'tools') return `${toolCount} 个 Maker / Agent 可用工具`
  if (kind === 'maker') return '安装、升级、初始化、授权和工具审计'
  return '模型与供应商设置'
}

function toolStatusText(tool: ToolItem): string {
  if (tool.required_proxy && !tool.remote_exposed && tool.registered && tool.executor_handler) return '本地代理已挂载，等待 Maker MCP 暴露远程能力'
  if (tool.required_proxy && !tool.remote_exposed) return '远程未暴露，相关生成能力暂不可用'
  if (tool.remote_exposed && tool.registered && tool.executor_handler) return '远程已暴露，Agent 可调用'
  if (tool.source && !toolSourceIsMaker(tool.source)) return '本地代理工具，可调用'
  if (tool.remote_exposed && !tool.registered) return '远程已暴露，但尚未注册到 Agent'
  if (tool.registered && !tool.executor_handler) return '已注册，但执行器未接入'
  return '状态待确认，请重连刷新'
}

function toolSourceLabel(tool: ToolItem): string {
  if (tool.required_proxy && !tool.remote_exposed && tool.registered && tool.executor_handler) return '创意代理（已挂载）'
  if (tool.required_proxy && !tool.remote_exposed) return '创意代理（等待 Maker MCP 暴露）'
  if (toolSourceIsMaker(tool.source) || tool.remote_exposed) return 'Maker MCP'
  return tool.source || 'Agent'
}

function toolCallableCount(tools: ToolItem[]): number {
  return tools.filter(toolIsCallable).length
}

function toolIsCallable(tool: ToolItem): boolean {
  if (tool.required_proxy && !tool.remote_exposed) return false
  return Boolean(
    (tool.remote_exposed && tool.registered && tool.executor_handler)
    || (tool.source && !toolSourceIsMaker(tool.source))
  )
}

function toolSourceIsMaker(source?: string): boolean {
  const value = String(source || '').toLowerCase()
  return value === 'maker mcp' || value.startsWith('maker_mcp')
}

function toolVisualTone(tool: ToolItem): 'ready' | 'warn' | 'neutral' {
  if (toolIsCallable(tool)) return 'ready'
  if (tool.required_proxy || tool.remote_exposed || tool.registered) return 'warn'
  return 'neutral'
}

function ToolGroup({
  title,
  tone,
  tools,
}: {
  title: string
  tone: 'ready' | 'warn'
  tools: ToolItem[]
}) {
  return (
    <section className={`tool-group tool-group-${tone}`}>
      <div className="tool-group-head">
        <span className={`tool-status-dot ${tone}`} />
        <strong>{title}</strong>
        <small>{tools.length}</small>
      </div>
      <div className="tool-card-grid">
        {tools.slice(0, 200).map((tool, index) => {
          const visualTone = toolVisualTone(tool)
          return (
            <div
              className={`tool-card tool-card-${visualTone}`}
              key={`${tool.name || 'tool'}-${index}`}
              title={toolStatusText(tool)}
            >
              <span className={`tool-status-dot ${visualTone}`} />
              <strong>{tool.name || '未命名工具'}</strong>
              <small>{toolSourceLabel(tool)} · {toolShortStatus(tool)}</small>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function toolAuditTone(audit: any): 'ready' | 'warn' | 'fail' {
  if (audit?.readiness === 'ready' || audit?.ok === true) return 'ready'
  if (audit?.repair_ok && audit?.readiness === 'degraded') return 'warn'
  if (audit?.readiness === 'blocked' || audit?.mcp_connected === false) return 'fail'
  return 'warn'
}

function toolAuditReadinessLabel(audit: any, setup?: MakerSetupStatus | null): string {
  if (setup?.blockers?.includes('maker_project_not_bound')) return '项目未绑定'
  if (setup?.blockers?.includes('maker_project_not_initialized')) return '需要初始化'
  if (audit?.repair_ok && audit?.readiness === 'degraded') return '基础修复完成'
  const tone = toolAuditTone(audit)
  if (tone === 'ready') return '工具已就绪'
  if (tone === 'fail') return '需要修复'
  return '远程能力未完整暴露'
}

function toolAuditDiagnosisText(audit: any, setup?: MakerSetupStatus | null): string {
  if (setup?.blockers?.includes('maker_project_not_bound')) {
    return '当前目录只有残缺 Maker 配置，尚未绑定真实 Maker 项目。请点击“一键修复”重新初始化并选择或创建项目。'
  }
  if (setup?.blockers?.includes('maker_project_not_initialized')) {
    return '当前目录还没有完成 Maker 初始化。请先初始化项目，再审计远程工具。'
  }
  return audit?.diagnosis || audit?.next_action || '正在等待工具审计结果。'
}

function toolShortStatus(tool: ToolItem): string {
  if (toolIsCallable(tool)) return '可调用'
  if (tool.required_proxy && !tool.remote_exposed && tool.registered && tool.executor_handler) return '已挂载'
  if (tool.required_proxy && !tool.remote_exposed) return '等待远程暴露'
  if (tool.remote_exposed && !tool.registered) return '待注册'
  if (tool.registered && !tool.executor_handler) return '待接执行器'
  return '待确认'
}

function makerReadinessLabel(value?: string): string {
  switch (value) {
    case 'ready':
      return '就绪'
    case 'degraded':
      return '部分可用'
    case 'blocked':
      return '需要处理'
    case 'offline':
      return '后端离线'
    case undefined:
    case '':
      return '正在检测'
    default:
      return value
  }
}

function makerNextActionLabel(value?: string): string {
  const text = String(value || '').trim()
  if (!text) return '正在读取 Maker 接入状态。'
  if (text.includes('安装或升级 Maker MCP')) return '点击“一键修复”安装或升级 Maker MCP，然后自动重新检测。'
  if (text.includes('单独的空白 Maker 游戏项目目录')) return '点击“一键修复”选择或新建一个独立游戏项目目录。'
  if (text.includes('Maker 初始化')) return '点击“一键修复”在当前游戏目录里执行 Maker 初始化。'
  if (text.includes('残缺 Maker 配置') || text.includes('尚未绑定真实 Maker 项目')) return '点击“一键修复”重新初始化，并在内置流程里选择或创建真实 Maker 项目。'
  if (text.includes('TapTap 授权')) return '点击“一键修复”打开内置 Maker 浏览器完成 TapTap 授权。'
  if (text.includes('重连 Maker MCP')) return '点击“一键修复”重连 Maker MCP，并重新检查可用工具。'
  if (text.includes('已可开始')) return '已可开始一个小型 Maker 实战任务。'
  if (text.includes('install --ide')) return '安装或升级 Maker MCP，然后重新检测。'
  if (text.includes('separate empty Maker game directory')) return '请选择或新建一个单独的空白游戏项目目录。'
  if (text.includes('maker init')) return '在当前选择的游戏目录里执行 Maker 初始化。'
  if (text.includes('authorization URL')) return '打开内置 Maker 浏览器完成 TapTap 授权。'
  if (text.includes('Refresh Maker MCP') || text.includes('/maker/tool-audit')) {
    return '重连 Maker MCP，并重新检查可用工具。'
  }
  if (text.includes('Ready for a small real Maker coding task')) return '已可开始一个小型 Maker 实战任务。'
  return text
}

function makerRepairLabel(setup: MakerSetupStatus | null, audit: any, mcp: McpStatus | null): string {
  const blockers = setup?.blockers || []
  const warnings = setup?.warnings || []
  const missingRequired = Array.isArray(audit?.missing_required_proxy_tools)
    ? audit.missing_required_proxy_tools.length
    : setup?.tool_audit?.missing_required_proxy_tools?.length || 0
  if (blockers.includes('maker_mcp_config_missing') || blockers.includes('npx_missing')) return '一键修复'
  if (!setup?.project?.root || setup?.project?.is_app_root || warnings.includes('project_root_is_ttmevolve_app_root')) {
    return '一键修复'
  }
  if (
    blockers.includes('maker_project_not_initialized')
    || blockers.includes('maker_project_not_bound')
    || !setup?.project?.maker_initialized
    || setup?.project?.project_bound === false
  ) return '一键修复'
  if (blockers.includes('tap_auth_missing')) return '一键修复'
  if (!mcp?.connected) return '一键修复'
  if (missingRequired > 0 && audit?.repair_ok) return '重新审计'
  if (warnings.includes('maker_proxy_tools_missing') || missingRequired > 0) return '一键修复'
  return '重新修复'
}

function makerAssuranceText(setup: MakerSetupStatus | null, audit: any): string {
  if (!setup) return '正在检查安装、目录、初始化、授权和工具注册状态。'
  const blockers = setup.blockers || []
  const warnings = setup.warnings || []
  if (blockers.includes('maker_project_not_initialized')) return '还不能开始实战：当前目录尚未初始化，已阻止后续失败。'
  if (blockers.includes('maker_project_not_bound')) return '还不能开始实战：当前目录只有残缺 Maker 配置，尚未绑定真实项目。'
  if (blockers.includes('tap_auth_missing')) return '还不能调用远程 Maker 能力：需要先完成 TapTap 授权。'
  if (blockers.length) return '存在硬性前置条件未完成，TTMEvolve 会先拦截任务，避免进入必失败流程。'
  const missing = Array.isArray(audit?.missing_required_proxy_tools)
    ? audit.missing_required_proxy_tools.length
    : setup.tool_audit?.missing_required_proxy_tools?.length || 0
  if (warnings.includes('maker_proxy_tools_missing') || missing > 0) {
    if (audit?.repair_ok) {
      return `一键修复已完成本地挂载；${missing || '部分'} 个创意工具等待 Maker MCP 远程开放，调用时会给出可诊断提示。`
    }
    return `普通编码和预览可继续；${missing || '部分'} 个创意代理工具缺失，素材/图片/视频/3D 生成会先降级或要求重连。`
  }
  return '硬性前置已通过，可以开始小型 Maker 实战任务。'
}

function makerVersionDetail(setup: MakerSetupStatus | null): string {
  const pkg = setup?.maker_package
  if (!pkg) return 'Checking Maker MCP package version...'
  const current = pkg.configured || 'unknown'
  const latest = pkg.latest || ''
  const check = pkg.latest_check || 'pending'
  if (pkg.update_available === true && latest) return `Current ${current}, latest ${latest} available`
  if (pkg.update_available === false && latest) return `Current ${current}, latest ${latest}, up to date`
  if (check === 'unavailable') return `Current ${current}, latest check unavailable`
  if (check === 'cached' && latest) return `Current ${current}, latest ${latest} checked automatically`
  if (latest) return `Current ${current}, latest ${latest}`
  return `Current ${current}, checking latest automatically`
}

function makerMcpProbeText(probe?: MakerMcpProbe | null): string {
  if (!probe) return 'Maker MCP real probe: waiting for initialize/tools-list.'
  const elapsed = probe.elapsed_ms !== undefined ? ` in ${probe.elapsed_ms}ms` : ''
  if (probe.ok || probe.connected) {
    return `Maker MCP real probe passed${elapsed}: ${probe.tool_count ?? 0} tools from fresh tools/list.`
  }
  const error = probe.error ? ` ${probe.error}` : ''
  return `Maker MCP real probe failed${elapsed}.${error}`
}

function makerSafetyChecks(setup: MakerSetupStatus | null, audit: any, mcp: McpStatus | null) {
  const initialized = Boolean(setup?.project?.maker_initialized)
  const projectBound = Boolean(setup?.project?.project_bound)
  const separateProject = Boolean(setup?.project?.root && !setup?.project?.is_app_root)
  const authReady = Boolean(setup?.auth?.tap_auth_present || setup?.auth?.pat_present)
  const agentRootMcpReady = Boolean(setup?.agent_root_mcp?.registered)
  const mcpConnected = Boolean(mcp?.connected || audit?.mcp_connected)
  const missingRequired = Array.isArray(audit?.missing_required_proxy_tools)
    ? audit.missing_required_proxy_tools.length
        : setup?.tool_audit?.missing_required_proxy_tools?.length || 0
  return [
    {
      label: '项目目录',
      ok: separateProject,
      detail: separateProject ? '已使用独立游戏目录，不会污染 TTMEvolve 本体目录。' : '请先选择或新建独立游戏目录。',
    },
    {
      label: 'Maker 初始化',
      ok: initialized,
      detail: initialized ? '当前目录已完成 Maker 初始化。' : '未初始化前不会继续执行实战任务。',
    },
    {
      label: '项目绑定',
      ok: projectBound,
      detail: projectBound
        ? `已绑定 Maker 项目 ${setup?.project?.project_id || ''}。`
        : '当前目录未绑定真实 Maker 项目；project_id=0 或缺失时不能调用完整远程工具。',
    },
    {
      label: 'Agent 根目录 MCP',
      ok: agentRootMcpReady,
      detail: agentRootMcpReady
        ? `已在 TTMEvolve 根目录注册 Maker MCP（${setup?.agent_root_mcp?.registered_count ?? 0}/${setup?.agent_root_mcp?.target_count ?? 0}）。`
        : 'TTMEvolve 根目录还没有完整 MCP 注册；点击一键修复会在 GUI 内写入。'
    },
    {
      label: '授权状态',
      ok: authReady,
      warn: !authReady,
      detail: authReady ? '已检测到授权信息。' : '未授权时只允许本地编码准备，远程 Maker 调用会被拦截。',
    },
    {
      label: '工具注册',
      ok: mcpConnected && missingRequired === 0,
      warn: mcpConnected && missingRequired > 0 && Boolean(audit?.repair_ok),
      detail: mcpConnected
        ? missingRequired > 0
          ? audit?.repair_ok
            ? `本地代理入口已挂载，${missingRequired} 个创意远程能力等待 Maker MCP 暴露。`
            : `远程已连接，但缺少 ${missingRequired} 个创意代理工具；请点击一键修复挂载代理入口。`
          : '远程工具已连接并通过审计。'
        : 'Maker MCP 尚未连接，请点击“一键修复”重连。',
    },
  ]
}

function makerLogKindLabel(kind?: string): string {
  switch (String(kind || '').toLowerCase()) {
    case 'system':
      return '系统'
    case 'stdout':
      return '输出'
    case 'stderr':
      return '错误'
    case 'error':
      return '失败'
    case 'input':
      return '输入'
    default:
      return '日志'
  }
}

function makerLogText(value: string): string {
  const text = String(value || '').trim()
  if (!text) return ''
  if (text === 'Skipped Maker MCP install.') return '已跳过 Maker MCP 安装。'
  if (text === 'Skipped Maker project init.') return '已跳过 Maker 项目初始化。'
  if (text === 'Maker project already initialized.') return 'Maker 项目已初始化。'
  if (text === 'Maker practice setup canceled.') return '已停止 Maker 接入流程。'
  if (text.startsWith('cwd:')) return `运行目录：${text.slice(4).trim()}`
  if (text.startsWith('exit code:')) return `退出码：${text.slice('exit code:'.length).trim()}`
  if (text.includes('@taptap/maker install')) return '正在安装或升级 Maker MCP。'
  if (text.includes('@taptap/maker init')) {
    return text.endsWith(' init 0') ? '正在初始化 Maker 项目，并创建新的 Maker 项目绑定。' : '正在初始化 Maker 项目。'
  }
  if (text.includes('Codex MCP config unchanged')) return 'Codex 的 Maker MCP 配置无需变更。'
  if (text.includes('Cursor MCP config unchanged')) return 'Cursor 的 Maker MCP 配置无需变更。'
  if (text.includes('Claude fallback MCP config unchanged')) return 'Claude 的 Maker MCP 备用配置无需变更。'
  if (text.includes('Choose app by index')) return 'Maker 需要选择项目；TTMEvolve 会默认选择“创建新项目”。'
  if (text.includes('required in non-interactive mode')) return 'Maker 初始化需要项目选择参数，正在改用自动选择方式。'
  if (text.includes('Assertion failed') && text.includes('UV_HANDLE_CLOSING')) return 'Maker CLI 在项目选择阶段异常退出，请重新点击初始化。'
  if (text.includes('Maker command failed with exit code')) return text.replace('Maker command failed with exit code', 'Maker 命令执行失败，退出码')
  return text
}

function MakerStepCard({
  step,
  title,
  detail,
  action,
  disabled,
  onClick,
}: {
  step: string
  title: string
  detail: string
  action: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <div className="maker-onboarding-card">
      <span>{step}</span>
      <strong>{title}</strong>
      <p title={detail}>{detail}</p>
      <button type="button" onClick={onClick} disabled={disabled}>{action}</button>
    </div>
  )
}
