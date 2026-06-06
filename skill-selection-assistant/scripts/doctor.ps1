param(
  [string]$SkillsRoot = "",
  [string]$IndexDir = "",
  [string]$Query = "build a frontend UI",
  [switch]$Fix
)

$ErrorActionPreference = "Stop"

function Resolve-SkillsRoot {
  param([string]$ExplicitRoot)

  if ($ExplicitRoot -and (Test-Path -LiteralPath $ExplicitRoot)) {
    return (Resolve-Path -LiteralPath $ExplicitRoot).Path
  }
  if ($env:CODEX_HOME) {
    $candidate = Join-Path $env:CODEX_HOME "skills"
    if (Test-Path -LiteralPath $candidate) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  $homeCandidate = Join-Path $HOME ".codex\skills"
  if (Test-Path -LiteralPath $homeCandidate) {
    return (Resolve-Path -LiteralPath $homeCandidate).Path
  }
  return ""
}

function Test-JsonFile {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return $false }
  try {
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
    return $true
  }
  catch {
    return $false
  }
}

$skillDir = Split-Path -Parent $PSScriptRoot
if (-not $IndexDir) {
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$scanScript = Join-Path $PSScriptRoot "scan-local-skills.ps1"
$recommendScript = Join-Path $PSScriptRoot "recommend-skills.ps1"
$memoryScript = Join-Path $PSScriptRoot "record-selection-memory.ps1"
$summaryScript = Join-Path $PSScriptRoot "summarize-index.py"
$rulesPath = Join-Path $skillDir "rules\categories.json"
$summaryPath = Join-Path $IndexDir "route-summary.json"
$memoryPath = Join-Path $IndexDir "selection-memory.md"
$classificationMapPath = Join-Path $IndexDir "DETAILED_CLASSIFICATION.md"
$skillsRootResolved = Resolve-SkillsRoot -ExplicitRoot $SkillsRoot

$checks = New-Object System.Collections.Generic.List[object]
$checks.Add([pscustomobject]@{ name = "skill_instance"; ok = (Test-Path -LiteralPath (Join-Path $skillDir "SKILL.md")); detail = $skillDir })
$checks.Add([pscustomobject]@{ name = "skills_root"; ok = (-not [string]::IsNullOrWhiteSpace($skillsRootResolved)); detail = $skillsRootResolved })
$checks.Add([pscustomobject]@{ name = "scanner"; ok = (Test-Path -LiteralPath $scanScript); detail = $scanScript })
$checks.Add([pscustomobject]@{ name = "recommender"; ok = (Test-Path -LiteralPath $recommendScript); detail = $recommendScript })
$checks.Add([pscustomobject]@{ name = "memory_recorder"; ok = (Test-Path -LiteralPath $memoryScript); detail = $memoryScript })
$checks.Add([pscustomobject]@{ name = "index_summarizer"; ok = (Test-Path -LiteralPath $summaryScript); detail = $summaryScript })
$checks.Add([pscustomobject]@{ name = "rules"; ok = (Test-JsonFile -Path $rulesPath); detail = $rulesPath })

$fixes = @()
if ((-not (Test-Path -LiteralPath $summaryPath)) -and $Fix) {
  if (-not $skillsRootResolved) {
    throw "Cannot run -Fix because no local Codex skills root was found. Pass -SkillsRoot explicitly."
  }
  & $scanScript -SkillsRoot $skillsRootResolved -OutputDir $IndexDir | Out-Null
  $fixes += "generated-index"
}

$summaryOk = Test-JsonFile -Path $summaryPath
$checks.Add([pscustomobject]@{ name = "route_summary"; ok = $summaryOk; detail = $summaryPath })
$checks.Add([pscustomobject]@{ name = "selection_memory"; ok = (Test-Path -LiteralPath $memoryPath); detail = $memoryPath })

if ($summaryOk -and (-not (Test-Path -LiteralPath $classificationMapPath)) -and $Fix -and (Test-Path -LiteralPath $summaryScript)) {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    & $python.Source $summaryScript --index-dir $IndexDir | Out-Null
    $fixes += "generated-classification-summary"
  }
}
$checks.Add([pscustomobject]@{ name = "classification_summary"; ok = (Test-Path -LiteralPath $classificationMapPath); detail = $classificationMapPath })

$shortlistCount = 0
$summary = $null
if ($summaryOk) {
  $summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $shortlistRoot = Join-Path $IndexDir "shortlists"
  if (Test-Path -LiteralPath $shortlistRoot) {
    $shortlistCount = @(Get-ChildItem -LiteralPath $shortlistRoot -Filter "*.json" -Recurse -ErrorAction SilentlyContinue).Count
  }
}
$checks.Add([pscustomobject]@{ name = "shortlists"; ok = ($shortlistCount -gt 0); detail = "$shortlistCount shortlist files" })

$recommendation = $null
if ($summaryOk -and (Test-Path -LiteralPath $recommendScript)) {
  try {
    $recommendation = (& $recommendScript -Query $Query -IndexDir $IndexDir -SkillsRoot $skillsRootResolved | Out-String | ConvertFrom-Json)
    $checks.Add([pscustomobject]@{ name = "sample_recommendation"; ok = ($recommendation.selection.returned -gt 0); detail = "$($recommendation.route.route_type)/$($recommendation.route.category)" })
  }
  catch {
    $checks.Add([pscustomobject]@{ name = "sample_recommendation"; ok = $false; detail = $_.Exception.Message })
  }
}

$ok = -not @($checks | Where-Object { -not $_.ok })

[pscustomobject]@{
  status = $(if ($ok) { "ok" } else { "needs-attention" })
  skill_instance_dir = $skillDir
  skills_root = $skillsRootResolved
  index_dir = $IndexDir
  fixes = $fixes
  checks = $checks
  summary = $(if ($summary) {
    [pscustomobject]@{
      raw_total = $summary.raw_total
      total = $summary.total
      full_routes_generated = $summary.full_routes_generated
      rules_schema_version = $summary.rules_schema_version
    }
  } else { $null })
  sample = $(if ($recommendation) {
    [pscustomobject]@{
      query = $Query
      route = $recommendation.route
      returned = $recommendation.selection.returned
      first_candidate = $(if ($recommendation.selection.returned -gt 0) { $recommendation.selection.candidates[0].name } else { "" })
    }
  } else { $null })
} | ConvertTo-Json -Depth 12
