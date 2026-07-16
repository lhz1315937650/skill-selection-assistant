param(
  [string]$CodexHome = "",
  [string]$Destination = "",
  [string[]]$SkillsRoot = @(),
  [switch]$SkipScan,
  [switch]$SkipDeepIndex,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ManagedItems = @("SKILL.md", "VERSION", "agents", "references", "rules", "schemas", "scripts")

function Resolve-CodexHome {
  param([string]$ExplicitHome)
  if ($ExplicitHome) { return [IO.Path]::GetFullPath($ExplicitHome) }
  if ($env:CODEX_HOME) { return [IO.Path]::GetFullPath($env:CODEX_HOME) }
  return [IO.Path]::GetFullPath((Join-Path $HOME ".codex"))
}

function Install-ManagedFiles {
  param([string]$Source, [string]$Target)

  $targetParent = Split-Path -Parent $Target
  New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
  $createdTarget = -not (Test-Path -LiteralPath $Target)
  New-Item -ItemType Directory -Force -Path $Target | Out-Null
  $transaction = Join-Path $targetParent (".skill-selection-install-" + [guid]::NewGuid().ToString("N"))
  $stagedRoot = Join-Path $transaction "staged"
  $backupRoot = Join-Path $transaction "backup"
  New-Item -ItemType Directory -Force -Path $stagedRoot, $backupRoot | Out-Null
  $replaced = New-Object System.Collections.Generic.List[object]

  try {
    foreach ($item in $ManagedItems) {
      $src = Join-Path $Source $item
      if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $stagedRoot $item) -Recurse -Force
      }
    }
    Get-ChildItem -LiteralPath $stagedRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -eq "__pycache__" } |
      Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stagedRoot -File -Recurse -Force -Filter "*.pyc" -ErrorAction SilentlyContinue |
      Remove-Item -Force

    foreach ($item in $ManagedItems) {
      $targetItem = Join-Path $Target $item
      $stagedItem = Join-Path $stagedRoot $item
      $backupItem = Join-Path $backupRoot $item
      $hadExisting = Test-Path -LiteralPath $targetItem
      if ($hadExisting) {
        Move-Item -LiteralPath $targetItem -Destination $backupItem
      }
      $replaced.Add([pscustomobject]@{ target = $targetItem; backup = $backupItem; had_existing = $hadExisting })
      if (Test-Path -LiteralPath $stagedItem) {
        Move-Item -LiteralPath $stagedItem -Destination $targetItem
      }
    }
  }
  catch {
    for ($i = $replaced.Count - 1; $i -ge 0; $i--) {
      $state = $replaced[$i]
      if (Test-Path -LiteralPath $state.target) {
        Remove-Item -LiteralPath $state.target -Recurse -Force
      }
      if ($state.had_existing -and (Test-Path -LiteralPath $state.backup)) {
        Move-Item -LiteralPath $state.backup -Destination $state.target
      }
    }
    if ($createdTarget -and (Test-Path -LiteralPath $Target)) {
      $remaining = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue)
      if ($remaining.Count -eq 0) {
        Remove-Item -LiteralPath $Target -Force
      }
    }
    throw
  }
  finally {
    if (Test-Path -LiteralPath $transaction) {
      Remove-Item -LiteralPath $transaction -Recurse -Force
    }
  }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$skillSource = Join-Path $repoRoot "skill-selection-assistant"
if (-not (Test-Path -LiteralPath (Join-Path $skillSource "SKILL.md"))) {
  throw "Cannot find skill source folder: $skillSource"
}

$codexHomeResolved = Resolve-CodexHome -ExplicitHome $CodexHome
if (-not $Destination) {
  $Destination = Join-Path (Join-Path $codexHomeResolved "skills") "skill-selection-assistant"
}
$Destination = [IO.Path]::GetFullPath($Destination)
$destinationParent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null

if ((Test-Path -LiteralPath $Destination) -and (-not $Force)) {
  throw "Destination already exists: $Destination. Re-run with -Force to update the installed router skill while preserving local runtime artifacts."
}

$resolvedSkillsRoots = New-Object System.Collections.Generic.List[string]
if ($SkillsRoot.Count -gt 0) {
  foreach ($root in $SkillsRoot) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
      throw "Skills root does not exist: $root"
    }
    $resolvedSkillsRoots.Add((Resolve-Path -LiteralPath $root).Path)
  }
}
else {
  $primaryRoot = Join-Path $codexHomeResolved "skills"
  New-Item -ItemType Directory -Force -Path $primaryRoot | Out-Null
  $resolvedSkillsRoots.Add((Resolve-Path -LiteralPath $primaryRoot).Path)
  $defaultCodexHome = [IO.Path]::GetFullPath((Join-Path $HOME ".codex"))
  $agentsSkills = Join-Path (Join-Path $HOME ".agents") "skills"
  if ((-not $CodexHome) -and ($codexHomeResolved -eq $defaultCodexHome) -and (Test-Path -LiteralPath $agentsSkills -PathType Container)) {
    $resolvedSkillsRoots.Add((Resolve-Path -LiteralPath $agentsSkills).Path)
  }
}

Install-ManagedFiles -Source $skillSource -Target $Destination

$scanResult = $null
$summaryResult = $null
$deepResult = $null
if (-not $SkipScan) {
  $scanScript = Join-Path $Destination "scripts\scan-local-skills.ps1"
  if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "Installed scanner not found: $scanScript"
  }
  $scanResult = & $scanScript -SkillsRoot $resolvedSkillsRoots[0]

  $summaryScript = Join-Path $Destination "scripts\summarize-index.py"
  $python = Get-Command python -ErrorAction SilentlyContinue
  $indexDir = $scanResult.OutputDir
  if ((Test-Path -LiteralPath $summaryScript) -and $python) {
    try {
      $summaryResult = & $python.Source $summaryScript --index-dir $indexDir | Out-String | ConvertFrom-Json
    }
    catch {
      $summaryResult = [pscustomobject]@{ summary_ran = $false; summary_skipped_reason = $_.Exception.Message }
    }
  }
  if ((-not $SkipDeepIndex) -and $python) {
    $deepScript = Join-Path $Destination "scripts\deep-classify-skills.py"
    if (Test-Path -LiteralPath $deepScript) {
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
  version = $(if (Test-Path -LiteralPath (Join-Path $Destination "VERSION")) { (Get-Content -LiteralPath (Join-Path $Destination "VERSION") -Raw -Encoding UTF8).Trim() } else { "development" })
  destination = (Resolve-Path -LiteralPath $Destination).Path
  scan_ran = [bool]$scanResult
  summary_ran = $(if ($summaryResult) { [bool]$summaryResult.summary_ran } else { $false })
  summary = $summaryResult
  deep_index_ran = $(if ($deepResult) { [bool]$deepResult.deep_index_ran } else { $false })
  deep_index = $deepResult
  skills_root = $resolvedSkillsRoots[0]
  skills_roots = @($resolvedSkillsRoots)
  index_dir = $(if ($scanResult) { $scanResult.OutputDir } else { Join-Path $Destination ".skill-index" })
} | ConvertTo-Json -Depth 8
