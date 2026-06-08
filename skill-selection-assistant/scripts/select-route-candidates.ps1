param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [ValidateSet("primary_domain", "domain_detail", "specialty", "adaptive_leaf", "task_type")]
  [string]$RouteType = "domain_detail",

  [Parameter(Mandatory = $true)]
  [string]$Category,

  [int]$Limit = 0,
  [int]$MaxRecommendations = 8,
  [int]$MinRecommendations = 1,
  [int]$ScoreWindow = 3,
  [int]$MinRelevanceScore = 3,
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
  $tokens = @(
    [regex]::Matches($Text.ToLowerInvariant(), "[\p{L}\p{N}_]{2,}") |
      ForEach-Object { $_.Value } |
      Sort-Object -Unique
  )
  $cjk = -join ([regex]::Matches($Text, "[\u4e00-\u9fff]") | ForEach-Object { $_.Value })
  if ($cjk.Length -ge 2) {
    for ($i = 0; $i -le $cjk.Length - 2; $i++) {
      $tokens += $cjk.Substring($i, 2)
    }
  }
  return @($tokens | Sort-Object -Unique)
}

function Get-UsefulQueryTokens {
  param([string[]]$Tokens)

  $stopTokens = @(
    "the", "and", "for", "with", "this", "that", "into", "from", "using",
    "use", "make", "create", "build", "write", "organize", "please", "help"
  )

  return @(
    $Tokens |
      Where-Object {
        $token = [string]$_
        (-not [string]::IsNullOrWhiteSpace($token)) -and
          $token.Length -ge 2 -and
          ($stopTokens -notcontains $token)
      } |
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

function Normalize-SkillName {
  param([string]$Name)
  return (($Name -replace "\s+", "-").Trim().ToLowerInvariant())
}

function Add-MemoryScore {
  param([hashtable]$Scores, [string]$SkillName, [int]$Amount)
  if ([string]::IsNullOrWhiteSpace($SkillName)) { return }
  $key = Normalize-SkillName -Name $SkillName
  if (-not $Scores.ContainsKey($key)) { $Scores[$key] = 0 }
  $Scores[$key] += $Amount
}

function Import-SelectionMemoryScores {
  param([string]$Path, [string]$Category)

  $scores = @{}
  if (-not (Test-Path -LiteralPath $Path)) { return $scores }

  $currentOutcome = ""
  $currentSkill = ""
  $currentRoute = ""

  function Commit-MemoryEntry {
    if ([string]::IsNullOrWhiteSpace($currentSkill) -or [string]::IsNullOrWhiteSpace($currentOutcome)) { return }

    $categoryMatches = $true
    if (-not [string]::IsNullOrWhiteSpace($Category) -and -not [string]::IsNullOrWhiteSpace($currentRoute)) {
      $categoryMatches = $currentRoute.Contains($Category)
    }
    $multiplier = $(if ($categoryMatches) { 1 } else { 0.5 })

    switch ($currentOutcome) {
      "selected" { Add-MemoryScore -Scores $scores -SkillName $currentSkill -Amount ([int](60 * $multiplier)) }
      "rejected" { Add-MemoryScore -Scores $scores -SkillName $currentSkill -Amount ([int](-24 * $multiplier)) }
      "setup-failed" { Add-MemoryScore -Scores $scores -SkillName $currentSkill -Amount ([int](-16 * $multiplier)) }
      "missed" { Add-MemoryScore -Scores $scores -SkillName $currentSkill -Amount ([int](20 * $multiplier)) }
    }
  }

  foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
    if ($line -match "^###\s+") {
      Commit-MemoryEntry
      $currentOutcome = ""
      $currentSkill = ""
      $currentRoute = ""
      continue
    }
    if ($line -match '^- outcome:\s+`?([^`]+?)`?\s*$') {
      $currentOutcome = $Matches[1].Trim()
      continue
    }
    if ($line -match '^- selected_skill:\s+`?([^`]+?)`?\s*$') {
      $currentSkill = $Matches[1].Trim()
      continue
    }
    if ($line -match '^- route:\s+`?([^`]+?)`?\s*/\s*`?([^`]+?)`?\s*$') {
      $currentRoute = ($Matches[1].Trim() + "/" + $Matches[2].Trim())
      continue
    }
  }
  Commit-MemoryEntry

  return $scores
}

function New-UWord {
  param([int[]]$Codes)
  return (-join ($Codes | ForEach-Object { [char]$_ }))
}

function Test-ContainsUWord {
  param([string]$Text, [int[]]$Codes)
  return $Text.Contains((New-UWord -Codes $Codes))
}

function Add-TokenIfContainsUWord {
  param([System.Collections.ArrayList]$Tokens, [string]$Text, [int[]]$Codes, [string[]]$Add)
  if (Test-ContainsUWord -Text $Text -Codes $Codes) {
    foreach ($token in $Add) {
      if (-not [string]::IsNullOrWhiteSpace($token)) {
        [void]$Tokens.Add($token)
      }
    }
  }
}

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$routeFolder = switch ($RouteType) {
  "primary_domain" { "primary-domain" }
  "domain_detail" { "domain-detail" }
  "specialty" { "specialty" }
  "adaptive_leaf" { "adaptive-leaf" }
  "task_type" { "task-type" }
}

$fileName = (Get-SafeFileName -Name $Category) + ".json"
$routePath = Join-Path (Join-Path (Join-Path $IndexDir "routes") $routeFolder) $fileName
$shortlistPath = Join-Path (Join-Path (Join-Path $IndexDir "shortlists") $routeFolder) $fileName
if ((-not $UseFullRoute) -and (Test-Path -LiteralPath $shortlistPath)) {
  $routePath = $shortlistPath
}

if (-not (Test-Path -LiteralPath $routePath)) {
  if ($UseFullRoute) {
    throw "Full route file not found: $routePath. Re-run scan-local-skills.ps1 with -IncludeFullRoutes, or omit -UseFullRoute to use the generated shortlist."
  }
  throw "Shortlist file not found: $routePath. Re-run scan-local-skills.ps1 or choose a category from route-summary.md."
}

$route = Get-Content -LiteralPath $routePath -Raw -Encoding UTF8 | ConvertFrom-Json
$queryTokens = Get-TokenList -Text $Query
$tokens = Get-TokenList -Text ($Query + " " + $Category)
$usefulQueryTokens = Get-UsefulQueryTokens -Tokens $queryTokens
$categoryTokens = Get-TokenList -Text $Category
$leafSpecialty = ""
$leafTask = ""
if (($RouteType -eq "adaptive_leaf") -and ($Category -match "^specialty=(.+?)\|task=(.+)$")) {
  $leafSpecialty = $Matches[1]
  $leafTask = $Matches[2]
  $categoryTokens = Get-TokenList -Text ($leafSpecialty + " " + $leafTask)
}
$memoryScores = Import-SelectionMemoryScores -Path (Join-Path $IndexDir "selection-memory.md") -Category $Category
$queryLower = $Query.ToLowerInvariant()
$expandedQueryTokens = [System.Collections.ArrayList]::new()
foreach ($token in $usefulQueryTokens) { [void]$expandedQueryTokens.Add($token) }
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x524D,0x7AEF) -Add @("frontend", "ui", "web", "page")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x9875,0x9762) -Add @("page", "web", "frontend", "ui")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x9879,0x76EE) -Add @("project", "workspace", "repo", "repository", "local")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x672C,0x5730) -Add @("local", "workspace", "project")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x7ED3,0x6784) -Add @("structure", "architecture", "organize", "project")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x673A,0x5668,0x4EBA) -Add @("bot", "agent", "automation")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x5B66,0x672F) -Add @("academic", "research", "paper")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x8BBA,0x6587) -Add @("paper", "academic", "research", "literature")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x5F15,0x7528) -Add @("citation", "reference", "bibliography")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6570,0x636E) -Add @("data", "analysis", "analytics", "spreadsheet")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x56FE,0x8868) -Add @("chart", "visualization", "dataviz", "plot")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x4EE3,0x7801) -Add @("code", "coding", "programming")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6D4B,0x8BD5) -Add @("test", "testing", "debug")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x68C0,0x67E5) -Add @("review", "audit", "check", "debug")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x56FE,0x7247) -Add @("image", "visual", "design")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x56FE,0x50CF) -Add @("image", "visual", "design")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6587,0x6863) -Add @("document", "file", "pdf", "extract", "parse")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6587,0x4EF6) -Add @("document", "file", "extract", "parse")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x63D0,0x53D6) -Add @("extract", "parse", "text", "ocr")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x89E3,0x6790) -Add @("parse", "extract", "text")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x77E5,0x8BC6,0x5E93) -Add @("knowledge", "notes", "obsidian", "vault", "wiki")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x7B14,0x8BB0) -Add @("notes", "notebook", "knowledge", "markdown")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6574,0x7406) -Add @("organize", "structure", "summarize", "knowledge")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6280,0x80FD) -Add @("skill", "skills")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x8DEF,0x7531) -Add @("router", "routing", "route", "selection")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x81EA,0x751F,0x957F) -Add @("self-growth", "self-growing", "growth", "index", "memory")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x81EA,0x589E,0x957F) -Add @("self-growth", "self-growing", "growth", "index", "memory")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x672C,0x673A,0x73AF,0x5883) -Add @("local", "machine", "skills", "index")
Add-TokenIfContainsUWord -Tokens $expandedQueryTokens -Text $queryLower -Codes @(0x6D6A,0x8D39) -Add @("token", "shortlist", "minimize")
$usefulQueryTokens = @($expandedQueryTokens | Sort-Object -Unique)
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
    (@($candidate.specialty) -join " "),
    (@($candidate.task_type) -join " "),
    (@($candidate.output_type) -join " "),
    $candidate.relative_path
  ) -join " "
  $haystack = $haystack.ToLowerInvariant()

  $score = Get-OriginBoost -Origin $candidate.origin
  $relevanceScore = 0
  foreach ($token in $tokens) {
    if ($candidate.name.ToLowerInvariant() -eq $token) { $score += 30 }
    elseif ($candidate.name.ToLowerInvariant().Contains($token)) { $score += 12 }
    elseif ($haystack.Contains($token)) { $score += 4 }
  }

  foreach ($token in $usefulQueryTokens) {
    if ($candidate.name.ToLowerInvariant().Contains($token)) { $relevanceScore += 4 }
    elseif ([string]$candidate.relative_path -and ([string]$candidate.relative_path).ToLowerInvariant().Contains($token)) { $relevanceScore += 3 }
    elseif ($haystack.Contains($token)) { $relevanceScore += 1 }
  }

  foreach ($token in $categoryTokens) {
    if ($candidate.name.ToLowerInvariant().Contains($token)) { $score += 18 }
    elseif ($haystack.Contains($token)) { $score += 5 }
  }

  if (@($candidate.domain_detail) -contains $Category) { $score += 8 }
  if (@($candidate.specialty) -contains $Category) {
    $score += 14
    $relevanceScore += 2
  }
  if ($leafSpecialty -and (@($candidate.specialty) -contains $leafSpecialty)) {
    $score += 14
    $relevanceScore += 2
  }
  if ($leafTask -and (@($candidate.task_type) -contains $leafTask)) {
    $score += 10
    $relevanceScore += 1
  }
  if ($candidate.primary_domain -eq $Category) { $score += 8 }
  if (@($candidate.task_type) -contains $Category) { $score += 5 }
  if ([int]$candidate.duplicate_count -gt 1) { $score += [Math]::Min([int]$candidate.duplicate_count, 6) }
  if ($haystack -match "project|workspace|repo|repository|local") {
    $score += 28
  }
  if ([string]$candidate.relative_path -notmatch "^(gh\d+|er\d+|baoyu-|composio-|awesome-|anthropic)") {
    $score += 12
  }

  if ($wantsVisual -and ($haystack -match "design|visual|interface|ui|frontend")) {
    $score += 18
  }
  if ((-not $wantsTesting) -and (@($candidate.task_type) -contains "test-debug")) {
    $score -= 10
  }
  if ((-not $wantsTesting) -and ($candidate.name.ToLowerInvariant() -match "test|debug")) {
    $score -= 12
  }

  $canonicalName = $(if ($candidate.PSObject.Properties.Name -contains "canonical_name") { $candidate.canonical_name } else { Normalize-SkillName -Name $candidate.name })
  $memoryScore = 0
  if ($memoryScores.ContainsKey($canonicalName)) {
    $memoryScore = [int]$memoryScores[$canonicalName]
    $score += $memoryScore
  }
  $score += ($relevanceScore * 4)

  $candidateResult = [pscustomobject]@{
    score = $score
    origin_priority = Get-OriginBoost -Origin $candidate.origin
    name = $candidate.name
    canonical_name = $canonicalName
    reason_hint = $candidate.short_description
    primary_domain = $candidate.primary_domain
    domain_detail = $candidate.domain_detail
    specialty = $candidate.specialty
    task_type = $candidate.task_type
    setup_level = $candidate.setup_level
    origin = $candidate.origin
    duplicate_count = $candidate.duplicate_count
    relevance_score = $relevanceScore
    relative_path = $candidate.relative_path
    skill_md = $candidate.skill_md
  }
  if ($memoryScore -ne 0) {
    $candidateResult | Add-Member -NotePropertyName memory_score -NotePropertyValue $memoryScore -Force
  }
  $candidateResult
}

if (-not $KeepVariants) {
  $merged = @()
  $scored | Group-Object canonical_name | ForEach-Object {
    $group = @($_.Group)
    $best = $group | Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "origin_priority"; Descending = $true }, name | Select-Object -First 1
    $best | Add-Member -NotePropertyName merged_variant_count -NotePropertyValue $group.Count -Force
    if ($group.Count -gt 1) {
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
    }
    $merged += $best
  }
  $scored = $merged
}

$sorted = @($scored | Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "origin_priority"; Descending = $true }, name)
$selectionMode = "explicit_limit"
$scoreThreshold = $null
if ($Limit -gt 0) {
  $top = @($sorted | Select-Object -First $Limit)
}
else {
  $selectionMode = "dynamic_score_window"
  $top = @()
  $eligible = @($sorted | Where-Object { [int]$_.relevance_score -ge $MinRelevanceScore })
  if ($eligible.Count -gt 0) {
    $topScore = [int]$eligible[0].score
    $scoreThreshold = $topScore - $ScoreWindow
    $top = @($eligible | Where-Object { [int]$_.score -ge $scoreThreshold } | Select-Object -First $MaxRecommendations)
    if ($top.Count -lt $MinRecommendations) {
      $top = @($eligible | Select-Object -First ([Math]::Min($MinRecommendations, $eligible.Count)))
    }
  }
  else {
    $selectionMode = "low_confidence_no_match"
  }
}

[pscustomobject]@{
  query = $Query
  route_type = $RouteType
  category = $Category
  route_count = $route.count
  source_count = $(if ($route.PSObject.Properties.Name -contains "source_count") { $route.source_count } else { $route.count })
  source_file = $routePath
  merged_variants = (-not $KeepVariants)
  returned = $top.Count
  recommendation_policy = [pscustomobject]@{
    mode = $selectionMode
    explicit_limit = $(if ($Limit -gt 0) { $Limit } else { $null })
    min_recommendations = $MinRecommendations
    max_recommendations = $MaxRecommendations
    score_window = $ScoreWindow
    min_relevance_score = $MinRelevanceScore
    score_threshold = $scoreThreshold
  }
  candidates = $top
} | ConvertTo-Json -Depth 12
