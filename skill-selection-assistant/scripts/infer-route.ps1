param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [string]$IndexDir = ""
)

$ErrorActionPreference = "Stop"

function Get-TokenList {
  param([string]$Text)
  if ([string]::IsNullOrWhiteSpace($Text)) { return @() }
  return @(
    [regex]::Matches($Text.ToLowerInvariant(), "[\p{L}\p{N}_]{2,}") |
      ForEach-Object { $_.Value } |
      Sort-Object -Unique
  )
}

function Add-Score {
  param([hashtable]$Scores, [string]$Key, [int]$Amount)
  if (-not $Scores.ContainsKey($Key)) { $Scores[$Key] = 0 }
  $Scores[$Key] += $Amount
}

function Match-Rule {
  param([string]$Text, [string]$Pattern)
  return ($Text -match $Pattern)
}

function Add-CnScore {
  param([hashtable]$Scores, [string]$Key, [int]$Amount, [object[]]$Words)
  foreach ($wordValue in $Words) {
    $word = [string]$wordValue
    if ($text.Contains($word)) {
      Add-Score -Scores $Scores -Key $Key -Amount $Amount
    }
  }
}

function ConvertTo-OrderedHashtable {
  param([object]$Object)
  $map = @{}
  if ($null -eq $Object) { return $map }
  foreach ($property in $Object.PSObject.Properties) {
    $map[$property.Name] = $property.Value
  }
  return $map
}

function Import-RuleConfig {
  param([string]$SkillDir)
  $rulesPath = Join-Path $SkillDir "rules\categories.json"
  if (-not (Test-Path -LiteralPath $rulesPath)) {
    throw "Shared category rules not found: $rulesPath"
  }
  return (Get-Content -LiteralPath $rulesPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}

$skillDir = Split-Path -Parent $PSScriptRoot
if (-not $IndexDir) {
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$ruleConfig = Import-RuleConfig -SkillDir $skillDir
$detailRules = ConvertTo-OrderedHashtable -Object $ruleConfig.domain_detail_rules
$taskRules = ConvertTo-OrderedHashtable -Object $ruleConfig.task_rules
$primaryMap = ConvertTo-OrderedHashtable -Object $ruleConfig.primary_map
$cnDetailWords = ConvertTo-OrderedHashtable -Object $ruleConfig.query_cn_detail_words
$cnTaskWords = ConvertTo-OrderedHashtable -Object $ruleConfig.query_cn_task_words

$summaryPath = Join-Path $IndexDir "route-summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
  throw "Route summary not found: $summaryPath. Re-run scan-local-skills.ps1 first."
}

$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$text = $Query.ToLowerInvariant()
$tokens = Get-TokenList -Text $Query

$detailScores = @{}
foreach ($key in $detailRules.Keys) {
  if (Match-Rule -Text $text -Pattern $detailRules[$key]) {
    Add-Score -Scores $detailScores -Key $key -Amount 20
  }
  foreach ($token in $tokens) {
    if ($key.Contains($token)) {
      Add-Score -Scores $detailScores -Key $key -Amount 8
    }
  }
}

$taskScores = @{}
foreach ($key in $taskRules.Keys) {
  if (Match-Rule -Text $text -Pattern $taskRules[$key]) {
    Add-Score -Scores $taskScores -Key $key -Amount 12
  }
}

foreach ($key in $cnDetailWords.Keys) {
  Add-CnScore -Scores $detailScores -Key $key -Amount 24 -Words @($cnDetailWords[$key])
}

foreach ($key in $cnTaskWords.Keys) {
  Add-CnScore -Scores $taskScores -Key $key -Amount 16 -Words @($cnTaskWords[$key])
}

$bestDetail = $detailScores.GetEnumerator() | Sort-Object @{ Expression = "Value"; Descending = $true }, Name | Select-Object -First 1
$bestTask = $taskScores.GetEnumerator() | Sort-Object @{ Expression = "Value"; Descending = $true }, Name | Select-Object -First 1

$routeType = "primary_domain"
$category = "general"
$confidence = 0
if ($bestDetail) {
  $routeType = "domain_detail"
  $category = $bestDetail.Key
  $confidence = [Math]::Min(100, [int]$bestDetail.Value * 4)
}
elseif ($bestTask) {
  $routeType = "task_type"
  $category = $bestTask.Key
  $confidence = [Math]::Min(70, [int]$bestTask.Value * 4)
}

$primaryDomain = "general"
if ($primaryMap.ContainsKey($category)) {
  $primaryDomain = $primaryMap[$category]
}
elseif ($routeType -eq "primary_domain") {
  $primaryDomain = $category
}

$available = $false
$summaryBucket = $null
switch ($routeType) {
  "domain_detail" { $summaryBucket = $summary.domain_detail }
  "task_type" { $summaryBucket = $summary.task_type }
  "primary_domain" { $summaryBucket = $summary.primary_domain }
}
$routeInfo = $summaryBucket | Where-Object { $_.name -eq $category } | Select-Object -First 1
if ($routeInfo) { $available = $true }

[pscustomobject]@{
  query = $Query
  route_type = $routeType
  category = $category
  primary_domain = $primaryDomain
  confidence = $confidence
  available = $available
  route_count = $(if ($routeInfo) { $routeInfo.PSObject.Properties["count"].Value } else { 0 })
  shortlist_file = $(if ($routeInfo -and ($routeInfo.PSObject.Properties.Name -contains "shortlist_file")) { $routeInfo.PSObject.Properties["shortlist_file"].Value } else { "" })
  selector_args = "-Query `"$Query`" -RouteType $routeType -Category $category -Limit 12"
  task_hint = $(if ($bestTask) { $bestTask.Key } else { "" })
} | ConvertTo-Json -Depth 8
