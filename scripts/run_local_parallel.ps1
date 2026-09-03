# High-volume parallel harvest on local PC (target ~10k rows, prefer high/medium).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/run_local_parallel.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/run_local_parallel.ps1 -Workers 12

param(
  [int]$Workers = 8,
  [int]$Loops = 0,
  [int]$Queries = 12,
  [int]$PerQuery = 30,
  [int]$MaxFetch = 120,
  [string]$Audience = "founders",
  [string]$NichesFile = "data\niches_usa.txt"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Missing venv python at $python"
}

$logDir = Join-Path $PWD "data\local_runs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$niches = Get-Content $NichesFile |
  ForEach-Object { $_.Trim() } |
  Where-Object { $_ -and -not $_.StartsWith("#") }

if (-not $niches) { throw "No niches found in $NichesFile" }

Write-Host "Local parallel harvest workers=$Workers niches=$($niches.Count) loops=$Loops audience=$Audience"
Write-Host "Logs: $logDir"
Write-Host "Stop: Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -match 'run_local_parallel|community_scanner\.cli' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }"

$script:loop = 1
while ($true) {
  if ($Loops -gt 0 -and $script:loop -gt $Loops) { break }
  Write-Host "=== cycle $($script:loop) ==="

  for ($i = 0; $i -lt $niches.Count; $i += $Workers) {
    $batch = $niches[$i..([Math]::Min($i + $Workers - 1, $niches.Count - 1))]
    $jobs = @()
    foreach ($niche in $batch) {
      $safe = ($niche -replace '[^a-zA-Z0-9_-]', '_')
      $log = Join-Path $logDir ("cycle{0}_{1}_{2}.log" -f $script:loop, $i, $safe)
      Write-Host "start niche=$niche -> $log"
      $jobs += Start-Job -ScriptBlock {
        param($py, $root, $niche, $audience, $queries, $perQuery, $maxFetch, $log)
        Set-Location $root
        & $py -m community_scanner.cli run `
          --niche $niche `
          --geo USA `
          --audience $audience `
          --queries $queries `
          --per-query $perQuery `
          --max-fetch $maxFetch *>> $log
        return $LASTEXITCODE
      } -ArgumentList $python, $PWD.Path, $niche, $Audience, $Queries, $PerQuery, $MaxFetch, $log
    }
    $jobs | Wait-Job | Out-Null
    foreach ($job in $jobs) {
      $code = Receive-Job $job
      if ($code -ne 0) {
        Write-Host "WARN job $($job.Id) exit=$code"
      }
      Remove-Job $job -Force
    }
  }

  Write-Host "cycle $($script:loop) done"
  $script:loop++
  if ($Loops -eq 0) {
    Start-Sleep -Seconds 20
  }
}
