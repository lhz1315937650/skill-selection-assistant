param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [ValidateSet("primary_domain", "domain_detail", "task_type")]
  [string]$RouteType = "domain_detail",

  [Parameter(Mandatory = $true)]
  [string]$Category,

  [int]$Limit = 12,
  [string]$IndexDir = ""
)

$ErrorActionPreference = "Stop"

function Get-SafeFileName {
  param([string]$Name)
  $safe = (($Name -replace "[^a-zA-Z0-9._-]", "-").Trim("-").ToLowerInvariant())
  if ([string]::IsNullOrWhiteSpace($safe)) { return "unknown" }
  return $safe
}

function Get-TokenList {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) { return @() }
  return @(
    [regex]::Matches($Text.ToLowerInvariant(), "[\p{L}\p{N}_]{2,}") |
      ForEach-Object { $_.Value } |
      Sort-Object -Unique
  )
}

function Get-OriginBoost {
  param([string]$Origin)
  switch ($Origin) {
    "user-local" { return 8 }
    "official-system" { return 6 }
    "installed-topic" { return 5 }
    "linked-external" { return 2 }
    default { return 0 }
  }
}

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$routeFolder = switch ($RouteType) {
  "primary_domain" { "primary-domain" }
  "domain_detail" { "domain-detail" }
  "task_type" { "task-type" }
}

$routePath = Join-Path (Join-Path (Join-Path $IndexDir "routes") $routeFolder) ((Get-SafeFileName -Name $Category) + ".json")
if (-not (Test-Path -LiteralPath $routePath)) {
  throw "Route file not found: $routePath. Re-run scan-local-skills.ps1 or choose a category from route-summary.md."
}

$route = Get-Content -LiteralPath $routePath -Raw -Encoding UTF8 | ConvertFrom-Json
$tokens = Get-TokenList -Text ($Query + " " + $Category)
$categoryTokens = Get-TokenList -Text $Category

$scored = foreach ($candidate in @($route.candidates)) {
  $haystack = @(
    $candidate.name,
    $candidate.short_description,
    (@($candidate.domain_detail) -join " "),
    (@($candidate.task_type) -join " "),
    (@($candidate.output_type) -join " "),
    $candidate.relative_path
  ) -join " "
  $haystack = $haystack.ToLowerInvariant()

  $score = Get-OriginBoost -Origin $candidate.origin
  foreach ($token in $tokens) {
    if ($candidate.name.ToLowerInvariant() -eq $token) { $score += 30 }
    elseif ($candidate.name.ToLowerInvariant().Contains($token)) { $score += 12 }
    elseif ($haystack.Contains($token)) { $score += 4 }
  }

  foreach ($token in $categoryTokens) {
    if ($candidate.name.ToLowerInvariant().Contains($token)) { $score += 18 }
    elseif ($haystack.Contains($token)) { $score += 5 }
  }

  if (@($candidate.domain_detail) -contains $Category) { $score += 8 }
  if ($candidate.primary_domain -eq $Category) { $score += 8 }
  if (@($candidate.task_type) -contains $Category) { $score += 5 }
  if ([int]$candidate.duplicate_count -gt 1) { $score += [Math]::Min([int]$candidate.duplicate_count, 6) }

  [pscustomobject]@{
    score = $score
    name = $candidate.name
    reason_hint = $candidate.short_description
    primary_domain = $candidate.primary_domain
    domain_detail = $candidate.domain_detail
    task_type = $candidate.task_type
    setup_level = $candidate.setup_level
    origin = $candidate.origin
    duplicate_count = $candidate.duplicate_count
    relative_path = $candidate.relative_path
    skill_md = $candidate.skill_md
  }
}

$top = @($scored | Sort-Object @{ Expression = "score"; Descending = $true }, name | Select-Object -First $Limit)

[pscustomobject]@{
  query = $Query
  route_type = $RouteType
  category = $Category
  route_count = $route.count
  returned = $top.Count
  candidates = $top
} | ConvertTo-Json -Depth 12
