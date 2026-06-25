# start-practice.ps1 - one-click Maker practice setup + GUI launch

[CmdletBinding()]
param(
    [string]$ProjectName = "smoke-maker-game",
    [string]$ProjectDir = "",
    [switch]$SkipMakerInstall,
    [switch]$SkipMakerInit,
    [switch]$NoGui,
    [switch]$DryRun
)

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Hidden GUI launchers do not always have a console handle.
}
$OutputEncoding = [System.Text.Encoding]::UTF8

$PROJECT_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PROJECT_ROOT

function Write-Info($msg) { Write-Host "[TTMEvolve Practice] $msg" }
function Write-Warn($msg) { Write-Host "[TTMEvolve Practice] Warn: $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[TTMEvolve Practice] Error: $msg" -ForegroundColor Red }

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
        (Join-Path $cache "playwright"),
        (Join-Path $portable "node-global")
    )
    foreach ($dir in $dirs) {
        if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    }
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

function Add-PortableBins {
    $vendorNode = Join-Path $PROJECT_ROOT "vendor\node"
    $vendorGit = Join-Path $PROJECT_ROOT "vendor\git\cmd"
    if (Test-Path (Join-Path $vendorNode "node.exe")) {
        $env:PATH = "$vendorNode;$($env:PATH)"
        $env:TTM_NODE_EXE = Join-Path $vendorNode "node.exe"
        Write-Info "Using embedded Node: $env:TTM_NODE_EXE"
    }
    if (Test-Path (Join-Path $vendorGit "git.exe")) {
        $env:PATH = "$vendorGit;$($env:PATH)"
        $env:TTM_GIT_EXE = Join-Path $vendorGit "git.exe"
        Write-Info "Using embedded Git: $env:TTM_GIT_EXE"
    }
}

function Resolve-Npx {
    $cmd = Get-Command "npx.cmd" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command "npx" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "npx not found. Install Node.js or place portable Node under vendor/node."
}

function Invoke-Step($label, $exe, [string[]]$argv, $cwd = $PROJECT_ROOT) {
    Write-Info "$label"
    Write-Host "  $exe $($argv -join ' ')" -ForegroundColor DarkGray
    Write-Host "  cwd: $cwd" -ForegroundColor DarkGray
    if ($DryRun) { return 0 }
    Push-Location $cwd
    try {
        & $exe @argv
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            throw "$label failed with exit code $code"
        }
        return $code
    }
    finally {
        Pop-Location
    }
}

function Convert-ToConfigPath([string]$path) {
    $full = [System.IO.Path]::GetFullPath($path)
    $root = [System.IO.Path]::GetFullPath($PROJECT_ROOT)
    if (-not $root.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $root = $root + [System.IO.Path]::DirectorySeparatorChar
    }
    $rootUri = [System.Uri]::new($root)
    $fullUri = [System.Uri]::new($full)
    $rel = [System.Uri]::UnescapeDataString($rootUri.MakeRelativeUri($fullUri).ToString())
    if (-not $rel.StartsWith("../") -and -not $rel.StartsWith("..\") -and -not [System.IO.Path]::IsPathRooted($rel)) {
        return "./" + ($rel -replace "\\", "/")
    }
    return $full -replace "\\", "/"
}

function Ensure-ObjectMember($obj, [string]$name, $value) {
    if (-not ($obj.PSObject.Properties.Name -contains $name)) {
        $obj | Add-Member -NotePropertyName $name -NotePropertyValue $value
    }
}

function Update-TTMEvolveConfig([string]$makerProjectDir) {
    $configPath = Join-Path $PROJECT_ROOT "config.json"
    if (-not (Test-Path $configPath)) {
        if (-not (Test-Path (Join-Path $PROJECT_ROOT "config.example.json"))) {
            throw "config.json missing and config.example.json not found."
        }
        Write-Info "Creating config.json from config.example.json"
        if (-not $DryRun) { Copy-Item (Join-Path $PROJECT_ROOT "config.example.json") $configPath -Force }
    }
    if ($DryRun -and -not (Test-Path $configPath)) {
        Write-Info "Dry run: config.json would be created and pointed at $makerProjectDir"
        return
    }

    $cfg = Get-Content $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Ensure-ObjectMember $cfg "runtime" ([pscustomobject]@{})
    Ensure-ObjectMember $cfg "maker_mcp" ([pscustomobject]@{})
    Ensure-ObjectMember $cfg.maker_mcp "env" ([pscustomobject]@{})
    Ensure-ObjectMember $cfg.maker_mcp.env "TAPTAP_MCP_ENV" "production"
    Ensure-ObjectMember $cfg.maker_mcp "command" "cmd.exe"
    Ensure-ObjectMember $cfg.maker_mcp "args" @("/d", "/s", "/c", "npx.cmd", "-y", "-p", "@taptap/maker@0.0.19", "taptap-maker")

    $configProjectPath = Convert-ToConfigPath $makerProjectDir
    $cfg.project_root = $configProjectPath
    $cfg.storage_root = "./storage"
    $cfg.runtime.portable_root = "./portable"
    $cfg.maker_mcp.cwd = $configProjectPath

    Write-Info "Writing config project_root=$configProjectPath"
    if (-not $DryRun) {
        $cfg | ConvertTo-Json -Depth 100 | Set-Content -Path $configPath -Encoding UTF8
    }
}

function Test-MakerInitialized([string]$makerProjectDir) {
    return (
        (Test-Path (Join-Path $makerProjectDir ".maker-mcp\config.json")) -or
        (Test-Path (Join-Path $makerProjectDir ".project\settings.json"))
    )
}

function Wait-Endpoint([string]$url, [int]$seconds = 20) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { return $true }
        }
        catch {}
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Show-DiagnosticUrls {
    Write-Info "Diagnostics:"
    Write-Host "  http://127.0.0.1:7345/runtime/portable"
    Write-Host "  http://127.0.0.1:7345/maker/setup-status"
    Write-Host "  http://127.0.0.1:7345/maker/tool-audit"
    Write-Host "  http://127.0.0.1:7345/runtime/readiness"
}

try {
    Write-Info "One-click Maker practice setup"
    Write-Info "Agent root: $PROJECT_ROOT"
    Initialize-PortableRuntime
    Add-PortableBins

    if (-not $ProjectDir) {
        $ProjectDir = Join-Path (Join-Path $PROJECT_ROOT "workspace") $ProjectName
    }
    $ProjectDir = [System.IO.Path]::GetFullPath($ProjectDir)
    if ($ProjectDir -eq [System.IO.Path]::GetFullPath($PROJECT_ROOT)) {
        throw "Refusing to use the TTMEvolve app root as the Maker game project."
    }
    Write-Info "Maker project: $ProjectDir"
    if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $ProjectDir | Out-Null }

    Update-TTMEvolveConfig $ProjectDir

    $npx = Resolve-Npx
    if (-not $SkipMakerInstall) {
        Invoke-Step "Installing/refreshing Maker MCP for Codex/Cursor/Claude" $npx @("-y", "@taptap/maker", "install", "--ide", "codex,cursor,claude")
    } else {
        Write-Warn "Skipping Maker MCP install because -SkipMakerInstall was passed."
    }

    if (-not $SkipMakerInit) {
        if (Test-MakerInitialized $ProjectDir) {
            Write-Info "Maker project already initialized."
        } else {
            Invoke-Step "Initializing Maker project" $npx @("-y", "@taptap/maker", "init") $ProjectDir
        }
    } else {
        Write-Warn "Skipping Maker init because -SkipMakerInit was passed."
    }

    if ($NoGui) {
        Show-DiagnosticUrls
        Write-Info "Done. GUI launch skipped."
        exit 0
    }

    Write-Info "Launching TTMEvolve GUI..."
    if (-not $DryRun) {
        & (Join-Path $PROJECT_ROOT "start-gui.ps1")
        if (Wait-Endpoint "http://127.0.0.1:7345/runtime/portable" 25) {
            Write-Info "Backend is ready."
        } else {
            Write-Warn "Backend endpoint did not answer yet; GUI may still be starting."
        }
    }
    Show-DiagnosticUrls
    Write-Info "Practice setup complete. In the chat, ask for one tiny Maker smoke task."
}
catch {
    Write-Fail $_.Exception.Message
    if (-not $NoGui) { Read-Host "Press Enter to exit" | Out-Null }
    exit 1
}
