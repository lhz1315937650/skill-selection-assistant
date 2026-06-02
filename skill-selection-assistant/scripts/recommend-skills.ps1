param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [int]$Limit = 3,
  [string]$IndexDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$inferScript = Join-Path $PSScriptRoot "infer-route.ps1"
$selectScript = Join-Path $PSScriptRoot "select-route-candidates.ps1"

if (-not (Test-Path -LiteralPath $inferScript)) {
  throw "Missing infer-route.ps1 next to recommend-skills.ps1."
}
if (-not (Test-Path -LiteralPath $selectScript)) {
  throw "Missing select-route-candidates.ps1 next to recommend-skills.ps1."
}

$route = (& $inferScript -Query $Query -IndexDir $IndexDir | Out-String | ConvertFrom-Json)
if (-not $route.available) {
  throw "No available route for category '$($route.category)'. Re-run scan-local-skills.ps1 or inspect route-summary.md."
}

$selection = (& $selectScript -Query $Query -RouteType $route.route_type -Category $route.category -Limit $Limit -IndexDir $IndexDir | Out-String | ConvertFrom-Json)

[pscustomobject]@{
  query = $Query
  route = [pscustomobject]@{
    route_type = $route.route_type
    category = $route.category
    primary_domain = $route.primary_domain
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
    candidates = $selection.candidates
  }
  next_step = "Recommend the best 1-3 candidates in the user's language, then read the chosen candidate SKILL.md only after the user chooses."
} | ConvertTo-Json -Depth 12
