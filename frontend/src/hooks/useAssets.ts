import { useCallback } from 'react'

const API_BASE = 'http://127.0.0.1:7345'

export type AssetType = 'image' | 'audio' | 'video' | 'unknown'

export interface AssetItem {
  name: string
  path: string
  type: AssetType
  size: number
}

export interface StatResult {
  ok: boolean
  name?: string
  path?: string
  size?: number
  mime?: string
  is_dir?: boolean
  modified?: number
  error?: string
}

export interface UseAssetsReturn {
  listAssets: (
    path: string,
    extensions?: string
  ) => Promise<{ ok: boolean; assets?: AssetItem[]; error?: string }>
  statFile: (path: string) => Promise<StatResult>
}

export function useAssets(): UseAssetsReturn {
  const listAssets = useCallback(
    async (path: string, extensions?: string) => {
      const url = new URL(`${API_BASE}/fs/assets`)
      url.searchParams.set('path', path)
      if (extensions) {
        url.searchParams.set('extensions', extensions)
      }
      const resp = await fetch(url.toString())
      return resp.json()
    },
    []
  )

  const statFile = useCallback(async (path: string) => {
    const resp = await fetch(
      `${API_BASE}/fs/stat?path=${encodeURIComponent(path)}`
    )
    return resp.json()
  }, [])

  return { listAssets, statFile }
}
