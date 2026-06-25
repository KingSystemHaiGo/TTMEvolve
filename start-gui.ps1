# start-gui.ps1 - TTMEvolve desktop GUI single-entry launch
# Builds frontend/electron if needed, then opens Electron window.

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Hidden GUI launchers do not always have a console handle.
}
$OutputEncoding = [System.Text.Encoding]::UTF8

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PROJECT_ROOT

function Write-Info($msg) { Write-Host "[TTMEvolve] $msg" }
function Write-Error($msg) { Write-Host "[TTMEvolve] Error: $msg" -ForegroundColor Red }
function Initialize-PortableRuntime {
    $portable = Join-Path $PROJECT_ROOT "portable"
    $portableHome = Join-Path $portable "home"
    $cache = Join-Path $portable "cache"
    $tmp = Join-Path $portable "tmp"
    $appData = Join-Path $portableHome "AppData\Roaming"
    $localAppData = Join-Path $portableHome "AppData\Local"
    $dirs = @(
        $portable, $portableHome, $cache, $tmp, $appData, $localAppData,
        (Join-Path $portableHome ".taptap-maker"),
        (Join-Path $cache "npm"),
        (Join-Path $cache "pip"),
        (Join-Path $cache "huggingface"),
        (Join-Path $portable "node-global")
    )
    foreach ($dir in $dirs) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $env:TTMEVOLVE_ROOT = $PROJECT_ROOT
    $env:TTMEVOLVE_PORTABLE_ROOT = $portable
    $env:TTMEVOLVE_HOME = $portableHome
    $env:TTMEVOLVE_CACHE = $cache
    $env:TTMEVOLVE_TEMP = $tmp
    $makerHome = Join-Path $portableHome ".taptap-maker"
    $env:TAPTAP_MAKER_HOME = $makerHome
    $env:TTM_MAKER_HOME = $makerHome
    $env:HOME = $portableHome
    $env:USERPROFILE = $portableHome
    $env:APPDATA = $appData
    $env:LOCALAPPDATA = $localAppData
    $env:XDG_CACHE_HOME = Join-Path $cache "xdg"
    $env:PIP_CACHE_DIR = Join-Path $cache "pip"
    $env:npm_config_cache = Join-Path $cache "npm"
    $env:npm_config_prefix = Join-Path $portable "node-global"
    $env:NPM_CONFIG_CACHE = $env:npm_config_cache
    $env:NPM_CONFIG_PREFIX = $env:npm_config_prefix
    $env:HF_HOME = Join-Path $cache "huggingface"
    $env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME "hub"
    $env:TRANSFORMERS_CACHE = Join-Path $env:HF_HOME "transformers"
    $vendorEmbeddings = Join-Path $PROJECT_ROOT "vendor\embeddings"
    $env:SENTENCE_TRANSFORMERS_HOME = $(if (Test-Path $vendorEmbeddings) { $vendorEmbeddings } else { Join-Path $cache "sentence-transformers" })
    $env:TORCH_HOME = Join-Path $cache "torch"
    $env:MPLCONFIGDIR = Join-Path $cache "matplotlib"
    $vendorPlaywright = Join-Path $PROJECT_ROOT "vendor\playwright"
    $env:PLAYWRIGHT_BROWSERS_PATH = $(if (Test-Path $vendorPlaywright) { $vendorPlaywright } else { Join-Path $cache "playwright" })
    $env:TMP = $tmp
    $env:TEMP = $tmp
    $env:TMPDIR = $tmp
    Write-Info "Portable runtime: $portable"
    Write-Log "Portable runtime: $portable"
}

# Log to file for debugging flash-close issues
$LogDir = Join-Path $PROJECT_ROOT "logs\gui"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("start-gui-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$LegacyLogFile = Join-Path $PROJECT_ROOT "start-gui.log"
function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    $line | Out-File -FilePath $LogFile -Append -Encoding utf8
    $line | Out-File -FilePath $LegacyLogFile -Append -Encoding utf8
}
function Test-Executable($exe, [string[]]$argv = @("--version")) {
    try {
        $output = & $exe @argv 2>&1
        $code = $LASTEXITCODE
        Write-Log "Probe: $exe $($argv -join ' ') -> exit $code; output: $($output -join ' ')"
        return $code -eq 0
    }
    catch {
        Write-Log "Probe failed: $exe $($argv -join ' '): $($_.Exception.Message)"
        return $false
    }
}
function Format-ProcessLine($item) {
    if ($item -is [System.Management.Automation.ErrorRecord]) {
        return $item.ToString()
    }
    return [string]$item
}

function Should-HideConsoleLine([string]$line) {
    return (
        $line -match "libpng warning: iCCP: known incorrect sRGB profile" -or
        $line -match "llama_context: n_ctx_seq .* n_ctx_train" -or
        $line -match "Loading weights:"
    )
}

function Invoke-Logged($label, $exe, [string[]]$argv, $cwd = $PROJECT_ROOT) {
    Write-Log "RUN [$label]: $exe $($argv -join ' ') (cwd=$cwd)"
    Push-Location $cwd
    try {
        & $exe @argv 2>&1 | ForEach-Object {
            $line = Format-ProcessLine $_
            if (-not (Should-HideConsoleLine $line)) {
                Write-Host $line
            }
            $line | Out-File -FilePath $LogFile -Append -Encoding utf8
        }
        $code = $LASTEXITCODE
        Write-Log "EXIT [$label]: $code"
        return $code
    }
    finally {
        Pop-Location
    }
}
function Test-HttpOk($url) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500
    }
    catch {
        return $false
    }
}
function Start-WebFallback($pythonExe) {
    Write-Info "Electron 桌面壳启动失败，切换到浏览器调试模式..."
    Write-Log "Starting browser fallback"

    if (-not (Test-HttpOk "http://127.0.0.1:7345/health")) {
        $backend = Start-Process -FilePath $pythonExe `
            -ArgumentList @("main.py", "--serve") `
            -WorkingDirectory $PROJECT_ROOT `
            -PassThru `
            -WindowStyle Hidden
        Write-Info "已启动 App Server: http://127.0.0.1:7345"
        Write-Log "Fallback backend PID: $($backend.Id)"
    } else {
        Write-Info "App Server 已在运行: http://127.0.0.1:7345"
    }

    if (-not (Test-HttpOk "http://127.0.0.1:5173/")) {
        $frontendRoot = Join-Path $PROJECT_ROOT "frontend"
        $frontend = Start-Process -FilePath "npm.cmd" `
            -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
            -WorkingDirectory $frontendRoot `
            -PassThru `
            -WindowStyle Hidden
        Write-Info "已启动前端 Dev Server: http://127.0.0.1:5173/"
        Write-Log "Fallback frontend PID: $($frontend.Id)"
    } else {
        Write-Info "前端 Dev Server 已在运行: http://127.0.0.1:5173/"
    }

    Write-Info "请在浏览器打开: http://127.0.0.1:5173/"
    Write-Info "运行日志目录: $LogDir"
}

function Start-ElectronDetached($electron, [string[]]$argv, $cwd) {
    Write-Log "RUN [electron-detached]: $electron $($argv -join ' ') (cwd=$cwd)"
    $outFile = Join-Path $LogDir ("electron-stdout-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $errFile = Join-Path $LogDir ("electron-stderr-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $proc = Start-Process -FilePath $electron `
        -ArgumentList $argv `
        -WorkingDirectory $cwd `
        -RedirectStandardOutput $outFile `
        -RedirectStandardError $errFile `
        -PassThru `
        -WindowStyle Hidden
    Write-Log "Electron detached PID: $($proc.Id)"
    Write-Log "Electron detached stdout: $outFile"
    Write-Log "Electron detached stderr: $errFile"
    return $proc
}

function Test-OutputStale([string[]]$sources, [string[]]$outputs) {
    foreach ($out in $outputs) {
        if (-not (Test-Path $out)) { return $true }
    }
    $oldestOutput = ($outputs | ForEach-Object { (Get-Item $_).LastWriteTimeUtc } | Sort-Object | Select-Object -First 1)
    foreach ($src in $sources) {
        if (Test-Path $src) {
            $item = Get-Item $src
            if ($item.PSIsContainer) {
                $newestSource = Get-ChildItem -Path $src -Recurse -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTimeUtc -Descending |
                    Select-Object -First 1
                if ($newestSource -and $newestSource.LastWriteTimeUtc -gt $oldestOutput) {
                    return $true
                }
            } elseif ($item.LastWriteTimeUtc -gt $oldestOutput) {
                return $true
            }
        }
    }
    return $false
}

Write-Log "=== start-gui.ps1 started ==="

try {
    Write-Info "启动桌面 GUI..."
    Write-Info "工作目录: $PROJECT_ROOT"
    Write-Info "日志文件: $LogFile"
    Write-Log "Project root: $PROJECT_ROOT"

    # Detect Python
    $vendorPython = Join-Path $PROJECT_ROOT "vendor\python\python.exe"
    $pythonExe = $null
    if (Test-Path $vendorPython) {
        if (Test-Executable $vendorPython) {
            $pythonExe = $vendorPython
            Write-Info "使用内嵌 Python: $vendorPython"
            $env:TTM_PYTHON_EXE = $vendorPython
        }
    }
    if (-not $pythonExe) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd -and (Test-Executable $pythonCmd.Source)) {
            $pythonExe = $pythonCmd.Source
            Write-Info "使用系统 Python: $(& $pythonExe --version 2>&1)"
        }
    }
    if (-not $pythonExe) {
        $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if (Test-Path $codexPython) {
            if (Test-Executable $codexPython) {
                $pythonExe = $codexPython
                Write-Info "使用 Codex 内置 Python: $codexPython"
            }
        }
    }
    if (-not $pythonExe) {
        $pyCmd = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCmd -and (Test-Executable $pyCmd.Source @("-3", "--version"))) {
            $pythonExe = $pyCmd.Source
            Write-Info "使用 Python Launcher: $(& $pythonExe -3 --version 2>&1)"
        }
    }
    if (-not $pythonExe) {
        throw "未找到可运行的 Python。请安装 Python 并加入 PATH，或运行 scripts/build_embedded.py。"
    }
    Write-Log "Python candidate: $pythonExe"

    # Detect Node (required for Electron)
    $vendorNode = Join-Path $PROJECT_ROOT "vendor\node\node.exe"
    $nodeExe = $null
    if (Test-Path $vendorNode) {
        if (Test-Executable $vendorNode) {
            $nodeExe = $vendorNode
            Write-Info "使用内嵌 Node: $vendorNode"
            $env:PATH = "$($vendorNode | Split-Path -Parent);$($env:PATH)"
            $env:TTM_NODE_EXE = $vendorNode
        }
    }
    if (-not $nodeExe) {
        $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        if (-not $nodeCmd -or -not (Test-Executable $nodeCmd.Source)) {
            throw "未找到 node.exe。Electron GUI 需要 Node.js，请安装或运行 scripts/build_embedded.py。"
        }
        $nodeExe = $nodeCmd.Source
        Write-Info "使用系统 Node: $(& $nodeExe --version)"
    }
    Write-Log "Node: $nodeExe"

    # Detect Git
    $vendorGit = Join-Path $PROJECT_ROOT "vendor\git\cmd\git.exe"
    if (Test-Path $vendorGit) {
        $env:PATH = "$($vendorGit | Split-Path -Parent);$($env:PATH)"
        $env:TTM_GIT_EXE = $vendorGit
        Write-Info "使用内嵌 Git: $vendorGit"
    }

    # Load embedded env
    $envFile = Join-Path $PROJECT_ROOT ".env.embedded"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
        Write-Info "已加载 .env.embedded"
    }

    Initialize-PortableRuntime

    # Auto-create config.json
    if (-not (Test-Path config.json)) {
        Write-Info "config.json 不存在，正在从 config.example.json 复制..."
        Copy-Item config.example.json config.json -Force
        Write-Info "已创建 config.json，请按需修改后重新启动。"
        Read-Host "按 Enter 退出"
        exit 1
    }

    $venvPython = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"

    # Create venv if needed
    if (-not (Test-Path .venv)) {
        Write-Info "创建虚拟环境..."
        $createCode = Invoke-Logged "create venv" $pythonExe @("-m", "venv", ".venv", "--system-site-packages")
        if ($createCode -ne 0) {
            Write-Info "虚拟环境创建失败，将直接使用当前 Python。"
        }
    }

    $runtimePython = $pythonExe
    if (Test-Path $venvPython) {
        if (Test-Executable $venvPython) {
            $runtimePython = $venvPython
            Write-Info "使用虚拟环境 Python: $venvPython"
        } else {
            Write-Info "检测到虚拟环境 Python 不可用，已回退到: $pythonExe"
            Write-Log "Broken venv python ignored: $venvPython"
        }
    } else {
        Write-Info "未找到虚拟环境 Python，使用: $pythonExe"
    }
    $env:TTM_PYTHON_EXE = $runtimePython
    Remove-Item Env:\TTM_FALLBACK_MOCK -ErrorAction SilentlyContinue
    Write-Log "Runtime Python: $runtimePython"

    # Check/prepare environment
    Write-Info "检查/准备环境..."
    $bootstrapCode = Invoke-Logged "bootstrap" $runtimePython @("scripts\bootstrap.py")
    Write-Log "bootstrap exit code: $bootstrapCode"

    if ($bootstrapCode -ne 0 -and $bootstrapCode -ne 2) {
        throw "环境初始化失败。"
    }

    if ($bootstrapCode -eq 2) {
        throw "环境未完全就绪。当前阶段不再自动降级到 mock，请查看日志修复依赖或模型。"
    }
    Write-Info "GUI 后端使用 config.json 中的真实 provider 启动。"
    Write-Log "GUI backend provider override: $($env:TTM_GUI_PROVIDER)"

    # Helper to resolve npm .bin executable (uses .cmd on Windows)
    function Get-NpmBin($dir, $name) {
        $base = Join-Path (Join-Path (Join-Path (Join-Path $PROJECT_ROOT $dir) "node_modules") ".bin") $name
        if ($IsWindows -or ($env:OS -eq "Windows_NT")) {
            $cmd = "$base.cmd"
            if (Test-Path $cmd) { return $cmd }
        }
        if (Test-Path $base) { return $base }
        # fallback: search PATH
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        throw "找不到 $name，请确认已运行 npm install。"
    }

    # Build frontend if needed
    $rendererHtml = Join-Path $PROJECT_ROOT "electron\dist\renderer\index.html"
    $frontendSources = @(
        (Join-Path $PROJECT_ROOT "frontend\src"),
        (Join-Path $PROJECT_ROOT "frontend\index.html"),
        (Join-Path $PROJECT_ROOT "frontend\vite.config.ts")
    )
    $frontendStale = Test-OutputStale $frontendSources @($rendererHtml)
    if ($frontendStale) {
        Write-Info "构建前端..."
        $vite = Get-NpmBin "frontend" "vite"
        Write-Log "Building frontend with: $vite"
        $buildCode = Invoke-Logged "frontend build" $vite @("build") (Join-Path $PROJECT_ROOT "frontend")
        if ($buildCode -ne 0) {
            throw "前端构建失败。"
        }
    } else {
        Write-Info "前端产物已存在，跳过构建。"
    }

    # Build electron main/preload if needed
    $electronMain = Join-Path $PROJECT_ROOT "electron\dist\main\index.js"
    $electronPreload = Join-Path $PROJECT_ROOT "electron\dist\preload\index.js"
    $electronSources = @(
        (Join-Path $PROJECT_ROOT "electron\main"),
        (Join-Path $PROJECT_ROOT "electron\preload"),
        (Join-Path $PROJECT_ROOT "electron\vite.main.config.ts"),
        (Join-Path $PROJECT_ROOT "electron\vite.preload.config.ts"),
        (Join-Path $PROJECT_ROOT "electron\tsconfig.json")
    )
    $electronStale = Test-OutputStale $electronSources @($electronMain, $electronPreload)
    if ($electronStale) {
        Write-Info "构建 Electron 主进程..."
        $tsc = Get-NpmBin "electron" "tsc"
        $viteMain = Get-NpmBin "electron" "vite"
        Write-Log "Building electron with tsc=$tsc vite=$viteMain"
        $tscCode = Invoke-Logged "electron tsc" $tsc @() (Join-Path $PROJECT_ROOT "electron")
        if ($tscCode -ne 0) { throw "tsc 失败" }
        $mainCode = Invoke-Logged "electron main build" $viteMain @("build", "--config", "vite.main.config.ts") (Join-Path $PROJECT_ROOT "electron")
        if ($mainCode -ne 0) { throw "vite main 失败" }
        $preloadCode = Invoke-Logged "electron preload build" $viteMain @("build", "--config", "vite.preload.config.ts") (Join-Path $PROJECT_ROOT "electron")
        if ($preloadCode -ne 0) { throw "vite preload 失败" }
    } else {
        Write-Info "Electron 主进程产物已存在，跳过构建。"
    }

    # Launch Electron
    Write-Info "正在打开 TTMEvolve 桌面窗口..."
    $electron = Get-NpmBin "electron" "electron"
    Write-Log "Launching electron: $electron"
    $env:NODE_ENV = "production"
    $electronProc = Start-ElectronDetached $electron @(".") (Join-Path $PROJECT_ROOT "electron")
    Start-Sleep -Seconds 3
    if ($electronProc.HasExited) {
        Write-Log "Electron detached exited early: $($electronProc.ExitCode)"
        Write-Error "Electron 启动后立即退出，已切换到浏览器调试模式。"
        Start-WebFallback $runtimePython
        exit 0
    }
    Write-Info "桌面窗口已启动。详细日志: $LogDir"
    Write-Log "Electron detached startup accepted."
}
catch {
    $err = $_.Exception.Message
    Write-Error $err
    Write-Log "ERROR: $err"
    Write-Log $_.ScriptStackTrace
    Read-Host "按 Enter 退出"
    exit 1
}
finally {
    Write-Log "=== start-gui.ps1 ended ==="
}
