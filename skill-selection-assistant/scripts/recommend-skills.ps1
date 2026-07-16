param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [int]$Limit = 0,
  [int]$MaxRecommendations = 8,
  [int]$MinRecommendations = 1,
  [int]$ScoreWindow = 3,
  [int]$MinRelevanceScore = 3,
  [string]$IndexDir = "",
  [string[]]$SkillsRoot = @(),
  [string]$Path = "",
  [switch]$Legacy,
  [switch]$Compat
)

$ErrorActionPreference = "Stop"
$PrimarySkillsRoot = $(if ($SkillsRoot.Count -gt 0) { [string]$SkillsRoot[0] } else { "" })

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$inferScript = Join-Path $PSScriptRoot "infer-route.ps1"
$selectScript = Join-Path $PSScriptRoot "select-route-candidates.ps1"
$scanScript = Join-Path $PSScriptRoot "scan-local-skills.ps1"
$deepBuildScript = Join-Path $PSScriptRoot "deep-classify-skills.py"
$deepRouteScript = Join-Path $PSScriptRoot "deep-route.py"

function Get-ResolvedPathOrEmpty {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path) -or (-not (Test-Path -LiteralPath $Path))) {
    return ""
  }
  return (Get-Item -LiteralPath $Path).FullName
}

function Test-LocalIndexStale {
  param(
    [string]$ManifestPath,
    [string]$ExplicitSkillsRoot,
    [string]$RouterSkillPath
  )

  if (-not (Test-Path -LiteralPath $ManifestPath)) {
    return $true
  }

  try {
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifestRoot = Get-ResolvedPathOrEmpty -Path ([string]$manifest.skills_root)
    $requestedRoot = Get-ResolvedPathOrEmpty -Path $ExplicitSkillsRoot
    if (-not $manifestRoot) { return $true }
    if ($ExplicitSkillsRoot -and ((-not $requestedRoot) -or ($requestedRoot -ne $manifestRoot))) {
      return $true
    }

    $selfSkillPath = Get-ResolvedPathOrEmpty -Path $RouterSkillPath
    $currentFiles = @(
      Get-ChildItem -LiteralPath $manifestRoot -Filter "SKILL.md" -Recurse -Force -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName } |
        Where-Object { (-not $selfSkillPath) -or ($_ -ne $selfSkillPath) } |
        Sort-Object -Unique
    )
    $manifestFiles = @($manifest.files)
    $indexedFiles = @($manifestFiles | ForEach-Object { [string]$_.skill_md } | Where-Object { $_ } | Sort-Object -Unique)
    if ($currentFiles.Count -ne $indexedFiles.Count) { return $true }
    if (@(Compare-Object -ReferenceObject $indexedFiles -DifferenceObject $currentFiles).Count -gt 0) { return $true }

    $manifestByPath = @{}
    foreach ($entry in $manifestFiles) {
      if ($entry.skill_md) { $manifestByPath[[string]$entry.skill_md] = $entry }
    }
    foreach ($filePath in $currentFiles) {
      if (-not $manifestByPath.ContainsKey($filePath)) { return $true }
      $file = Get-Item -LiteralPath $filePath
      $entry = $manifestByPath[$filePath]
      if (([int64]$entry.file_length -ne [int64]$file.Length) -or ([int64]$entry.last_write_ticks -ne [int64]$file.LastWriteTime.Ticks)) {
        return $true
      }
    }
    return $false
  }
  catch {
    return $true
  }
}

function Get-FirstRouteInfo {
  param([object]$Summary, [string]$RouteType, [string]$Category)

  $bucket = switch ($RouteType) {
    "primary_domain" { $Summary.primary_domain }
    "domain_detail" { $Summary.domain_detail }
    "specialty" { $Summary.specialty }
    "adaptive_leaf" { $Summary.adaptive_leaf }
    "task_type" { $Summary.task_type }
    default { @() }
  }

  return @($bucket | Where-Object { $_.name -eq $Category } | Select-Object -First 1)
}

function Get-FirstAvailableRoute {
  param([object]$Summary)

  foreach ($pair in @(
    @{ route_type = "primary_domain"; bucket = $Summary.primary_domain },
    @{ route_type = "domain_detail"; bucket = $Summary.domain_detail },
    @{ route_type = "specialty"; bucket = $Summary.specialty },
    @{ route_type = "adaptive_leaf"; bucket = $Summary.adaptive_leaf },
    @{ route_type = "task_type"; bucket = $Summary.task_type }
  )) {
    $item = @($pair.bucket | Sort-Object @{ Expression = "count"; Descending = $true }, name | Select-Object -First 1)
    if ($item.Count -gt 0) {
      return [pscustomobject]@{
        route_type = $pair.route_type
        category = $item[0].name
        route_count = $item[0].count
        shortlist_file = $item[0].shortlist_file
      }
    }
  }

  return $null
}

if (-not (Test-Path -LiteralPath $inferScript)) {
  throw "Missing infer-route.ps1 next to recommend-skills.ps1."
}
if (-not (Test-Path -LiteralPath $selectScript)) {
  throw "Missing select-route-candidates.ps1 next to recommend-skills.ps1."
}

$summaryPath = Join-Path $IndexDir "route-summary.json"
$manifestPath = Join-Path $IndexDir "manifest.json"
$routerSkillPath = Join-Path (Split-Path -Parent $PSScriptRoot) "SKILL.md"
$indexRefreshReason = ""
$needsScan = (-not (Test-Path -LiteralPath $summaryPath))
if ($needsScan) {
  $indexRefreshReason = "index_missing"
}
elseif (Test-LocalIndexStale -ManifestPath $manifestPath -ExplicitSkillsRoot $PrimarySkillsRoot -RouterSkillPath $routerSkillPath) {
  $needsScan = $true
  $indexRefreshReason = "local_skill_library_changed"
}

if ($needsScan) {
  if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "The local skill index is missing or stale and the scanner is unavailable: $scanScript"
  }
  if ($PrimarySkillsRoot) {
    & $scanScript -SkillsRoot $PrimarySkillsRoot -OutputDir $IndexDir | Out-Null
  }
  else {
    & $scanScript -OutputDir $IndexDir | Out-Null
  }
}

if (-not (Test-Path -LiteralPath $summaryPath)) {
  throw "Route summary was not generated: $summaryPath"
}

if (-not $Legacy) {
  $python = Get-Command python -ErrorAction SilentlyContinue
  $deepMetadataPath = Join-Path $IndexDir "deep\metadata.json"
  if ($python -and (Test-Path -LiteralPath $deepBuildScript) -and (Test-Path -LiteralPath $deepRouteScript)) {
    $manifestForDeep = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $deepRoots = $(if ($SkillsRoot.Count -gt 0) { @($SkillsRoot) } else { @([string]$manifestForDeep.skills_root) })
    $deepRootsChanged = $false
    if (Test-Path -LiteralPath $deepMetadataPath) {
      try {
        $existingDeepMetadata = Get-Content -LiteralPath $deepMetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $existingDeepRoots = @($existingDeepMetadata.skills_roots | ForEach-Object { [string]$_ } | Where-Object { $_ })
        if (($SkillsRoot.Count -eq 0) -and $existingDeepRoots.Count -gt 0) {
          $deepRoots = $existingDeepRoots
        }
        elseif ($SkillsRoot.Count -gt 0) {
          $requestedNormalized = @($deepRoots | ForEach-Object { (Get-Item -LiteralPath $_).FullName } | Sort-Object -Unique)
          $existingNormalized = @($existingDeepRoots | ForEach-Object { (Get-Item -LiteralPath $_).FullName } | Sort-Object -Unique)
          $deepRootsChanged = (@(Compare-Object -ReferenceObject $existingNormalized -DifferenceObject $requestedNormalized).Count -gt 0)
        }
      }
      catch {
        $deepRootsChanged = ($SkillsRoot.Count -gt 0)
      }
    }
    $deepBuildArgs = @($deepBuildScript)
    foreach ($root in $deepRoots) { $deepBuildArgs += @("--skills-root", $root) }
    $deepBuildArgs += @("--index-dir", $IndexDir)
    $shouldBuildDeep = $needsScan -or $deepRootsChanged -or (-not (Test-Path -LiteralPath $deepMetadataPath))
    if ($deepRootsChanged -and [string]::IsNullOrWhiteSpace($indexRefreshReason)) { $indexRefreshReason = "skills_roots_changed" }
    $deepWasRefreshed = $shouldBuildDeep
    if ($shouldBuildDeep) {
      & $python.Source @deepBuildArgs | Out-Null
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to build the per-user deep skill index."
      }
    }

    $deepArgs = @($deepRouteScript, "--query", $Query, "--index-dir", $IndexDir, "--limit", $(if ($Limit -gt 0) { $Limit } else { $MaxRecommendations }))
    if ($Path) { $deepArgs += @("--path", $Path) }
    $deepResult = (& $python.Source @deepArgs | Out-String | ConvertFrom-Json)
    if ($deepResult.mode -eq "index_stale") {
      & $python.Source @deepBuildArgs | Out-Null
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to refresh the stale per-user deep skill index."
      }
      $deepWasRefreshed = $true
      $deepResult = (& $python.Source @deepArgs | Out-String | ConvertFrom-Json)
    }
    $deepEnvelope = [ordered]@{
      schema_version = "3.0.0"
      query = $Query
      engine = "deep_hospital"
      mode = $deepResult.mode
      index = [pscustomobject]@{
        refreshed = ($deepWasRefreshed -or (-not [string]::IsNullOrWhiteSpace($indexRefreshReason)))
        refresh_reason = $indexRefreshReason
        skills_root = $manifestForDeep.skills_root
        skills_roots = @($deepRoots)
        scope = "installing-user-local-skills-exhaustive"
      }
      route = $deepResult.current
      branches = @($deepResult.branches)
      candidates = @($deepResult.candidates)
      next_step = $(switch ($deepResult.mode) {
        "choose_category" { "Present only the returned branches, ask the user to choose one, then call recommend-skills.ps1 again with its exact -Path." }
        "choose_skill" { "Present the compact candidates and ask which skill to activate. Read only the chosen SKILL.md." }
        "no_skills_installed" { "No local skills are installed yet. Offer to answer directly, install a skill, or create a new skill." }
        default { [string]$deepResult.instruction }
      })
    }
    if ($Compat) { $deepEnvelope.deep_route = $deepResult }
    [pscustomobject]$deepEnvelope | ConvertTo-Json -Depth 14
    exit 0
  }
}

$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$route = (& $inferScript -Query $Query -IndexDir $IndexDir | Out-String | ConvertFrom-Json)
$fallbackReason = ""
if (-not $route.available) {
  $originalRoute = [pscustomobject]@{
    route_type = $route.route_type
    category = $route.category
    task_hint = $route.task_hint
  }

  $fallback = $null
  if (($route.PSObject.Properties.Name -contains "domain_detail") -and $route.domain_detail) {
    $detailRouteInfo = Get-FirstRouteInfo -Summary $summary -RouteType "domain_detail" -Category $route.domain_detail
    if ($detailRouteInfo.Count -gt 0) {
      $fallback = [pscustomobject]@{
        route_type = "domain_detail"
        category = $route.domain_detail
        route_count = $detailRouteInfo[0].count
        shortlist_file = $detailRouteInfo[0].shortlist_file
      }
    }
  }

  if (-not $fallback -and $route.task_hint) {
    $taskRouteInfo = Get-FirstRouteInfo -Summary $summary -RouteType "task_type" -Category $route.task_hint
    if ($taskRouteInfo.Count -gt 0) {
      $fallback = [pscustomobject]@{
        route_type = "task_type"
        category = $route.task_hint
        route_count = $taskRouteInfo[0].count
        shortlist_file = $taskRouteInfo[0].shortlist_file
      }
    }
  }

  if (-not $fallback -and $route.primary_domain) {
    $primaryRouteInfo = Get-FirstRouteInfo -Summary $summary -RouteType "primary_domain" -Category $route.primary_domain
    if ($primaryRouteInfo.Count -gt 0) {
      $fallback = [pscustomobject]@{
        route_type = "primary_domain"
        category = $route.primary_domain
        route_count = $primaryRouteInfo[0].count
        shortlist_file = $primaryRouteInfo[0].shortlist_file
      }
    }
  }

  if (-not $fallback) {
    $fallback = Get-FirstAvailableRoute -Summary $summary
  }

  if (-not $fallback) {
    [pscustomobject]@{
      schema_version = "3.0.0"
      query = $Query
      engine = "legacy_shortlist"
      mode = "choose_skill"
      index = [pscustomobject]@{
        refreshed = (-not [string]::IsNullOrWhiteSpace($indexRefreshReason))
        refresh_reason = $indexRefreshReason
        skills_root = $summary.skills_root
        skills_roots = @($summary.skills_root)
        scope = $summary.index_scope
      }
      route = $originalRoute
      selection = [pscustomobject]@{
        source_file = ""
        source_count = 0
        merged_variants = $true
        returned = 0
        recommendation_policy = [pscustomobject]@{
          mode = "no_available_route"
          explicit_limit = $(if ($Limit -gt 0) { $Limit } else { $null })
          min_recommendations = $MinRecommendations
          max_recommendations = $MaxRecommendations
          score_window = $ScoreWindow
          min_relevance_score = $MinRelevanceScore
          score_threshold = $null
        }
        candidates = @()
      }
      fallback = [pscustomobject]@{
        used = $false
        reason = "No route files are available. Re-run scan-local-skills.ps1 and confirm the skills root contains installed skills."
      }
      branches = @()
      candidates = @()
      next_step = "Tell the user no local skill match is available yet, then offer to answer directly or install/create a relevant skill."
    } | ConvertTo-Json -Depth 12
    exit 0
  }

  $fallbackReason = "Inferred route '$($route.route_type)/$($route.category)' was unavailable in this local skills root; fell back to '$($fallback.route_type)/$($fallback.category)'."
  $route.route_type = $fallback.route_type
  $route.category = $fallback.category
  $route.route_count = $fallback.route_count
  $route.shortlist_file = $fallback.shortlist_file
}

if (($route.route_type -eq "specialty") -and $route.task_hint) {
  $leafCategory = "specialty=$($route.category)|task=$($route.task_hint)"
  $leafRouteInfo = Get-FirstRouteInfo -Summary $summary -RouteType "adaptive_leaf" -Category $leafCategory
  if (($leafRouteInfo.Count -gt 0) -and (([int]$route.route_count -le 0) -or ([int]$leafRouteInfo[0].count -lt [int]$route.route_count))) {
    $route.route_type = "adaptive_leaf"
    $route.category = $leafCategory
    $route.route_count = $leafRouteInfo[0].count
    $route.shortlist_file = $leafRouteInfo[0].shortlist_file
  }
}

if ($Limit -gt 0) {
  $selection = (& $selectScript -Query $Query -RouteType $route.route_type -Category $route.category -Limit $Limit -IndexDir $IndexDir -MaxRecommendations $MaxRecommendations -MinRecommendations $MinRecommendations -ScoreWindow $ScoreWindow -MinRelevanceScore $MinRelevanceScore | Out-String | ConvertFrom-Json)
}
else {
  $selection = (& $selectScript -Query $Query -RouteType $route.route_type -Category $route.category -IndexDir $IndexDir -MaxRecommendations $MaxRecommendations -MinRecommendations $MinRecommendations -ScoreWindow $ScoreWindow -MinRelevanceScore $MinRelevanceScore | Out-String | ConvertFrom-Json)
}

[pscustomobject]@{
  schema_version = "3.0.0"
  query = $Query
  engine = "legacy_shortlist"
  mode = "choose_skill"
  index = [pscustomobject]@{
    refreshed = (-not [string]::IsNullOrWhiteSpace($indexRefreshReason))
    refresh_reason = $indexRefreshReason
    skills_root = $summary.skills_root
    skills_roots = @($summary.skills_root)
    scope = $summary.index_scope
  }
  route = [pscustomobject]@{
    route_type = $route.route_type
    category = $route.category
    primary_domain = $route.primary_domain
    domain_detail = $(if ($route.PSObject.Properties.Name -contains "domain_detail") { $route.domain_detail } else { "" })
    confidence = $route.confidence
    route_count = $route.route_count
    shortlist_file = $route.shortlist_file
    task_hint = $route.task_hint
  }
  selection = [pscustomobject]@{
    source_file = $selection.source_file
    source_count = $selection.source_count
    merged_variants = $selection.merged_variants
    returned = $selection.returned
    recommendation_policy = $selection.recommendation_policy
    candidates = $selection.candidates
  }
  fallback = [pscustomobject]@{
    used = (-not [string]::IsNullOrWhiteSpace($fallbackReason))
    reason = $fallbackReason
  }
  branches = @()
  candidates = @($selection.candidates)
  next_step = "Recommend candidates according to the returned recommendation_policy. Keep explanations concise, then read only the chosen SKILL.md and optionally run record-selection-memory.ps1 to update local selection memory."
} | ConvertTo-Json -Depth 12
