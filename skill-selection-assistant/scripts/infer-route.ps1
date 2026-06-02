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

function New-UWord {
  param([int[]]$Codes)
  return (-join ($Codes | ForEach-Object { [char]$_ }))
}

function Add-CnScore {
  param([hashtable]$Scores, [string]$Key, [int]$Amount, [object[]]$Words)
  foreach ($wordCodes in $Words) {
    $word = New-UWord -Codes $wordCodes
    if ($text.Contains($word)) {
      Add-Score -Scores $Scores -Key $Key -Amount $Amount
    }
  }
}

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

$summaryPath = Join-Path $IndexDir "route-summary.json"
if (-not (Test-Path -LiteralPath $summaryPath)) {
  throw "Route summary not found: $summaryPath. Re-run scan-local-skills.ps1 first."
}

$summary = Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$text = $Query.ToLowerInvariant()
$tokens = Get-TokenList -Text $Query

$detailRules = [ordered]@{
  "frontend-web" = "frontend|front-end|react|vue|html|css|tailwind|ui|ux|web page|website|component"
  "backend-api" = "backend|api|server|database|sql|webhook|graphql|rest"
  "testing-debugging" = "test|debug|bug|qa|ci|tdd|fix|diagnose"
  "academic-research" = "paper|academic|research|literature|citation|arxiv|scholar"
  "document-processing" = "pdf|docx|document|word|ocr|file|parse|extract"
  "presentation-slides" = "ppt|pptx|slide|deck|presentation"
  "spreadsheet-data" = "excel|xlsx|spreadsheet|csv|table"
  "data-analysis" = "data|analysis|analytics|chart|dashboard|statistics|visualization"
  "visual-design" = "image|design|diagram|poster|logo|visual|cover"
  "publishing-social" = "publish|post|wechat|weibo|twitter|xhs|newsletter"
  "writing-editing" = "write|writing|article|blog|copy|proofread|polish|rewrite"
  "translation-localization" = "translate|translation|localization|bilingual"
  "security-risk" = "security|risk|privacy|auth|audit"
  "devops-git" = "git|github|deploy|docker|release|commit|repo"
  "ai-ml" = "\bai\b|llm|model|prompt|agent|rag|machine learning"
  "automation-integration" = "automation|workflow|integrat|connector"
  "business-product" = "product|prd|market|sales|finance|business"
  "media-video-audio" = "video|audio|youtube|transcript|subtitle"
  "coding-general" = "code|coding|program|script|develop"
}

$taskRules = [ordered]@{
  "generate" = "generate|create|write|build|make"
  "review" = "review|audit|check|inspect"
  "test-debug" = "test|debug|fix|diagnose"
  "plan" = "plan|strategy|roadmap|design"
  "transform" = "convert|format|rewrite|refactor"
  "analyze" = "analy|inspect|diagnose|research"
  "publish" = "publish|post|release|deploy"
  "extract" = "extract|parse|scrape"
  "summarize" = "summar"
  "workflow" = "workflow|process|mechanism"
}

$primaryMap = @{
  "frontend-web" = "coding"
  "backend-api" = "coding"
  "testing-debugging" = "coding"
  "devops-git" = "coding"
  "ai-ml" = "coding"
  "automation-integration" = "coding"
  "coding-general" = "coding"
  "academic-research" = "research"
  "document-processing" = "documents"
  "presentation-slides" = "documents"
  "spreadsheet-data" = "data"
  "data-analysis" = "data"
  "business-product" = "data"
  "visual-design" = "design"
  "media-video-audio" = "design"
  "publishing-social" = "publishing"
  "writing-editing" = "writing"
  "translation-localization" = "writing"
  "security-risk" = "safety"
}

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

Add-CnScore -Scores $detailScores -Key "frontend-web" -Amount 24 -Words @(@(0x524D,0x7AEF), @(0x9875,0x9762), @(0x7F51,0x9875), @(0x754C,0x9762), @(0x7F51,0x7AD9), @(0x7EC4,0x4EF6))
Add-CnScore -Scores $detailScores -Key "backend-api" -Amount 24 -Words @(@(0x540E,0x7AEF), @(0x63A5,0x53E3), @(0x6570,0x636E,0x5E93), @(0x670D,0x52A1,0x7AEF))
Add-CnScore -Scores $detailScores -Key "testing-debugging" -Amount 24 -Words @(@(0x6D4B,0x8BD5), @(0x8C03,0x8BD5), @(0x62A5,0x9519), @(0x4FEE,0x590D), @(0x8BCA,0x65AD))
Add-CnScore -Scores $detailScores -Key "academic-research" -Amount 24 -Words @(@(0x8BBA,0x6587), @(0x5B66,0x672F), @(0x7814,0x7A76), @(0x6587,0x732E), @(0x5F15,0x7528))
Add-CnScore -Scores $detailScores -Key "document-processing" -Amount 24 -Words @(@(0x6587,0x6863), @(0x6587,0x4EF6), @(0x63D0,0x53D6), @(0x89E3,0x6790))
Add-CnScore -Scores $detailScores -Key "presentation-slides" -Amount 24 -Words @(@(0x5E7B,0x706F,0x7247), @(0x6F14,0x793A), @(0x6C47,0x62A5))
Add-CnScore -Scores $detailScores -Key "spreadsheet-data" -Amount 24 -Words @(@(0x8868,0x683C), @(0x7535,0x5B50,0x8868,0x683C))
Add-CnScore -Scores $detailScores -Key "data-analysis" -Amount 24 -Words @(@(0x6570,0x636E), @(0x5206,0x6790), @(0x56FE,0x8868), @(0x53EF,0x89C6,0x5316))
Add-CnScore -Scores $detailScores -Key "visual-design" -Amount 24 -Words @(@(0x56FE,0x7247), @(0x8BBE,0x8BA1), @(0x6D77,0x62A5), @(0x5C01,0x9762), @(0x89C6,0x89C9))
Add-CnScore -Scores $detailScores -Key "publishing-social" -Amount 24 -Words @(@(0x53D1,0x5E03), @(0x516C,0x4F17,0x53F7), @(0x5C0F,0x7EA2,0x4E66), @(0x5FAE,0x535A), @(0x63A8,0x6587))
Add-CnScore -Scores $detailScores -Key "writing-editing" -Amount 24 -Words @(@(0x6587,0x7AE0), @(0x5199,0x4F5C), @(0x6DA6,0x8272), @(0x6539,0x5199), @(0x6587,0x6848))
Add-CnScore -Scores $detailScores -Key "translation-localization" -Amount 24 -Words @(@(0x7FFB,0x8BD1), @(0x672C,0x5730,0x5316), @(0x53CC,0x8BED))
Add-CnScore -Scores $detailScores -Key "security-risk" -Amount 24 -Words @(@(0x5B89,0x5168), @(0x98CE,0x9669), @(0x9690,0x79C1), @(0x5BA1,0x8BA1))
Add-CnScore -Scores $detailScores -Key "devops-git" -Amount 24 -Words @(@(0x90E8,0x7F72), @(0x63D0,0x4EA4), @(0x4ED3,0x5E93), @(0x7248,0x672C))
Add-CnScore -Scores $detailScores -Key "ai-ml" -Amount 24 -Words @(@(0x673A,0x5668,0x5B66,0x4E60), @(0x6A21,0x578B), @(0x667A,0x80FD,0x4F53), @(0x63D0,0x793A,0x8BCD))
Add-CnScore -Scores $detailScores -Key "automation-integration" -Amount 24 -Words @(@(0x81EA,0x52A8,0x5316), @(0x6D41,0x7A0B), @(0x96C6,0x6210), @(0x8FDE,0x63A5,0x5668))
Add-CnScore -Scores $detailScores -Key "business-product" -Amount 24 -Words @(@(0x4EA7,0x54C1), @(0x9700,0x6C42), @(0x5546,0x4E1A), @(0x5E02,0x573A), @(0x9500,0x552E))
Add-CnScore -Scores $detailScores -Key "media-video-audio" -Amount 24 -Words @(@(0x89C6,0x9891), @(0x97F3,0x9891), @(0x5B57,0x5E55), @(0x8F6C,0x5F55))
Add-CnScore -Scores $detailScores -Key "coding-general" -Amount 24 -Words @(@(0x4EE3,0x7801), @(0x7F16,0x7A0B), @(0x811A,0x672C), @(0x5F00,0x53D1))

Add-CnScore -Scores $taskScores -Key "generate" -Amount 16 -Words @(@(0x751F,0x6210), @(0x521B,0x5EFA), @(0x642D,0x5EFA), @(0x5236,0x4F5C))
Add-CnScore -Scores $taskScores -Key "review" -Amount 16 -Words @(@(0x8BC4,0x5BA1), @(0x5BA1,0x67E5), @(0x68C0,0x67E5), @(0x770B,0x770B))
Add-CnScore -Scores $taskScores -Key "test-debug" -Amount 16 -Words @(@(0x6D4B,0x8BD5), @(0x8C03,0x8BD5), @(0x4FEE,0x590D), @(0x62A5,0x9519))
Add-CnScore -Scores $taskScores -Key "plan" -Amount 16 -Words @(@(0x65B9,0x6848), @(0x8BA1,0x5212), @(0x89C4,0x5212), @(0x8BBE,0x8BA1))
Add-CnScore -Scores $taskScores -Key "transform" -Amount 16 -Words @(@(0x8F6C,0x6362), @(0x683C,0x5F0F,0x5316), @(0x6539,0x5199), @(0x91CD,0x6784))
Add-CnScore -Scores $taskScores -Key "analyze" -Amount 16 -Words @(@(0x5206,0x6790), @(0x8BCA,0x65AD), @(0x7814,0x7A76))
Add-CnScore -Scores $taskScores -Key "publish" -Amount 16 -Words @(@(0x53D1,0x5E03), @(0x63A8,0x9001), @(0x4E0A,0x7EBF))
Add-CnScore -Scores $taskScores -Key "extract" -Amount 16 -Words @(@(0x63D0,0x53D6), @(0x89E3,0x6790), @(0x6293,0x53D6))
Add-CnScore -Scores $taskScores -Key "summarize" -Amount 16 -Words @(@(0x603B,0x7ED3), @(0x6458,0x8981), @(0x6982,0x62EC))
Add-CnScore -Scores $taskScores -Key "workflow" -Amount 16 -Words @(@(0x6D41,0x7A0B), @(0x673A,0x5236))

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
