param(
  [string]$CodexHome = "",
  [string]$Destination = "",
  [string]$SkillsRoot = "",
  [switch]$SkipScan,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-CodexHome {
  param([string]$ExplicitHome)

  if ($ExplicitHome) {
    return $ExplicitHome
  }
  if ($env:CODEX_HOME) {
    return $env:CODEX_HOME
  }
  return (Join-Path $HOME ".codex")
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$skillSource = Join-Path $repoRoot "skill-selection-assistant"
if (-not (Test-Path -LiteralPath (Join-Path $skillSource "SKILL.md"))) {
  throw "Cannot find skill source folder: $skillSource"
}

if (-not $Destination) {
  $codexHomeResolved = Resolve-CodexHome -ExplicitHome $CodexHome
  $Destination = Join-Path (Join-Path $codexHomeResolved "skills") "skill-selection-assistant"
}

$destinationParent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null

if ((Test-Path -LiteralPath $Destination) -and (-not $Force)) {
  throw "Destination already exists: $Destination. Re-run with -Force to update the installed router skill while preserving local runtime artifacts."
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
foreach ($item in @("SKILL.md", "agents", "rules", "scripts")) {
  $src = Join-Path $skillSource $item
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination $Destination -Recurse -Force
  }
}

$scanResult = $null
if (-not $SkipScan) {
  $scanScript = Join-Path $Destination "scripts\scan-local-skills.ps1"
  if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "Installed scanner not found: $scanScript"
  }

  if ($SkillsRoot) {
    $scanResult = & $scanScript -SkillsRoot $SkillsRoot
  }
  else {
    $scanResult = & $scanScript
  }
}

[pscustomobject]@{
  status = "installed"
  destination = (Resolve-Path -LiteralPath $Destination).Path
  scan_ran = (-not $SkipScan)
  skills_root = $(if ($scanResult) { $scanResult.SkillsRoot } else { $SkillsRoot })
  index_dir = $(if ($scanResult) { $scanResult.OutputDir } else { Join-Path $Destination ".skill-index" })
} | ConvertTo-Json -Depth 6
