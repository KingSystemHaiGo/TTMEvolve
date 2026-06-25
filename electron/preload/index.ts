import { contextBridge, ipcRenderer } from 'electron'

/**
 * Minimal preload for Phase 1.
 * Future phases can expose ipcRenderer methods here for Electron-native features.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  windowControls: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    toggleMaximize: () => ipcRenderer.invoke('window:toggleMaximize'),
    close: () => ipcRenderer.invoke('window:close'),
  },
  files: {
    openDialog: () => ipcRenderer.invoke('files:openDialog'),
    openDirectory: () => ipcRenderer.invoke('files:openDirectory'),
  },
  makerBrowser: {
    show: () => ipcRenderer.invoke('makerBrowser:show'),
    hide: () => ipcRenderer.invoke('makerBrowser:hide'),
    setBounds: (rect: { x: number; y: number; width: number; height: number }) =>
      ipcRenderer.invoke('makerBrowser:setBounds', rect),
    navigate: (url: string) => ipcRenderer.invoke('makerBrowser:navigate', url),
    reload: () => ipcRenderer.invoke('makerBrowser:reload'),
    setDarkMode: (enabled: boolean, options?: { reload?: boolean }) =>
      ipcRenderer.invoke('makerBrowser:setDarkMode', enabled, options),
  },
})
