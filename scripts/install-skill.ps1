param(
  [string]$CodexHome = "",
  [string]$Destination = "",
  [string[]]$SkillsRoot = @(),
  [switch]$SkipScan,
  [switch]$SkipDeepIndex,
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
$summaryResult = $null
$deepResult = $null
$resolvedSkillsRoots = @($SkillsRoot | Where-Object { $_ })
if (-not $SkipScan) {
  $scanScript = Join-Path $Destination "scripts\scan-local-skills.ps1"
  if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "Installed scanner not found: $scanScript"
  }

  if ($SkillsRoot.Count -gt 0) {
    $scanResult = & $scanScript -SkillsRoot $SkillsRoot[0]
  }
  else {
    $scanResult = & $scanScript
  }

  $summaryScript = Join-Path $Destination "scripts\summarize-index.py"
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ((Test-Path -LiteralPath $summaryScript) -and $python) {
    $indexDir = $(if ($scanResult) { $scanResult.OutputDir } else { Join-Path $Destination ".skill-index" })
    try {
      $summaryResult = & $python.Source $summaryScript --index-dir $indexDir | Out-String | ConvertFrom-Json
    }
    catch {
      $summaryResult = [pscustomobject]@{
        summary_ran = $false
        summary_skipped_reason = $_.Exception.Message
      }
    }
  }
  if ((-not $SkipDeepIndex) -and $python) {
    $deepScript = Join-Path $Destination "scripts\deep-classify-skills.py"
    $indexDir = $(if ($scanResult) { $scanResult.OutputDir } else { Join-Path $Destination ".skill-index" })
    if ($resolvedSkillsRoots.Count -eq 0 -and $scanResult) {
      $resolvedSkillsRoots = @([string]$scanResult.SkillsRoot)
      $agentsSkills = Join-Path (Join-Path $HOME ".agents") "skills"
      if (Test-Path -LiteralPath $agentsSkills -PathType Container) {
        $resolvedSkillsRoots += $agentsSkills
      }
    }
    if ((Test-Path -LiteralPath $deepScript) -and $resolvedSkillsRoots.Count -gt 0) {
      $deepArgs = @($deepScript)
      foreach ($root in $resolvedSkillsRoots) { $deepArgs += @("--skills-root", $root) }
      $deepArgs += @("--index-dir", $indexDir)
      & $python.Source @deepArgs | Out-Null
      if ($LASTEXITCODE -eq 0) {
        $deepMetadataPath = Join-Path $indexDir "deep\metadata.json"
        $deepResult = [pscustomobject]@{
          deep_index_ran = $true
          deep_index = $deepMetadataPath
          metadata = $(if (Test-Path -LiteralPath $deepMetadataPath) { Get-Content -LiteralPath $deepMetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null })
        }
      }
      else {
        $deepResult = [pscustomobject]@{ deep_index_ran = $false; deep_index_skipped_reason = "Deep classifier exited with a non-zero status." }
      }
    }
  }
}

[pscustomobject]@{
  status = "installed"
  destination = (Resolve-Path -LiteralPath $Destination).Path
  scan_ran = (-not $SkipScan)
  summary_ran = $(if ($summaryResult) { $summaryResult.summary_ran } else { $false })
  summary = $summaryResult
  deep_index_ran = $(if ($deepResult) { $deepResult.deep_index_ran } else { $false })
  deep_index = $deepResult
  skills_root = $(if ($scanResult) { $scanResult.SkillsRoot } elseif ($SkillsRoot.Count -gt 0) { $SkillsRoot[0] } else { "" })
  skills_roots = @($resolvedSkillsRoots)
  index_dir = $(if ($scanResult) { $scanResult.OutputDir } else { Join-Path $Destination ".skill-index" })
} | ConvertTo-Json -Depth 6
