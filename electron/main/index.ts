import { app, BrowserView, BrowserWindow, dialog, ipcMain, nativeTheme, OpenDialogOptions } from 'electron'
import { spawn, spawnSync, ChildProcess } from 'child_process'
import * as path from 'path'
import * as fs from 'fs'
import * as http from 'http'

const PYTHON_HOST = '127.0.0.1'
const PYTHON_PORT = 7345
const HEALTH_URL = `http://${PYTHON_HOST}:${PYTHON_PORT}/health`
const VITE_DEV_URL = 'http://127.0.0.1:5173'
const BACKEND_HEALTH_TIMEOUT_MS = 120000

let pythonProcess: ChildProcess | null = null
let logFile = ''
let mainWindow: BrowserWindow | null = null
let startupWindow: BrowserWindow | null = null
let makerBrowserView: BrowserView | null = null
let makerBrowserVisible = false
let makerBrowserDarkMode = false
let makerBrowserThemeCssKey: string | null = null

const MAKER_LIGHT_CSS = `
  :root {
    color-scheme: light !important;
  }
  input,
  textarea,
  select,
  button {
    color-scheme: light !important;
  }
  iframe {
    filter: none !important;
    background-color: transparent !important;
  }
  img,
  picture,
  svg {
    filter: none !important;
  }
`

const MAKER_DARK_CSS = `
  :root {
    color-scheme: dark !important;
  }
  html,
  body,
  #root,
  #app,
  [class*="bg-white"],
  [class~="bg-white"],
  [style*="background: white"],
  [style*="background-color: white"],
  [style*="background: #fff"],
  [style*="background-color: #fff"],
  [style*="background: #ffffff"],
  [style*="background-color: #ffffff"],
  [style*="background: rgb(255, 255, 255)"],
  [style*="background-color: rgb(255, 255, 255)"] {
    background-color: #181818 !important;
    color: #e5e5e5 !important;
  }
  [class*="bg-gray"],
  [class*="bg-slate"],
  [class*="bg-zinc"],
  [style*="background: rgb(247, 249, 250)"],
  [style*="background-color: rgb(247, 249, 250)"],
  [style*="background: #f7f9fa"],
  [style*="background-color: #f7f9fa"],
  [style*="background: rgb(248, 250, 252)"],
  [style*="background-color: rgb(248, 250, 252)"] {
    background-color: #202020 !important;
    color: #e5e5e5 !important;
  }
  input,
  textarea,
  select {
    background-color: #242424 !important;
    border-color: rgba(255, 255, 255, 0.14) !important;
    color: #e5e5e5 !important;
    color-scheme: dark !important;
  }
  button {
    border-color: rgba(255, 255, 255, 0.16) !important;
    color-scheme: dark !important;
  }
  iframe {
    filter: brightness(0.85) saturate(0.95) !important;
    background-color: #181818 !important;
  }
  [style*="bg-pattern"],
  [style*="/bg-pattern"] {
    background-image: none !important;
    background-color: #1a1a1a !important;
  }
  img[src*="bg-pattern"],
  img[src$="pattern.jpg"],
  img[src$="pattern.png"],
  img[src$="pattern.svg"] {
    display: none !important;
  }
  img,
  picture,
  svg:not([role="img"]):not([data-emoji]) {
    filter: brightness(0.88) !important;
  }
`

function ensureDir(target: string): string {
  fs.mkdirSync(target, { recursive: true })
  return target
}

function portablePaths(root = getProjectRoot()) {
  const portable = path.join(root, 'portable')
  const home = path.join(portable, 'home')
  const cache = path.join(portable, 'cache')
  const temp = path.join(portable, 'tmp')
  return {
    portable,
    home,
    cache,
    temp,
    desktop: path.join(home, 'Desktop'),
    documents: path.join(home, 'Documents'),
    downloads: path.join(home, 'Downloads'),
    music: path.join(home, 'Music'),
    pictures: path.join(home, 'Pictures'),
    videos: path.join(home, 'Videos'),
    appData: path.join(home, 'AppData', 'Roaming'),
    localAppData: path.join(home, 'AppData', 'Local'),
    electronUserData: path.join(portable, 'electron', 'userData'),
    electronSession: path.join(portable, 'electron', 'sessionData'),
    electronCrash: path.join(portable, 'electron', 'crashDumps'),
    makerHome: path.join(home, '.taptap-maker'),
    npmCache: path.join(cache, 'npm'),
    nodePrefix: path.join(portable, 'node-global'),
    pipCache: path.join(cache, 'pip'),
    hfHome: path.join(cache, 'huggingface'),
    playwright: fs.existsSync(path.join(root, 'vendor', 'playwright'))
      ? path.join(root, 'vendor', 'playwright')
      : path.join(cache, 'playwright'),
    embeddings: fs.existsSync(path.join(root, 'vendor', 'embeddings'))
      ? path.join(root, 'vendor', 'embeddings')
      : path.join(cache, 'sentence-transformers'),
  }
}

function configureElectronPortablePaths() {
  const root = getProjectRoot()
  const p = portablePaths(root)
  for (const dir of Object.values(p)) {
    ensureDir(dir)
  }
  try {
    app.setPath('home', p.home)
    app.setPath('appData', p.appData)
    app.setPath('userData', p.electronUserData)
    app.setPath('sessionData', p.electronSession)
    app.setPath('cache', path.join(p.cache, 'electron'))
    app.setPath('logs', path.join(root, 'logs', 'electron'))
    app.setPath('crashDumps', p.electronCrash)
    app.setPath('temp', p.temp)
    app.setPath('desktop', p.desktop)
    app.setPath('documents', p.documents)
    app.setPath('downloads', p.downloads)
    app.setPath('music', p.music)
    app.setPath('pictures', p.pictures)
    app.setPath('videos', p.videos)
  } catch (err: any) {
    writeLog(`[Electron] Portable app path setup failed: ${err?.message || err}`)
  }
}

function portableChildEnv(root = getProjectRoot()) {
  const p = portablePaths(root)
  for (const dir of Object.values(p)) {
    ensureDir(dir)
  }
  return {
    TTMEVOLVE_ROOT: root,
    TTMEVOLVE_PORTABLE_ROOT: p.portable,
    TTMEVOLVE_HOME: p.home,
    TTMEVOLVE_CACHE: p.cache,
    TTMEVOLVE_TEMP: p.temp,
    TAPTAP_MAKER_HOME: p.makerHome,
    TTM_MAKER_HOME: p.makerHome,
    HOME: p.home,
    USERPROFILE: p.home,
    APPDATA: p.appData,
    LOCALAPPDATA: p.localAppData,
    XDG_CACHE_HOME: path.join(p.cache, 'xdg'),
    PIP_CACHE_DIR: p.pipCache,
    npm_config_cache: p.npmCache,
    npm_config_prefix: p.nodePrefix,
    NPM_CONFIG_CACHE: p.npmCache,
    NPM_CONFIG_PREFIX: p.nodePrefix,
    HF_HOME: p.hfHome,
    HUGGINGFACE_HUB_CACHE: path.join(p.hfHome, 'hub'),
    TRANSFORMERS_CACHE: path.join(p.hfHome, 'transformers'),
    SENTENCE_TRANSFORMERS_HOME: p.embeddings,
    TORCH_HOME: path.join(p.cache, 'torch'),
    MPLCONFIGDIR: path.join(p.cache, 'matplotlib'),
    PLAYWRIGHT_BROWSERS_PATH: p.playwright,
    TMP: p.temp,
    TEMP: p.temp,
    TMPDIR: p.temp,
  }
}

function ensureLogFile(): string {
  if (logFile) return logFile
  const root = getProjectRoot()
  const logDir = path.join(root, 'logs', 'gui')
  fs.mkdirSync(logDir, { recursive: true })
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  logFile = path.join(logDir, `electron-${stamp}.log`)
  return logFile
}

function writeLog(message: string) {
  const line = `[${new Date().toISOString()}] ${message}`
  console.log(message)
  try {
    fs.appendFileSync(ensureLogFile(), `${line}\n`, 'utf8')
  } catch {
    // Startup must not fail just because logging failed.
  }
}

function getProjectRoot(): string {
  // Packaged app: extraResources live next to app.asar under resources/
  const resourcesRoot = process.resourcesPath
  if (fs.existsSync(path.join(resourcesRoot, 'server', 'app_server.py'))) {
    return resourcesRoot
  }
  // Dev: electron/dist/main -> ../../..
  const devRoot = path.resolve(__dirname, '..', '..', '..')
  if (fs.existsSync(path.join(devRoot, 'server', 'app_server.py'))) {
    return devRoot
  }
  return process.cwd()
}

function getPythonPath(): string {
  const root = getProjectRoot()
  const isWin = process.platform === 'win32'
  const candidates: string[] = []

  // Prefer embedded Python shipped with the app
  const embeddedPython = isWin
    ? path.join(root, 'vendor', 'python', 'python.exe')
    : path.join(root, 'vendor', 'python', 'bin', 'python3')
  if (fs.existsSync(embeddedPython)) candidates.push(embeddedPython)

  if (process.env.TTM_PYTHON_EXE) candidates.push(process.env.TTM_PYTHON_EXE)

  if (process.env.USERPROFILE) {
    candidates.push(
      path.join(
        process.env.USERPROFILE,
        '.cache',
        'codex-runtimes',
        'codex-primary-runtime',
        'dependencies',
        'python',
        'python.exe'
      )
    )
  }

  const venvPython = isWin
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python3')
  if (fs.existsSync(venvPython)) candidates.push(venvPython)

  // Fallback to system python
  candidates.push(isWin ? 'python' : 'python3')

  for (const candidate of candidates) {
    const result = spawnSync(candidate, ['--version'], {
      encoding: 'utf8',
      timeout: 5000,
    })
    const output = `${result.stdout || ''}${result.stderr || ''}`.trim()
    if (result.status === 0) {
      writeLog(`[Electron] Python selected: ${candidate} ${output}`)
      return candidate
    }
    writeLog(
      `[Electron] Python candidate failed: ${candidate}; status=${result.status}; error=${result.error?.message || ''}; output=${output}`
    )
  }

  throw new Error('No runnable Python found.')
}

function checkHealth(timeoutMs: number): Promise<void> {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const tryHealth = () => {
      const req = http.get(HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          resolve()
        } else {
          retry()
        }
      })
      req.on('error', retry)
      req.setTimeout(300, () => {
        req.destroy()
        retry()
      })

      function retry() {
        if (Date.now() - start > timeoutMs) {
          reject(new Error('Python backend health check timeout'))
          return
        }
        setTimeout(tryHealth, 300)
      }
    }
    tryHealth()
  })
}

function isBackendRunning(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(1000, () => {
      req.destroy()
      resolve(false)
    })
  })
}

function startPythonBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const root = getProjectRoot()
    const python = getPythonPath()
    const script = path.join(root, 'server', 'electron_entry.py')
    const configPath = path.join(root, 'config.json')
    const providerOverride = process.env.TTM_GUI_PROVIDER || ''
    const args = providerOverride ? [script, configPath, providerOverride] : [script, configPath]

    writeLog(`[Electron] Log file: ${ensureLogFile()}`)
    writeLog(`[Electron] Starting Python backend: ${python} ${args.join(' ')}`)

    pythonProcess = spawn(python, args, {
      cwd: root,
      stdio: 'pipe',
      env: {
        ...process.env,
        ...portableChildEnv(root),
        PYTHONIOENCODING: 'utf-8',
        TTM_PYTHON_EXE: python,
      },
    })

    pythonProcess.stdout?.on('data', (data) => {
      writeLog(`[Python] ${data.toString().trim()}`)
    })

    pythonProcess.stderr?.on('data', (data) => {
      writeLog(`[Python:stderr] ${data.toString().trim()}`)
    })

    pythonProcess.on('error', (err) => {
      writeLog(`[Electron] Failed to start Python backend: ${err.message}`)
      reject(new Error(`Failed to start Python backend: ${err.message}`))
    })

    pythonProcess.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        writeLog(`[Electron] Python backend exited with code ${code}`)
      }
      pythonProcess = null
    })

    checkHealth(BACKEND_HEALTH_TIMEOUT_MS)
      .then(() => {
        writeLog('[Electron] Python backend is ready')
        resolve()
      })
      .catch(reject)
  })
}

function stopPythonBackend() {
  if (pythonProcess) {
    writeLog('[Electron] Stopping Python backend')
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(pythonProcess.pid), '/T', '/F'], {
        encoding: 'utf8',
        timeout: 10000,
        windowsHide: true,
      })
    } else {
      pythonProcess.kill('SIGTERM')
    }
    pythonProcess = null
  }
}

function stopBackendOnPort() {
  if (process.platform !== 'win32') return
  try {
    const result = spawnSync('netstat', ['-ano', '-p', 'tcp'], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
    })
    const lines = `${result.stdout || ''}\n${result.stderr || ''}`.split(/\r?\n/)
    const pids = new Set<string>()
    for (const line of lines) {
      if (!line.includes(`:${PYTHON_PORT}`) || !/LISTENING/i.test(line)) continue
      const parts = line.trim().split(/\s+/)
      const pid = parts[parts.length - 1]
      if (/^\d+$/.test(pid)) pids.add(pid)
    }
    for (const pid of pids) {
      writeLog(`[Electron] Stopping backend listener on port ${PYTHON_PORT}: pid=${pid}`)
      spawnSync('taskkill', ['/pid', pid, '/T', '/F'], {
        encoding: 'utf8',
        timeout: 10000,
        windowsHide: true,
      })
    }
  } catch (err: any) {
    writeLog(`[Electron] Failed to stop backend by port: ${err?.message || err}`)
  }
}

function stopWholeAppRuntime() {
  stopPythonBackend()
  stopBackendOnPort()
}

function startupHtml(stage: string, detail: string, percent: number, failed = false): string {
  const safeStage = escapeHtml(stage)
  const safeDetail = escapeHtml(detail)
  const clamped = Math.max(0, Math.min(100, Math.round(percent)))
  const logPath = escapeHtml(path.join(getProjectRoot(), 'logs', 'gui'))
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      width: 100vw;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: "Microsoft YaHei UI", "Noto Sans SC", "Segoe UI", sans-serif;
      color: #060a26;
      background: #f7f9fa;
      overflow: hidden;
    }
    .card {
      width: 396px;
      padding: 22px;
      border: 1px solid rgba(6, 10, 38, 0.12);
      border-radius: 10px;
      background: #ffffff;
      box-shadow: 0 18px 40px rgba(6, 10, 38, 0.1);
    }
    .mark {
      display: inline-flex;
      align-items: center;
      height: 32px;
      padding: 0 12px;
      border-radius: 6px;
      background: #00d9c5;
      color: #ffffff;
      font-weight: 900;
      letter-spacing: 0;
    }
    h1 {
      margin: 14px 0 4px;
      font-size: 18px;
      line-height: 1.3;
    }
    p {
      margin: 0;
      color: rgba(6, 10, 38, 0.62);
      font-size: 13px;
      line-height: 1.6;
      overflow-wrap: anywhere;
    }
    .bar {
      height: 8px;
      margin-top: 18px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(6, 10, 38, 0.08);
    }
    .bar span {
      display: block;
      width: ${clamped}%;
      height: 100%;
      border-radius: inherit;
      background: ${failed ? '#ff5c66' : '#00d9c5'};
      transition: width 0.2s ease;
    }
    .foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
      color: rgba(6, 10, 38, 0.48);
      font-size: 11px;
    }
    button {
      min-height: 28px;
      border: 1px solid rgba(6, 10, 38, 0.12);
      border-radius: 6px;
      background: rgba(6, 10, 38, 0.06);
      color: rgba(6, 10, 38, 0.72);
      font: inherit;
      font-weight: 800;
    }
  </style>
</head>
<body>
  <main class="card">
    <div class="mark">TTM</div>
    <h1>${safeStage}</h1>
    <p>${safeDetail}</p>
    <div class="bar"><span></span></div>
    <div class="foot">
      <span>${failed ? `日志目录：${logPath}` : `启动进度 ${clamped}%`}</span>
      ${failed ? '<button onclick="window.close()">退出</button>' : ''}
    </div>
  </main>
</body>
</html>`
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function createStartupWindow() {
  if (startupWindow && !startupWindow.isDestroyed()) return startupWindow
  startupWindow = new BrowserWindow({
    width: 430,
    height: 235,
    resizable: false,
    maximizable: false,
    minimizable: false,
    frame: false,
    autoHideMenuBar: true,
    show: true,
    title: 'TTMEvolve 启动中',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  startupWindow.on('closed', () => {
    startupWindow = null
  })
  updateStartupProgress('正在启动 TTMEvolve', '正在准备便携运行环境...', 8)
  return startupWindow
}

function updateStartupProgress(stage: string, detail: string, percent: number, failed = false) {
  if (!startupWindow || startupWindow.isDestroyed()) return
  const dataUrl = `data:text/html;charset=utf-8,${encodeURIComponent(startupHtml(stage, detail, percent, failed))}`
  void startupWindow.loadURL(dataUrl)
}

function closeStartupWindow() {
  if (!startupWindow || startupWindow.isDestroyed()) return
  startupWindow.close()
  startupWindow = null
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 800,
    minHeight: 600,
    title: 'TTMEvolve',
    frame: false,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.env.NODE_ENV === 'development') {
    win.loadURL(VITE_DEV_URL)
    win.webContents.openDevTools()
  } else {
    const htmlPath = path.join(getProjectRoot(), 'frontend', 'dist', 'index.html')
    win.loadFile(htmlPath)
  }

  win.on('closed', () => {
    if (mainWindow === win) {
      mainWindow = null
    }
    writeLog('[Electron] Main window closed')
  })

  win.webContents.on('render-process-gone', (_event, details) => {
    writeLog(`[Electron] Renderer process gone: ${JSON.stringify(details)}`)
  })

  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    writeLog(`[Electron] Renderer failed to load ${validatedURL}: ${errorCode} ${errorDescription}`)
  })

  return win
}

function showMainWindowWhenReady(win: BrowserWindow): Promise<void> {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done || win.isDestroyed()) return
      done = true
      win.show()
      win.focus()
      resolve()
    }
    win.once('ready-to-show', finish)
    win.webContents.once('did-finish-load', () => {
      setTimeout(finish, 80)
    })
    setTimeout(finish, 10000)
  })
}

async function startAppWithSplash() {
  createStartupWindow()
  app.on('activate', () => {
    const target = mainWindow || startupWindow
    if (!target) return
    if (target.isMinimized()) target.restore()
    target.focus()
  })
  try {
    updateStartupProgress('检查后端状态', '正在确认本地 Agent 服务是否已经运行...', 18)
    const existing = await isBackendRunning()
    if (existing) {
      updateStartupProgress('复用已运行后端', '检测到本地 Agent 服务已经可用。', 64)
      writeLog('[Electron] Reusing existing Python backend on port 7345')
    } else {
      updateStartupProgress('启动后端服务', '正在启动 Python Agent、Maker MCP 与便携运行环境...', 32)
      await startPythonBackend()
    }

    updateStartupProgress('加载桌面界面', '后端已就绪，正在加载 TTMEvolve GUI...', 82)
    mainWindow = createWindow()
    writeLog('[Electron] Main window created')
    await showMainWindowWhenReady(mainWindow)
    updateStartupProgress('启动完成', 'TTMEvolve 已准备好。', 100)
    closeStartupWindow()
  } catch (err: any) {
    writeLog(`[Electron] Failed to start: ${err?.stack || err}`)
    updateStartupProgress(
      '启动失败',
      `${err.message || String(err)}。请查看日志后重试。`,
      100,
      true
    )
  }
}

function ensureMakerBrowserView(win: BrowserWindow): BrowserView {
  if (makerBrowserView && !makerBrowserView.webContents.isDestroyed()) {
    return makerBrowserView
  }
  makerBrowserView = new BrowserView({
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  makerBrowserView.webContents.setWindowOpenHandler(({ url }) => {
    makerBrowserView?.webContents.loadURL(url)
    return { action: 'deny' }
  })
  makerBrowserView.webContents.on('did-fail-load', (_event, code, description, url) => {
    writeLog(`[MakerBrowser] Failed to load ${url}: ${code} ${description}`)
  })
  makerBrowserView.webContents.on('did-finish-load', () => {
    void syncMakerBrowserDarkMode()
  })
  if (makerBrowserVisible) {
    win.addBrowserView(makerBrowserView)
  }
  void syncMakerBrowserDarkMode()
  return makerBrowserView
}

async function syncMakerBrowserDarkMode() {
  if (!makerBrowserView || makerBrowserView.webContents.isDestroyed()) return
  try {
    await syncMakerPageThemeState()
    if (makerBrowserThemeCssKey) {
      await makerBrowserView.webContents.removeInsertedCSS(makerBrowserThemeCssKey)
      makerBrowserThemeCssKey = null
    }
    makerBrowserThemeCssKey = await makerBrowserView.webContents.insertCSS(
      makerBrowserDarkMode ? MAKER_DARK_CSS : MAKER_LIGHT_CSS,
      { cssOrigin: 'user' }
    )
    await makerBrowserView.webContents
      .executeJavaScript(
        `(() => {
          document.documentElement.dataset.ttmevolveTheme = ${JSON.stringify(
            makerBrowserDarkMode ? 'dark' : 'light'
          )};
          window.dispatchEvent(new Event('resize'));
        })()`,
        true
      )
      .catch(() => undefined)
    await normalizeMakerBrowserTheme()
  } catch (err: any) {
    writeLog(`[MakerBrowser] Failed to apply dark mode: ${err?.message || err}`)
  }
}

async function syncMakerPageThemeState() {
  if (!makerBrowserView || makerBrowserView.webContents.isDestroyed()) return
  const mode = makerBrowserDarkMode ? 'dark' : 'light'
  const script = `
    (() => {
      const mode = ${JSON.stringify(mode)};
      const isDark = mode === 'dark';
      const root = document.documentElement;
      const body = document.body;
      const themeKeys = [
        'theme',
        'color-theme',
        'colorTheme',
        'darkMode',
        'dark-mode',
        'vite-ui-theme',
        'nuxt-color-mode',
        'vueuse-color-scheme',
        'arco-theme',
        'semi-theme',
        'taptap-theme',
        'maker-theme',
        'tapmaker-theme',
        'ttmevolve.maker.theme'
      ];
      for (const target of [localStorage, sessionStorage]) {
        for (const key of themeKeys) {
          try {
            if (target.getItem(key) !== null || /theme|dark|color/i.test(key)) {
              target.setItem(key, mode);
            }
          } catch {}
        }
      }
      for (const el of [root, body].filter(Boolean)) {
        el.classList.toggle('dark', isDark);
        el.classList.toggle('light', !isDark);
        el.classList.toggle('theme-dark', isDark);
        el.classList.toggle('theme-light', !isDark);
        el.classList.toggle('dark-mode', isDark);
        el.classList.toggle('light-mode', !isDark);
        el.setAttribute('data-theme', mode);
        el.setAttribute('data-color-mode', mode);
        el.setAttribute('data-prefers-color-scheme', mode);
        el.style.setProperty('color-scheme', mode, 'important');
      }
      let meta = document.querySelector('meta[name="color-scheme"]');
      if (!meta) {
        meta = document.createElement('meta');
        meta.setAttribute('name', 'color-scheme');
        document.head.appendChild(meta);
      }
      meta.setAttribute('content', mode);
      window.__ttmevolveForcedTheme = mode;
    })()
  `
  await makerBrowserView.webContents.executeJavaScript(script, true).catch(() => undefined)
}

async function normalizeMakerBrowserTheme() {
  if (!makerBrowserView || makerBrowserView.webContents.isDestroyed()) return
  const mode = makerBrowserDarkMode ? 'dark' : 'light'
  const script = `
    (() => {
      const mode = ${JSON.stringify(mode)};
      const skip = new Set(['CANVAS', 'IFRAME', 'IMG', 'PICTURE', 'VIDEO', 'AUDIO', 'SVG']);
      const parseRgb = (value) => {
        const match = String(value || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
        return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
      };
      const nearWhite = (rgb) => rgb && rgb[0] > 232 && rgb[1] > 232 && rgb[2] > 232;
      const nearLightGray = (rgb) => rgb && rgb[0] > 210 && rgb[1] > 210 && rgb[2] > 210 && Math.max(...rgb) - Math.min(...rgb) < 32;
      const rememberInlineStyle = (el) => {
        if (!el.dataset || el.dataset.ttmevolveThemeNormalized) return;
        el.dataset.ttmevolveOriginalStyle = el.getAttribute('style') || '';
        el.dataset.ttmevolveThemeNormalized = 'true';
      };
      const restoreLightTheme = () => {
        const nodes = document.querySelectorAll('[data-ttmevolve-theme-normalized="true"]');
        for (const el of nodes) {
          const original = el.dataset.ttmevolveOriginalStyle || '';
          if (original) {
            el.setAttribute('style', original);
          } else {
            el.removeAttribute('style');
          }
          delete el.dataset.ttmevolveOriginalStyle;
          delete el.dataset.ttmevolveThemeNormalized;
        }
      };
      const scanTheme = () => {
        if (window.__ttmevolveThemeScanning) return;
        window.__ttmevolveThemeScanning = true;
        try {
          if (mode !== 'dark') {
            restoreLightTheme();
            return;
          }
          const nodes = [document.documentElement, document.body, ...document.querySelectorAll('body *')].slice(0, 1800);
          for (const el of nodes) {
            if (!el || skip.has(el.tagName)) continue;
            const style = window.getComputedStyle(el);
            const bg = parseRgb(style.backgroundColor);
            const color = parseRgb(style.color);
            if (nearWhite(bg) || nearLightGray(bg)) {
              rememberInlineStyle(el);
              el.style.setProperty('background-color', '#202020', 'important');
              el.style.setProperty('color', '#e5e5e5', 'important');
              el.style.setProperty('border-color', 'rgba(255,255,255,0.14)', 'important');
            }
            if (color && color[0] < 55 && color[1] < 55 && color[2] < 55) {
              rememberInlineStyle(el);
              el.style.setProperty('color', '#e5e5e5', 'important');
            }
          }
        } finally {
          window.__ttmevolveThemeScanning = false;
        }
      };
      window.__ttmevolveScanTheme = scanTheme;
      scanTheme();
      if (!window.__ttmevolveThemeObserver) {
        window.__ttmevolveThemeObserver = new MutationObserver(() => {
          clearTimeout(window.__ttmevolveThemeTimer);
          window.__ttmevolveThemeTimer = setTimeout(() => {
            if (window.__ttmevolveScanTheme) window.__ttmevolveScanTheme();
          }, 80);
        });
        window.__ttmevolveThemeObserver.observe(document.documentElement, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['class', 'style'],
        });
      }
    })()
  `
  await makerBrowserView.webContents.executeJavaScript(script, true).catch(() => undefined)
}

function attachMakerBrowserView(win: BrowserWindow): BrowserView {
  const view = ensureMakerBrowserView(win)
  if (!makerBrowserVisible) {
    win.addBrowserView(view)
    makerBrowserVisible = true
  }
  return view
}

function detachMakerBrowserView() {
  if (!mainWindow || !makerBrowserView || !makerBrowserVisible) return
  try {
    mainWindow.removeBrowserView(makerBrowserView)
  } catch {
    // BrowserView may already be detached during window shutdown.
  }
  makerBrowserVisible = false
}

ipcMain.handle('window:minimize', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.minimize()
})

ipcMain.handle('window:toggleMaximize', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win) return
  if (win.isMaximized()) {
    win.unmaximize()
  } else {
    win.maximize()
  }
})

ipcMain.handle('window:close', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close()
})

ipcMain.handle('files:openDialog', async (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  const root = getProjectRoot()
  const options: OpenDialogOptions = {
    title: '选择要加入上下文的文件',
    defaultPath: fs.existsSync(path.join(root, 'workspace')) ? path.join(root, 'workspace') : root,
    properties: ['openFile', 'multiSelections'],
  }
  const result = win
    ? await dialog.showOpenDialog(win, options)
    : await dialog.showOpenDialog(options)
  if (result.canceled) return []
  return result.filePaths
})

ipcMain.handle('files:openDirectory', async (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  const root = getProjectRoot()
  const options: OpenDialogOptions = {
    title: '选择 Maker 游戏项目目录',
    defaultPath: fs.existsSync(path.join(root, 'workspace')) ? path.join(root, 'workspace') : root,
    properties: ['openDirectory', 'createDirectory'],
  }
  const result = win
    ? await dialog.showOpenDialog(win, options)
    : await dialog.showOpenDialog(options)
  if (result.canceled) return []
  return result.filePaths
})

ipcMain.handle('makerBrowser:show', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win) return { ok: false, error: 'window not found' }
  attachMakerBrowserView(win)
  return { ok: true }
})

ipcMain.handle('makerBrowser:hide', () => {
  detachMakerBrowserView()
  return { ok: true }
})

ipcMain.handle('makerBrowser:setBounds', (event, rect: { x: number; y: number; width: number; height: number }) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win) return { ok: false, error: 'window not found' }
  const view = attachMakerBrowserView(win)
  const bounds = {
    x: Math.max(0, Math.round(Number(rect.x) || 0)),
    y: Math.max(0, Math.round(Number(rect.y) || 0)),
    width: Math.max(1, Math.round(Number(rect.width) || 1)),
    height: Math.max(1, Math.round(Number(rect.height) || 1)),
  }
  view.setBounds(bounds)
  return { ok: true, bounds }
})

ipcMain.handle('makerBrowser:navigate', async (event, url: string) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (!win) return { ok: false, error: 'window not found' }
  const nextUrl = String(url || '').trim()
  if (!nextUrl) return { ok: false, error: 'url is required' }
  const view = attachMakerBrowserView(win)
  await view.webContents.loadURL(nextUrl)
  await syncMakerBrowserDarkMode()
  return { ok: true, url: view.webContents.getURL(), title: view.webContents.getTitle() }
})

ipcMain.handle('makerBrowser:reload', () => {
  if (!makerBrowserView || makerBrowserView.webContents.isDestroyed()) {
    return { ok: false, error: 'browser not ready' }
  }
  makerBrowserView.webContents.reload()
  return { ok: true }
})

ipcMain.handle('makerBrowser:setDarkMode', async (_event, enabled: boolean, options?: { reload?: boolean }) => {
  makerBrowserDarkMode = Boolean(enabled)
  nativeTheme.themeSource = makerBrowserDarkMode ? 'dark' : 'light'
  await syncMakerBrowserDarkMode()
  if (makerBrowserView && !makerBrowserView.webContents.isDestroyed()) {
    makerBrowserView.webContents.invalidate()
    if (options?.reload && makerBrowserView.webContents.getURL()) {
      makerBrowserView.webContents.reload()
    }
  }
  return { ok: true, enabled: makerBrowserDarkMode }
})

configureElectronPortablePaths()

const singleInstanceLock = app.requestSingleInstanceLock()
if (!singleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const target = mainWindow || startupWindow
    if (!target) return
    if (target.isMinimized()) target.restore()
    target.focus()
  })

  app.whenReady().then(() => {
  void startAppWithSplash()
  /*
  try {
    mainWindow = createWindow()
    writeLog('[Electron] Main window created')
  } catch (err: any) {
    writeLog(`[Electron] Failed to start: ${err?.stack || err}`)
    dialog.showErrorBox(
      '启动失败',
      `${err.message || String(err)}\n\n日志目录: ${path.join(getProjectRoot(), 'logs', 'gui')}`
    )
    app.quit()
    return
  }

  void (async () => {
    try {
      const existing = await isBackendRunning()
      if (existing) {
        writeLog('[Electron] Reusing existing Python backend on port 7345')
      } else {
        await startPythonBackend()
      }
    } catch (err: any) {
      writeLog(`[Electron] Python backend failed to start: ${err?.stack || err}`)
      writeLog(
        `[Electron] Backend startup is degraded; keeping GUI open. Logs: ${path.join(
          getProjectRoot(),
          'logs',
          'gui'
        )}`
      )
    }
  })()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow()
    }
  })
  */
  })
}

app.on('window-all-closed', () => {
  stopWholeAppRuntime()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopWholeAppRuntime()
})

app.on('will-quit', () => {
  stopWholeAppRuntime()
})
