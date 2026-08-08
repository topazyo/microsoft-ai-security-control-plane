#!/usr/bin/env pwsh
# .claude/hooks/instructions-loaded-log.ps1
#
# InstructionsLoaded hook — logs each time a CLAUDE.md or .claude/rules/*.md
# file is loaded into context (fires at session start and on lazy loads).
# Non-blocking; failures never abort the session.

param()
$ErrorActionPreference = 'Continue'

$stdin   = [System.Console]::In.ReadToEnd()
$payload = if ($stdin) { try { $stdin | ConvertFrom-Json } catch { $null } } else { $null }

$repoRoot  = (Resolve-Path (Join-Path $PSScriptRoot ".." "..")).Path
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$sid       = if ($payload -and $payload.session_id) { $payload.session_id } else { 'unknown' }

# session-logs/ is gitignored, keeping this transient log out of git
$logDir  = Join-Path $repoRoot ".claude" "session-logs"
$logPath = Join-Path $logDir "instructions-load.log"
try {
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $logPath -Value "[$timestamp] instructions loaded (session $sid)" -Encoding UTF8
} catch {
    [Console]::Error.WriteLine("[instructions-loaded-log] $_")
}

exit 0
