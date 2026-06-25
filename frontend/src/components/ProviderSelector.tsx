import { useEffect, useMemo, useRef, useState } from 'react'
import type { Provider, ProviderPreset } from '../App'

interface Props {
  provider: Provider
  onChange: (provider: Provider) => void
  presets?: ProviderPreset[]
  model?: string
  baseUrl?: string
  apiKey?: string
  apiKeySet?: boolean
  onModelChange?: (value: string) => void
  onBaseUrlChange?: (value: string) => void
  onApiKeyChange?: (value: string) => void
  onApiKeySetChange?: (value: boolean) => void
  sessionId?: string | null
  disabled?: boolean
  configLocked?: boolean
}

interface ModelsResponse {
  source?: string
  models?: string[]
  message?: string
}

interface ProbeResponse {
  ok?: boolean
  provider?: string
  runtime_kind?: string
  llm_class?: string
  model?: string
  base_url?: string
  elapsed_ms?: number
  output_preview?: string
  error?: string
  last_call_stats?: {
    endpoint?: string
    total_tokens?: number
    generate_ms?: number
    error_type?: string
  }
}

const API_BASE = 'http://127.0.0.1:7345'

export default function ProviderSelector({
  provider,
  onChange,
  presets = [],
  model = '',
  baseUrl = '',
  apiKey = '',
  apiKeySet = false,
  onModelChange,
  onBaseUrlChange,
  onApiKeyChange,
  onApiKeySetChange,
  sessionId,
  disabled = false,
  configLocked = false,
}: Props) {
  const [saving, setSaving] = useState(false)
  const [loadingModels, setLoadingModels] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [modelSource, setModelSource] = useState('')
  const [message, setMessage] = useState('')
  const [probing, setProbing] = useState(false)
  const [probe, setProbe] = useState<ProbeResponse | null>(null)
  const [providerOpen, setProviderOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const providerPickerRef = useRef<HTMLDivElement | null>(null)
  const modelPickerRef = useRef<HTMLDivElement | null>(null)

  const activePreset = useMemo(
    () => presets.find((item) => item.id === provider),
    [presets, provider]
  )
  const isLocal = activePreset?.kind === 'local' || provider === 'local'
  const isClaude = activePreset?.kind === 'anthropic' || provider === 'claude'
  const activeProviderLabel = activePreset?.label || provider || '选择供应商'
  const selectedModel = models.includes(model) ? model : ''

  useEffect(() => {
    const closePickers = (event: MouseEvent) => {
      const target = event.target as Node
      if (providerPickerRef.current && !providerPickerRef.current.contains(target)) {
        setProviderOpen(false)
      }
      if (modelPickerRef.current && !modelPickerRef.current.contains(target)) {
        setModelOpen(false)
      }
    }
    document.addEventListener('mousedown', closePickers)
    return () => document.removeEventListener('mousedown', closePickers)
  }, [])

  const loadModels = async (silent = false) => {
    if (!provider) return
    setLoadingModels(true)
    if (!silent) setMessage('')
    try {
      const res = await fetch(`${API_BASE}/llm/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, base_url: baseUrl, api_key: apiKey }),
      })
      const data: ModelsResponse = await res.json()
      const nextModels = data.models || []
      setModels(nextModels)
      setModelSource(data.source || '')
      if (!model && nextModels.length > 0) onModelChange?.(nextModels[0])
      if (data.message && !silent) setMessage(data.message)
    } catch (err: any) {
      if (!silent) setMessage(err.message || '模型列表获取失败')
    } finally {
      setLoadingModels(false)
    }
  }

  useEffect(() => {
    loadModels(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, baseUrl, apiKeySet])

  const applyPreset = (nextProvider: string) => {
    onChange(nextProvider)
    setProviderOpen(false)
    const preset = presets.find((item) => item.id === nextProvider)
    if (preset) {
      onModelChange?.(preset.model)
      onBaseUrlChange?.(preset.base_url)
      setModels([])
      setModelSource('')
      setMessage('')
      setProbe(null)
    }
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const res = await fetch(`${API_BASE}/config/llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, base_url: baseUrl, api_key: apiKey }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) throw new Error(data.error || '保存失败')
      onApiKeyChange?.('')
      onApiKeySetChange?.(Boolean(data.api_key_set))
      setMessage(data.api_key_set || isLocal ? '已保存' : '已保存，请补充 API Key')
      await loadModels(true)
    } catch (err: any) {
      setMessage(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const probeRuntime = async () => {
    setProbing(true)
    setMessage('')
    setProbe(null)
    try {
      const res = await fetch(`${API_BASE}/llm/probe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model,
          base_url: baseUrl,
          api_key: apiKey,
          timeout: 20,
          ...(sessionId ? { session_id: sessionId } : {}),
        }),
      })
      const data: ProbeResponse = await res.json()
      setProbe(data)
      if (!res.ok || !data.ok) {
        setMessage(data.error || '模型探测失败')
      } else {
        setMessage('模型探测通过')
      }
    } catch (err: any) {
      setMessage(err.message || '模型探测失败')
    } finally {
      setProbing(false)
    }
  }

  return (
    <div className="provider-settings">
      <div className="provider-settings-top">
        <label>
          <span>供应商</span>
          <div className="provider-picker" ref={providerPickerRef}>
            <button
              type="button"
              className="provider-picker-trigger"
              onClick={() => setProviderOpen((open) => !open)}
              disabled={disabled || configLocked || saving}
              aria-expanded={providerOpen}
            >
              <strong>{activeProviderLabel}</strong>
              <span>⌄</span>
            </button>
            {providerOpen && (
              <div className="provider-picker-menu" role="listbox">
                {presets.map((preset) => (
                  <button
                    type="button"
                    key={preset.id}
                    className={preset.id === provider ? 'active' : ''}
                    onClick={() => applyPreset(preset.id)}
                    role="option"
                    aria-selected={preset.id === provider}
                  >
                    <strong>{preset.label}</strong>
                    <small>{preset.kind || 'OpenAI 兼容'}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
        </label>
        <button onClick={save} disabled={disabled || configLocked || saving || probing}>
          {saving ? '保存中' : '保存'}
        </button>
      </div>

      <label>
        <span>模型</span>
        <div className="provider-model-row">
          <div className="provider-picker provider-model-picker" ref={modelPickerRef}>
            <button
              type="button"
              className="provider-picker-trigger"
              onClick={() => setModelOpen((open) => !open)}
              disabled={disabled || configLocked || saving || loadingModels || isLocal || models.length === 0}
              aria-expanded={modelOpen}
            >
              <strong>{loadingModels ? '获取中...' : selectedModel || '选择模型'}</strong>
              <span>⌄</span>
            </button>
            {modelOpen && (
              <div className="provider-picker-menu provider-model-menu" role="listbox">
                {models.map((item) => (
                  <button
                    type="button"
                    key={item}
                    className={item === selectedModel ? 'active' : ''}
                    onClick={() => {
                      onModelChange?.(item)
                      setModelOpen(false)
                    }}
                    role="option"
                    aria-selected={item === selectedModel}
                  >
                    <strong>{item}</strong>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            className="provider-refresh-button"
            onClick={() => loadModels(false)}
            disabled={disabled || configLocked || saving || loadingModels}
            title="刷新模型列表"
          >
            刷新
          </button>
        </div>
      </label>

      <label>
        <span>自定义模型</span>
        <input value={model} onChange={(e) => onModelChange?.(e.target.value)} disabled={disabled || configLocked || saving || isLocal} placeholder="模型 ID" />
      </label>

      <label>
        <span>接口地址</span>
        <input value={baseUrl} onChange={(e) => onBaseUrlChange?.(e.target.value)} disabled={disabled || configLocked || saving || isLocal || isClaude} placeholder="https://.../v1" />
      </label>

      <label>
        <span>API Key</span>
        <input
          value={apiKey}
          onChange={(e) => onApiKeyChange?.(e.target.value)}
          disabled={disabled || configLocked || saving || isLocal}
          placeholder={apiKeySet ? '已保存，留空沿用现有 Key' : 'sk-...'}
          type="password"
          autoComplete="off"
        />
      </label>

      <div className="provider-settings-foot">
        <button
          type="button"
          className="provider-probe-button"
          onClick={probeRuntime}
          disabled={disabled || saving || probing || isLocal}
          title="用当前配置发起一次极小模型调用"
        >
          {probing ? '探测中' : '探测模型'}
        </button>
        <span>{activePreset?.kind || 'OpenAI 兼容'}</span>
        {modelSource && <span>模型来源：{modelSource}</span>}
        {apiKeySet && !apiKey && <span>API Key 已保存</span>}
        {message && <strong>{message}</strong>}
      </div>
      {probe && (
        <div className={`provider-probe-result ${probe.ok ? 'probe-ok' : 'probe-error'}`}>
          <span>{probe.ok ? '接口已验证' : '接口失败'}</span>
          <strong>
            {[probe.provider, probe.llm_class, probe.model, `${probe.elapsed_ms ?? 0}ms`]
              .filter(Boolean)
              .join(' / ')}
          </strong>
          <small>
            {probe.last_call_stats?.endpoint || probe.base_url || '-'}
            {sessionId ? ` | 会话=${sessionId.slice(0, 8)}` : ' | 全局探测'}
            {probe.last_call_stats?.total_tokens !== undefined
              ? ` | token=${probe.last_call_stats.total_tokens}`
              : ''}
            {probe.last_call_stats?.error_type ? ` | 错误=${probe.last_call_stats.error_type}` : ''}
            {probe.error ? ` | ${probe.error}` : ''}
          </small>
        </div>
      )}
    </div>
  )
}
