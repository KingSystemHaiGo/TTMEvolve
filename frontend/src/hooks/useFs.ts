import { useCallback } from 'react'

const API_BASE = 'http://127.0.0.1:7345'

export interface FsItem {
  name: string
  is_dir: boolean
}

export interface UseFsReturn {
  listFiles: (path: string) => Promise<{ ok: boolean; items?: FsItem[]; error?: string }>
  readFile: (path: string) => Promise<{ ok: boolean; content?: string; error?: string }>
  writeFile: (path: string, content: string) => Promise<{ ok: boolean; error?: string }>
  deleteFile: (path: string) => Promise<{ ok: boolean; error?: string }>
}

export function useFs(): UseFsReturn {
  const listFiles = useCallback(async (path: string) => {
    const resp = await fetch(`${API_BASE}/fs/list?path=${encodeURIComponent(path)}`)
    return resp.json()
  }, [])

  const readFile = useCallback(async (path: string) => {
    const resp = await fetch(`${API_BASE}/fs/read?path=${encodeURIComponent(path)}`)
    return resp.json()
  }, [])

  const writeFile = useCallback(async (path: string, content: string) => {
    const resp = await fetch(`${API_BASE}/fs/write`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content }),
    })
    return resp.json()
  }, [])

  const deleteFile = useCallback(async (path: string) => {
    const resp = await fetch(`${API_BASE}/fs/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    return resp.json()
  }, [])

  return { listFiles, readFile, writeFile, deleteFile }
}
