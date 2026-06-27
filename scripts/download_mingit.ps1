$url = 'https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/MinGit-2.45.2-64-bit.zip'
$out = 'D:\CC\TTMEvolve\vendor\_cache\MinGit-2.45.2-64-bit.zip'
Write-Host "Downloading Git from $url"
try {
    Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 300
    Write-Host "Download complete"
    Get-Item $out | Select-Object Length, Name
} catch {
    Write-Host ("Error: " + $Error[0].Exception.Message)
}
