# start.ps1 - TTMEvolve single-entry launch
# Detects Python, creates venv, prepares/downloads environment, starts Agent

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
}

Write-Info "Working directory: $PROJECT_ROOT"

# If --gui is requested, delegate to start-gui.ps1
if ($args -contains "--gui") {
    $remainingArgs = $args | Where-Object { $_ -ne "--gui" }
    $guiScript = Join-Path $PROJECT_ROOT "start-gui.ps1"
    & $guiScript @remainingArgs
    exit $LASTEXITCODE
}

# Detect Python: prefer vendor/python, fallback to system python
$vendorPython = Join-Path $PROJECT_ROOT "vendor\python\python.exe"
$python = $null
if (Test-Path $vendorPython) {
    $python = Get-Command $vendorPython -ErrorAction SilentlyContinue
    if ($python) {
        Write-Info "Using embedded Python: $vendorPython"
        $env:TTM_PYTHON_EXE = $vendorPython
    }
}
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Error "python not found. Please install Python and add it to PATH, or run scripts/build_embedded.py."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Info "Using system Python: $(python --version)"
} else {
    Write-Info "Embedded Python version: $(&$python --version)"
}

# Detect Node: prefer vendor/node for frontend/electron builds
$vendorNode = Join-Path $PROJECT_ROOT "vendor\node\node.exe"
if (Test-Path $vendorNode) {
    $env:PATH = "$($vendorNode | Split-Path -Parent);$($env:PATH)"
    $env:TTM_NODE_EXE = $vendorNode
    Write-Info "Using embedded Node: $vendorNode"
}

# Detect Git: prefer vendor/git for git_commit tool
$vendorGit = Join-Path $PROJECT_ROOT "vendor\git\cmd\git.exe"
if (Test-Path $vendorGit) {
    $env:PATH = "$($vendorGit | Split-Path -Parent);$($env:PATH)"
    $env:TTM_GIT_EXE = $vendorGit
    Write-Info "Using embedded Git: $vendorGit"
}

# Load embedded environment variables
$envFile = Join-Path $PROJECT_ROOT ".env.embedded"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Write-Info "Loaded .env.embedded"
}

Initialize-PortableRuntime

$pythonExe = $python.Source

# Auto-create config.json
if (-not (Test-Path config.json)) {
    Write-Info "config.json missing, copying from config.example.json..."
    Copy-Item config.example.json config.json -Force
    Write-Info "config.json created. Please edit it and restart."
    Read-Host "Press Enter to exit"
    exit 1
}

$venvPython = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"

# Create venv if needed
if (-not (Test-Path .venv)) {
    Write-Info "Creating virtual environment..."
    & $pythonExe -m venv .venv --system-site-packages
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        Read-Host "Press Enter to exit"
        exit 1
    }
}

if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment Python not found: $venvPython"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check/prepare environment
Write-Info "Checking/preparing environment..."
& $venvPython scripts\bootstrap.py
$bootstrapCode = $LASTEXITCODE

if ($bootstrapCode -eq 0) {
    # Normal start
    Write-Info "Starting self-evolving TapMaker Agent..."
    if ($args.Count -gt 0) {
        & $venvPython main.py @args
    } else {
        & $venvPython main.py
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Agent exited with code: $LASTEXITCODE"
        Read-Host "Press Enter to exit"
        exit $LASTEXITCODE
    }
    exit 0
}

if ($bootstrapCode -eq 2) {
    # Bootstrap says fallback to mock
    Write-Info "Environment not fully ready. Starting Mock mode for testing..."
    if ($args.Count -gt 0) {
        & $venvPython main.py --provider mock @args
    } else {
        & $venvPython main.py --provider mock
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Mock mode failed, exit code: $LASTEXITCODE"
        Read-Host "Press Enter to exit"
        exit $LASTEXITCODE
    }
    Read-Host "Press Enter to exit"
    exit 0
}

# Fatal bootstrap error
Write-Error "Environment initialization failed."
Read-Host "Press Enter to exit"
exit $bootstrapCode
