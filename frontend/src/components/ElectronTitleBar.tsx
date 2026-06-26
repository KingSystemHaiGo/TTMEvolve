import { closeWindow, isTauri, minimizeWindow, toggleMaximizeWindow } from '../lib/tauri'

type ElectronApi = {
  windowControls?: {
    minimize: () => void
    toggleMaximize: () => void
    close: () => void
  }
}

declare global {
  interface Window {
    electronAPI?: ElectronApi
  }
}

export default function ElectronTitleBar() {
  const electronControls = window.electronAPI?.windowControls
  const tauriRuntime = isTauri()

  if (!electronControls && !tauriRuntime) {
    return <div className="electron-titlebar electron-titlebar-web" />
  }

  const minimize = () => {
    if (electronControls) {
      electronControls.minimize()
      return
    }
    void minimizeWindow()
  }

  const toggleMaximize = () => {
    if (electronControls) {
      electronControls.toggleMaximize()
      return
    }
    void toggleMaximizeWindow()
  }

  const close = () => {
    if (electronControls) {
      electronControls.close()
      return
    }
    void closeWindow()
  }

  return (
    <div className="electron-titlebar">
      <div className="electron-titlebar-drag" data-tauri-drag-region>
        <span className="electron-titlebar-accent" aria-hidden="true" />
      </div>
      <div className="electron-window-controls">
        <button type="button" aria-label="最小化" onClick={minimize}>
          -
        </button>
        <button type="button" aria-label="最大化" onClick={toggleMaximize}>
          □
        </button>
        <button type="button" aria-label="关闭" onClick={close}>
          ×
        </button>
      </div>
    </div>
  )
}
