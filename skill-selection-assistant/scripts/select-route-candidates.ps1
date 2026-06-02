param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [ValidateSet("primary_domain", "domain_detail", "task_type")]
  [string]$RouteType = "domain_detail",

  [Parameter(Mandatory = $true)]
  [string]$Category,

  [int]$Limit = 12,
  [string]$IndexDir = "",
  [switch]$UseFullRoute,
  [switch]$KeepVariants
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

function New-UWord {
  param([int[]]$Codes)
  return (-join ($Codes | ForEach-Object { [char]$_ }))
}

function Test-ContainsUWord {
  param([string]$Text, [int[]]$Codes)
  return $Text.Contains((New-UWord -Codes $Codes))
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

$fileName = (Get-SafeFileName -Name $Category) + ".json"
$routePath = Join-Path (Join-Path (Join-Path $IndexDir "routes") $routeFolder) $fileName
$shortlistPath = Join-Path (Join-Path (Join-Path $IndexDir "shortlists") $routeFolder) $fileName
if ((-not $UseFullRoute) -and (Test-Path -LiteralPath $shortlistPath)) {
  $routePath = $shortlistPath
}

if (-not (Test-Path -LiteralPath $routePath)) {
  throw "Route file not found: $routePath. Re-run scan-local-skills.ps1 or choose a category from route-summary.md."
}

$route = Get-Content -LiteralPath $routePath -Raw -Encoding UTF8 | ConvertFrom-Json
$tokens = Get-TokenList -Text ($Query + " " + $Category)
$categoryTokens = Get-TokenList -Text $Category
$queryLower = $Query.ToLowerInvariant()
$wantsVisual = (
  $queryLower.Contains("ui") -or
  $queryLower.Contains("design") -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x597D,0x770B)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x7F8E,0x89C2)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x8BBE,0x8BA1)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x754C,0x9762))
)
$wantsTesting = (
  $queryLower.Contains("test") -or
  $queryLower.Contains("debug") -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x6D4B,0x8BD5)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x8C03,0x8BD5)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x62A5,0x9519)) -or
  (Test-ContainsUWord -Text $queryLower -Codes @(0x4FEE,0x590D))
)

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

  if ($wantsVisual -and ($haystack -match "design|visual|interface|ui|frontend")) {
    $score += 18
  }
  if ((-not $wantsTesting) -and (@($candidate.task_type) -contains "test-debug")) {
    $score -= 10
  }
  if ((-not $wantsTesting) -and ($candidate.name.ToLowerInvariant() -match "test|debug")) {
    $score -= 12
  }

  [pscustomobject]@{
    score = $score
    origin_priority = Get-OriginBoost -Origin $candidate.origin
    name = $candidate.name
    canonical_name = $(if ($candidate.PSObject.Properties.Name -contains "canonical_name") { $candidate.canonical_name } else { $candidate.name.ToLowerInvariant() })
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

if (-not $KeepVariants) {
  $merged = @()
  $scored | Group-Object canonical_name | ForEach-Object {
    $group = @($_.Group)
    $best = $group | Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "origin_priority"; Descending = $true }, name | Select-Object -First 1
    $best | Add-Member -NotePropertyName merged_variant_count -NotePropertyValue $group.Count -Force
    $best | Add-Member -NotePropertyName variants -NotePropertyValue @($group | Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "origin_priority"; Descending = $true }, name | ForEach-Object {
      [pscustomobject]@{
        score = $_.score
        name = $_.name
        origin = $_.origin
        setup_level = $_.setup_level
        relative_path = $_.relative_path
        skill_md = $_.skill_md
      }
    }) -Force
    $merged += $best
  }
  $scored = $merged
}

$top = @($scored | Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "origin_priority"; Descending = $true }, name | Select-Object -First $Limit)

[pscustomobject]@{
  query = $Query
  route_type = $RouteType
  category = $Category
  route_count = $route.count
  source_count = $(if ($route.PSObject.Properties.Name -contains "source_count") { $route.source_count } else { $route.count })
  source_file = $routePath
  merged_variants = (-not $KeepVariants)
  returned = $top.Count
  candidates = $top
} | ConvertTo-Json -Depth 12
