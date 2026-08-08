#!/usr/bin/env pwsh
# .claude/hooks/postcompact-wrap-up.ps1
#
# PostCompact hook — fires after context compaction (manual or auto).
#   1. Logs the compaction event (gitignored session-logs/).
#   2. Emits a re-anchor reminder as additionalContext so the session
#      re-grounds after context was trimmed.
# Non-blocking; failures never abort the session.

param()
$ErrorActionPreference = 'Continue'

$stdin   = [System.Console]::In.ReadToEnd()
$payload = if ($stdin) { try { $stdin | ConvertFrom-Json } catch { $null } } else { $null }
$trigger = if ($payload -and $payload.trigger) { $payload.trigger } else { 'unknown' }

$repoRoot  = (Resolve-Path (Join-Path $PSScriptRoot ".." "..")).Path
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

$logDir  = Join-Path $repoRoot ".claude" "session-logs"
$logPath = Join-Path $logDir "compaction.log"
try {
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $logPath -Value "[$timestamp] post-compact ($trigger)" -Encoding UTF8
} catch {
    [Console]::Error.WriteLine("[postcompact-wrap-up] log: $_")
}

$reminder = "Context was just compacted ($trigger). Re-read the matrix's last-verified dates and CHANGELOG state before continuing status-verification work, and consider /wrap-up or /obsidian-save to persist tiered memory."
$out = @{
    continue           = $true
    hookSpecificOutput = @{ hookEventName = "PostCompact"; additionalContext = $reminder }
} | ConvertTo-Json -Compress -Depth 5
[Console]::Out.WriteLine($out)

exit 0
