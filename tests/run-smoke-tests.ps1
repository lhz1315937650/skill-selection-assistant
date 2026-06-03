param(
  [switch]$KeepOutput
)

$ErrorActionPreference = "Stop"

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) {
    throw "ASSERTION FAILED: $Message"
  }
}

function Read-Json {
  param([string]$Path)
  return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$skillRoot = Join-Path $repoRoot "tests\fixtures\skills"
$scanScript = Join-Path $repoRoot "skill-selection-assistant\scripts\scan-local-skills.ps1"
$inferScript = Join-Path $repoRoot "skill-selection-assistant\scripts\infer-route.ps1"
$recommendScript = Join-Path $repoRoot "skill-selection-assistant\scripts\recommend-skills.ps1"
$outputRoot = Join-Path $env:TEMP ("skill-selection-smoke-" + [guid]::NewGuid().ToString("N"))
$indexDir = Join-Path $outputRoot ".skill-index"

try {
  New-Item -ItemType Directory -Force -Path $indexDir | Out-Null

  & $scanScript -SkillsRoot $skillRoot -OutputDir $indexDir | Out-Null

  $indexPath = Join-Path $indexDir "skills-index.json"
  $summaryPath = Join-Path $indexDir "route-summary.json"
  $manifestPath = Join-Path $indexDir "manifest.json"
  $parseCachePath = Join-Path $indexDir "parsed-skills-cache.json"
  Assert-True (Test-Path -LiteralPath $indexPath) "skills-index.json should be generated"
  Assert-True (Test-Path -LiteralPath $summaryPath) "route-summary.json should be generated"
  Assert-True (Test-Path -LiteralPath $manifestPath) "manifest.json should be generated"
  Assert-True (Test-Path -LiteralPath $parseCachePath) "parsed-skills-cache.json should be generated"

  $index = Read-Json -Path $indexPath
  $manifest = Read-Json -Path $manifestPath
  Assert-True ([int]$index.raw_total -eq 7) "raw_total should be 7"
  Assert-True ([int]$index.total -eq 6) "total should preserve same-name variants and merge exact duplicates"
  Assert-True ([int]$index.duplicates_removed -eq 1) "duplicates_removed should be 1"
  Assert-True ($manifest.cache_file -eq "parsed-skills-cache.json") "manifest should point to parse cache"
  Assert-True ($null -eq $manifest.files[0].item) "manifest should not embed full parsed skill items"

  $duplicateVariants = @($index.skills | Where-Object { $_.canonical_name -eq "duplicate-tool" })
  Assert-True ($duplicateVariants.Count -eq 2) "duplicate-tool should have two content variants"
  Assert-True ((@($duplicateVariants | Where-Object { $_.dedupe_status -eq "variant" }).Count) -eq 2) "duplicate-tool variants should be marked variant"

  $frontendShortlist = Join-Path $indexDir "shortlists\domain-detail\frontend-web.json"
  $frontendRoute = Join-Path $indexDir "routes\domain-detail\frontend-web.json"
  Assert-True (Test-Path -LiteralPath $frontendShortlist) "frontend-web shortlist should exist"
  Assert-True (Test-Path -LiteralPath $frontendRoute) "frontend-web full route should exist"

  $staleFile = Join-Path $indexDir "routes\domain-detail\stale-route.json"
  Set-Content -LiteralPath $staleFile -Value "{}" -Encoding UTF8
  Assert-True (Test-Path -LiteralPath $staleFile) "stale route fixture should exist before rescan"
  & $scanScript -SkillsRoot $skillRoot -OutputDir $indexDir | Out-Null
  Assert-True (-not (Test-Path -LiteralPath $staleFile)) "stale route file should be removed by rescan"

  $frontendRouteInference = (& $inferScript -Query "build a beautiful frontend UI" -IndexDir $indexDir | Out-String | ConvertFrom-Json)
  Assert-True ($frontendRouteInference.category -eq "frontend-web") "frontend query should infer frontend-web"
  Assert-True ($frontendRouteInference.shortlist_file -eq "shortlists/domain-detail/frontend-web.json") "frontend inference should expose shortlist file"

  $researchRouteInference = (& $inferScript -Query "analyze this academic paper and extract citations" -IndexDir $indexDir | Out-String | ConvertFrom-Json)
  Assert-True ($researchRouteInference.category -eq "academic-research") "academic query should infer academic-research"

  $recommendation = (& $recommendScript -Query "build a beautiful frontend UI" -Limit 3 -IndexDir $indexDir | Out-String | ConvertFrom-Json)
  Assert-True ($recommendation.route.category -eq "frontend-web") "recommendation should use frontend-web route"
  Assert-True ($recommendation.selection.source_file -like "*shortlists*") "recommendation should read from shortlist"
  Assert-True ([int]$recommendation.selection.returned -gt 0) "recommendation should return candidates"
  Assert-True ($recommendation.selection.candidates[0].name -eq "frontend-design") "frontend-design should be first for frontend UI query"
  Assert-True ($recommendation.selection.merged_variants -eq $true) "recommendation should merge same-name variants by default"

  [pscustomobject]@{
    Status = "passed"
    OutputDir = $indexDir
    RawTotal = $index.raw_total
    Total = $index.total
    DuplicatesRemoved = $index.duplicates_removed
    ManifestCacheFile = $manifest.cache_file
    FrontendCategory = $frontendRouteInference.category
    FirstRecommendation = $recommendation.selection.candidates[0].name
  } | ConvertTo-Json -Depth 4
}
finally {
  if ((-not $KeepOutput) -and (Test-Path -LiteralPath $outputRoot)) {
    Remove-Item -LiteralPath $outputRoot -Recurse -Force
  }
}
