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
  const controls = window.electronAPI?.windowControls

  if (!controls) {
    return <div className="electron-titlebar electron-titlebar-web" />
  }

  return (
    <div className="electron-titlebar">
      <div className="electron-titlebar-drag">
        <span className="electron-titlebar-mark">TTMEvolve</span>
      </div>
      <div className="electron-window-controls">
        <button type="button" aria-label="最小化" onClick={() => controls.minimize()}>
          -
        </button>
        <button type="button" aria-label="最大化" onClick={() => controls.toggleMaximize()}>
          □
        </button>
        <button type="button" aria-label="关闭" onClick={() => controls.close()}>
          ×
        </button>
      </div>
    </div>
  )
}
