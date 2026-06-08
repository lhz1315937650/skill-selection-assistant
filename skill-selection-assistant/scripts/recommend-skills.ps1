param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [int]$Limit = 0,
  [int]$MaxRecommendations = 8,
  [int]$MinRecommendations = 1,
  [int]$ScoreWindow = 3,
  [int]$MinRelevanceScore = 3,
  [string]$IndexDir = "",
  [string]$SkillsRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$inferScript = Join-Path $PSScriptRoot "infer-route.ps1"
$selectScript = Join-Path $PSScriptRoot "select-route-candidates.ps1"
$scanScript = Join-Path $PSScriptRoot "scan-local-skills.ps1"

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
if (-not (Test-Path -LiteralPath $summaryPath)) {
  if (-not (Test-Path -LiteralPath $scanScript)) {
    throw "Route summary not found and scanner is missing: $summaryPath"
  }
  if ($SkillsRoot) {
    & $scanScript -SkillsRoot $SkillsRoot -OutputDir $IndexDir | Out-Null
  }
  else {
    & $scanScript -OutputDir $IndexDir | Out-Null
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
      query = $Query
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
  query = $Query
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
  next_step = "Recommend candidates according to the returned recommendation_policy. Keep explanations concise, then read only the chosen SKILL.md and optionally run record-selection-memory.ps1 to update local selection memory."
} | ConvertTo-Json -Depth 12
