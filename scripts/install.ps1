# clipsdaily copy-installer (Windows, PowerShell).
#
# Copies the clipsdaily skill + slash commands into your agent harness.
# This is the copy-install path (like BugHunter's scripts/install.ps1).
# The recommended install is the Claude Code plugin instead:
#
#   /plugin marketplace add abelprasad/clipsdaily
#   /plugin install clipsdaily@abelprasad
#
# Usage (run from the repo root):
#   .\scripts\install.ps1        # Claude Code only
#   .\scripts\install.ps1 -All   # Claude Code + every other detected harness
#
# -All copies the SKILL (not the commands) to each detected harness:
#   Claude Code    $env:USERPROFILE\.claude\skills
#   OpenCode/Codex $env:USERPROFILE\.agents\skills
#   Hermes         $env:USERPROFILE\.hermes\skills
#   Gemini         $env:USERPROFILE\.gemini\config\skills
# A harness counts as detected when its binary is on PATH or its home
# directory already exists. Slash commands stay Claude-Code-only by
# design — other harnesses don't share the command format.
#
# Idempotent: re-running it replaces the installed copy.
param(
    [switch]$All
)

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Install-Skill {
    param([string]$SkillsRoot)
    New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
    $Dest = Join-Path $SkillsRoot "clipsdaily"
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    Copy-Item -Recurse (Join-Path $RepoDir "skills\clipsdaily") $Dest
    Write-Host "  skill -> $Dest"
}

function Test-Harness {
    param([string]$Binary, [string]$HomeDir)
    if (Get-Command $Binary -ErrorAction SilentlyContinue) { return $true }
    if (Test-Path $HomeDir) { return $true }
    return $false
}

Write-Host "== clipsdaily copy-install (Claude Code) =="
Install-Skill (Join-Path $env:USERPROFILE ".claude\skills")

$CommandsDest = Join-Path $env:USERPROFILE ".claude\commands\clipsdaily"
if (Test-Path $CommandsDest) { Remove-Item -Recurse -Force $CommandsDest }
New-Item -ItemType Directory -Force -Path $CommandsDest | Out-Null
Copy-Item -Recurse (Join-Path $RepoDir "plugins\clipsdaily\commands\*") $CommandsDest
Write-Host "  commands -> $CommandsDest"

if ($All) {
    Write-Host "== -All: detected harnesses =="
    if (Test-Harness "opencode" (Join-Path $env:USERPROFILE ".agents")) -or (Test-Harness "codex" (Join-Path $env:USERPROFILE ".agents")) {
        Install-Skill (Join-Path $env:USERPROFILE ".agents\skills")
    } else {
        Write-Host "  OpenCode/Codex: not detected, skipped"
    }
    if (Test-Harness "hermes" (Join-Path $env:USERPROFILE ".hermes")) {
        Install-Skill (Join-Path $env:USERPROFILE ".hermes\skills")
    } else {
        Write-Host "  Hermes: not detected, skipped"
    }
    if (Test-Harness "gemini" (Join-Path $env:USERPROFILE ".gemini")) {
        Install-Skill (Join-Path $env:USERPROFILE ".gemini\config\skills")
    } else {
        Write-Host "  Gemini: not detected, skipped"
    }
}

Write-Host "Done. Restart Claude Code (or your harness) to pick up the skill."
Write-Host "Slash commands: /clipsdaily:run /clipsdaily:post /clipsdaily:queue"
Write-Host "  /clipsdaily:campaign /clipsdaily:submit /clipsdaily:earnings /clipsdaily:status"
