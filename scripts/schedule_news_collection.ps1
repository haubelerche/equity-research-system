<#
.SYNOPSIS
    Register (or remove) a Windows Task Scheduler job that runs the ticker-news
    collector on a recurring schedule - the lightweight replacement for the
    Airflow `collect_ticker_news` DAG (the astro/ deploy kit was removed).

.DESCRIPTION
    The job runs `python scripts/collect_ticker_news.py` from the repo root.
    The collector is idempotent (already-extracted articles are skipped), loads
    DATABASE_URL / OPENAI_API_KEY from the repo `.env` itself, and one ticker
    failing never aborts the batch - so a frequent schedule is safe and cheap.

    Default schedule mirrors the old DAG: every 3 hours, Mon-Fri (VN trading days).

.PARAMETER PythonExe
    Python executable to use. Defaults to whatever `python` resolves to on PATH
    (use the project's conda/venv interpreter for the right dependencies).

.PARAMETER IntervalHours
    Hours between runs (default 3).

.PARAMETER Tickers
    Optional explicit ticker list (e.g. "DHG","TRA"). Omit to use the MVP set
    baked into collect_ticker_news.py.

.PARAMETER TaskName
    Scheduled-task name (default "MAER-CollectTickerNews").

.PARAMETER Unregister
    Remove the scheduled task instead of creating it.

.EXAMPLE
    pwsh scripts/schedule_news_collection.ps1
    pwsh scripts/schedule_news_collection.ps1 -Tickers DHG,TRA -IntervalHours 4
    pwsh scripts/schedule_news_collection.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [string]   $PythonExe,
    [int]      $IntervalHours = 3,
    [string[]] $Tickers,
    [string]   $TaskName = "MAER-CollectTickerNews",
    [switch]   $Unregister
)

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's folder.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "No scheduled task named '$TaskName' - nothing to remove."
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

if (-not $PythonExe) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        throw "Could not resolve 'python' on PATH. Pass -PythonExe with the project interpreter."
    }
    $PythonExe = $cmd.Source
}

# Build the collector argument string.
$scriptPath = Join-Path $RepoRoot "scripts\collect_ticker_news.py"
$argList = @("`"$scriptPath`"")
if ($Tickers -and $Tickers.Count -gt 0) {
    $argList += "--tickers"
    $argList += $Tickers
}
$arguments = $argList -join " "

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $RepoRoot

# Every $IntervalHours, repeating across a 1-day window, only on weekdays (Mon-Fri).
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At (Get-Date).Date.AddHours(8)   # first run 08:00, then repeats
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(8) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 1)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Collect ticker-scoped CafeF/VietStock news (idempotent). Replaces the Airflow collect_ticker_news DAG." `
    -Force | Out-Null

Write-Host "Registered '$TaskName':"
Write-Host "  exec     : $PythonExe $arguments"
Write-Host "  workdir  : $RepoRoot"
Write-Host "  schedule : every $IntervalHours h, Mon-Fri"
Write-Host "Run now to verify:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove later:       pwsh scripts/schedule_news_collection.ps1 -Unregister"
