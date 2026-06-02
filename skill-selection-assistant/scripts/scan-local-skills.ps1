param(
  [string]$SkillsRoot = "",
  [string]$OutputDir = ""
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

  throw "Cannot find local Codex skills root. Pass -SkillsRoot explicitly."
}

function Get-FrontmatterValue {
  param([string[]]$Lines, [string]$Key)

  foreach ($line in $Lines) {
    if ($line -match ("^\s*" + [regex]::Escape($Key) + "\s*:\s*(.+?)\s*$")) {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ""
}

function Get-CategoryMatches {
  param([string]$Text, [hashtable]$Rules, [string]$Fallback)
  $hits = @()
  foreach ($key in $Rules.Keys) {
    if ($Text -match $Rules[$key]) {
      $hits += $key
    }
  }
  if ($hits.Count -eq 0 -and -not [string]::IsNullOrWhiteSpace($Fallback)) {
    $hits += $Fallback
  }
  return @($hits | Sort-Object -Unique)
}

function Join-UniqueValues {
  param([object[]]$Values)
  $out = @()
  foreach ($value in $Values) {
    foreach ($item in @($value)) {
      if ($null -eq $item) { continue }
      $text = [string]$item
      if ([string]::IsNullOrWhiteSpace($text)) { continue }
      $out += $text
    }
  }
  return @($out | Sort-Object -Unique)
}

function Normalize-SkillName {
  param([string]$Name)
  return (($Name -replace "\s+", "-").Trim().ToLowerInvariant())
}

function Get-SafeFileName {
  param([string]$Name)
  $safe = (($Name -replace "[^a-zA-Z0-9._-]", "-").Trim("-").ToLowerInvariant())
  if ([string]::IsNullOrWhiteSpace($safe)) { return "unknown" }
  return $safe
}

function Get-ShortText {
  param([string]$Text, [int]$MaxLength = 220)
  if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
  $flat = (($Text -replace "\s+", " ").Trim())
  if ($flat.Length -le $MaxLength) { return $flat }
  return $flat.Substring(0, $MaxLength).Trim() + "..."
}

function Get-ContentHash {
  param([string]$Text)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
  }
  finally {
    $sha.Dispose()
  }
}

function Get-OriginRank {
  param([string]$Origin)
  switch ($Origin) {
    "user-local" { return 1 }
    "official-system" { return 2 }
    "installed-topic" { return 3 }
    "linked-external" { return 4 }
    default { return 9 }
  }
}

function Get-SetupRank {
  param([string]$SetupLevel)
  switch ($SetupLevel) {
    "none" { return 1 }
    "local-runtime" { return 2 }
    "account" { return 3 }
    "network" { return 4 }
    default { return 9 }
  }
}

function Get-PrimaryDomain {
  param([string[]]$Details, [string[]]$Domains)

  foreach ($detail in @($Details)) {
    switch ($detail) {
      "academic-research" { return "research" }
      "document-processing" { return "documents" }
      "presentation-slides" { return "documents" }
      "spreadsheet-data" { return "data" }
      "data-analysis" { return "data" }
      "publishing-social" { return "publishing" }
      "visual-design" { return "design" }
      "media-video-audio" { return "design" }
      "security-risk" { return "safety" }
      "ai-ml" { return "coding" }
      "coding-general" { return "coding" }
      "frontend-web" { return "coding" }
      "backend-api" { return "coding" }
      "testing-debugging" { return "coding" }
      "devops-git" { return "coding" }
      "automation-integration" { return "coding" }
      "business-product" { return "data" }
      "writing-editing" { return "writing" }
      "translation-localization" { return "writing" }
    }
  }
  if (@($Domains).Count -gt 0) { return @($Domains)[0] }
  return "general"
}

function Get-WeightedDomainDetails {
  param([string]$NameText, [string]$MetaText, [string]$PreviewText)

  $scores = @{}
  foreach ($key in $domainDetailRules.Keys) {
    $score = 0
    $rule = $domainDetailRules[$key]
    if ($NameText -match $rule) { $score += 6 }
    if ($MetaText -match $rule) { $score += 3 }
    if ($PreviewText -match $rule) { $score += 1 }
    if ($score -gt 0) {
      $scores[$key] = $score
    }
  }

  if ($scores.Count -eq 0) {
    return @("general")
  }

  $strong = @($scores.GetEnumerator() | Where-Object { $_.Value -ge 3 } | Sort-Object @{ Expression = "Value"; Descending = $true }, Name | Select-Object -First 6)
  if ($strong.Count -eq 0) {
    $strong = @($scores.GetEnumerator() | Sort-Object @{ Expression = "Value"; Descending = $true }, Name | Select-Object -First 3)
  }
  return @($strong | ForEach-Object { $_.Key })
}

$domainDetailRules = [ordered]@{
  "academic-research" = "academic|paper|literature|citation|arxiv|research|scholar|thesis|abstract|methodology|empirical|experiment"
  "writing-editing" = "writing|writer|article|blog|copy|proofread|polish|tone|grammar|humanizer|story|outline"
  "translation-localization" = "translate|translation|localization|bilingual|language"
  "document-processing" = "pdf|docx|document|word|latex|ocr|text extraction|forms"
  "presentation-slides" = "pptx|slide|deck|presentation"
  "spreadsheet-data" = "excel|xlsx|spreadsheet|csv|table|stata|spss|sas"
  "data-analysis" = "data|analysis|analytics|visualization|dashboard|chart|benchmark|metrics|statistics|forecast"
  "ai-ml" = "\bai\b|ml|machine learning|llm|model|prompt|agent|rag|embedding|neural|classifier"
  "coding-general" = "code|coding|developer|software|programming|refactor|architecture|typescript|javascript|python|java|golang|rust"
  "frontend-web" = "frontend|react|vue|html|css|web|browser|ui|ux|tailwind"
  "backend-api" = "api|backend|server|database|sql|webhook|sdk|mcp|graphql|rest"
  "testing-debugging" = "test|debug|ci|qa|tdd|unit|integration|bug"
  "devops-git" = "git|github|deploy|docker|kubernetes|ci/cd|release"
  "security-risk" = "security|risk|guardrail|safety|privacy|auth|oauth|token|compliance|audit"
  "visual-design" = "image|design|diagram|cover|comic|visual|poster|logo|infographic|canvas|figma"
  "media-video-audio" = "video|audio|youtube|transcript|subtitle|podcast"
  "publishing-social" = "publish|post|wechat|weibo|xhs|twitter|social|newsletter"
  "business-product" = "product|prd|market|sales|customer|finance|business|strategy|roadmap"
  "automation-integration" = "automation|integrat|connector|composio|zapier|workflow"
}

$domainMap = @{
  "academic-research" = "research"
  "writing-editing" = "writing"
  "translation-localization" = "writing"
  "document-processing" = "documents"
  "presentation-slides" = "documents"
  "spreadsheet-data" = "data"
  "data-analysis" = "data"
  "ai-ml" = "coding"
  "coding-general" = "coding"
  "frontend-web" = "coding"
  "backend-api" = "coding"
  "testing-debugging" = "coding"
  "devops-git" = "coding"
  "security-risk" = "safety"
  "visual-design" = "design"
  "media-video-audio" = "design"
  "publishing-social" = "publishing"
  "business-product" = "data"
  "automation-integration" = "coding"
}

$taskRules = [ordered]@{
  summarize = "summar"
  review = "review|audit|evaluate|critique|check"
  generate = "generate|create|write|compose|draft|build"
  transform = "transform|convert|format|rewrite|refactor|migrate"
  "test-debug" = "test|debug|troubleshoot|fix|diagnose"
  extract = "extract|parse|scrape|transcript|ocr"
  publish = "publish|post|release|deploy"
  plan = "plan|strategy|roadmap|design"
  analyze = "analy|inspect|benchmark|measure"
}

$outputRules = [ordered]@{
  markdown = "markdown|md"
  image = "image|png|jpg|jpeg|webp|svg"
  pptx = "pptx|slide|deck|ppt"
  docx = "docx|word"
  xlsx = "xlsx|excel|spreadsheet|csv"
  html = "html|web"
  code = "code|script|typescript|javascript|python|powershell|shell"
  report = "report|brief|summary"
}

function Get-SetupLevel {
  param([string]$Text)
  if ($Text -match "api key|token|account|login|oauth|cookie|credential") { return "account" }
  if ($Text -match "install|download|npm|pip|python|node|browser|playwright|runtime") { return "local-runtime" }
  if ($Text -match "web|http|github|network|internet|remote") { return "network" }
  return "none"
}

function New-RouteEntry {
  param([object]$Skill)
  $descriptionText = $Skill.short_description
  if ([string]::IsNullOrWhiteSpace($descriptionText)) {
    $descriptionText = $Skill.description
  }

  return [pscustomobject]@{
    name = $Skill.name
    primary_domain = $Skill.primary_domain
    domain_detail = $Skill.domain_detail
    task_type = $Skill.task_type
    output_type = $Skill.output_type
    setup_level = $Skill.setup_level
    origin = $Skill.origin
    duplicate_count = $Skill.duplicate_count
    distinct_content_count = $Skill.distinct_content_count
    relative_path = $Skill.relative_path
    skill_md = $Skill.skill_md
    short_description = Get-ShortText -Text $descriptionText
  }
}

$skillsRootResolved = Resolve-SkillsRoot -ExplicitRoot $SkillsRoot
$skillDir = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
  $OutputDir = Join-Path $skillDir ".skill-index"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$recursiveSkillFiles = Get-ChildItem -LiteralPath $skillsRootResolved -Filter "SKILL.md" -Recurse -Force -ErrorAction SilentlyContinue
$topLevelSkillFiles = Get-ChildItem -LiteralPath $skillsRootResolved -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  $skillPath = Join-Path $_.FullName "SKILL.md"
  if (Test-Path -LiteralPath $skillPath) {
    Get-Item -LiteralPath $skillPath
  }
}
$skillFiles = @($recursiveSkillFiles + $topLevelSkillFiles) | Sort-Object FullName -Unique
$rawItems = @()

foreach ($file in $skillFiles) {
  $dir = Split-Path -Parent $file.FullName
  $dirItem = Get-Item -LiteralPath $dir
  $relative = $dir.Substring($skillsRootResolved.Length).TrimStart([char[]]@('\', '/'))
  $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
  $content = $lines -join "`n"
  $preview = ($lines | Select-Object -First 120) -join "`n"
  $name = Get-FrontmatterValue -Lines $lines -Key "name"
  if (-not $name) { $name = Split-Path -Leaf $dir }
  $description = Get-FrontmatterValue -Lines $lines -Key "description"
  $short = Get-FrontmatterValue -Lines $lines -Key "short-description"
  $nameText = $name.ToLowerInvariant()
  $metaText = "$description`n$short".ToLowerInvariant()
  $previewText = $preview.ToLowerInvariant()
  $combined = "$name`n$description`n$short`n$preview".ToLowerInvariant()

  $domainDetail = @(Get-WeightedDomainDetails -NameText $nameText -MetaText $metaText -PreviewText $previewText)
  $domain = @()
  foreach ($detail in $domainDetail) {
    if ($domainMap.ContainsKey($detail)) {
      $domain += $domainMap[$detail]
    }
  }
  if ($domain.Count -eq 0) { $domain += "general" }
  $domain = @($domain | Sort-Object -Unique)

  $origin = "user-local"
  if ($relative.StartsWith(".system")) { $origin = "official-system" }
  elseif ($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { $origin = "linked-external" }
  elseif ($name -match "^baoyu-" -or $relative -match "^baoyu-") { $origin = "installed-topic" }

  $setupLevel = Get-SetupLevel -Text $combined

  $rawItems += [pscustomobject]@{
    name = $name
    canonical_name = Normalize-SkillName -Name $name
    folder = Split-Path -Leaf $dir
    relative_path = $relative
    skill_md = $file.FullName
    origin = $origin
    origin_rank = Get-OriginRank -Origin $origin
    domain = $domain
    primary_domain = Get-PrimaryDomain -Details $domainDetail -Domains $domain
    domain_detail = $domainDetail
    task_type = @(Get-CategoryMatches -Text $combined -Rules $taskRules -Fallback "workflow")
    output_type = @(Get-CategoryMatches -Text $combined -Rules $outputRules -Fallback "workflow")
    setup_level = $setupLevel
    setup_rank = Get-SetupRank -SetupLevel $setupLevel
    status = "active"
    description = $description
    short_description = $short
    content_hash = Get-ContentHash -Text $content
    last_write_time = $file.LastWriteTime.ToString("s")
    last_write_ticks = $file.LastWriteTime.Ticks
  }
}

$items = @()
$duplicateGroups = @()

$rawItems | Group-Object canonical_name | ForEach-Object {
  $group = @($_.Group)
  $representative = $group | Sort-Object origin_rank, setup_rank, @{ Expression = "last_write_ticks"; Descending = $true } | Select-Object -First 1

  $sourcePaths = Join-UniqueValues -Values ($group | ForEach-Object { $_.relative_path })
  $sourceSkillFiles = Join-UniqueValues -Values ($group | ForEach-Object { $_.skill_md })
  $sourceOrigins = Join-UniqueValues -Values ($group | ForEach-Object { $_.origin })
  $domains = Join-UniqueValues -Values ($group | ForEach-Object { $_.domain })
  $domainDetails = Join-UniqueValues -Values ($group | ForEach-Object { $_.domain_detail })
  $taskTypes = Join-UniqueValues -Values ($group | ForEach-Object { $_.task_type })
  $outputTypes = Join-UniqueValues -Values ($group | ForEach-Object { $_.output_type })
  $contentHashes = Join-UniqueValues -Values ($group | ForEach-Object { $_.content_hash })

  if ($group.Count -gt 1) {
    $duplicateGroups += [pscustomobject]@{
      name = $representative.name
      canonical_name = $representative.canonical_name
      duplicate_count = $group.Count
      distinct_content_count = $contentHashes.Count
      source_origins = $sourceOrigins
      source_paths = $sourcePaths
    }
  }

  $items += [pscustomobject]@{
    name = $representative.name
    canonical_name = $representative.canonical_name
    folder = $representative.folder
    relative_path = $representative.relative_path
    skill_md = $representative.skill_md
    origin = $representative.origin
    source_origins = $sourceOrigins
    source_paths = $sourcePaths
    source_skill_md = $sourceSkillFiles
    duplicate_count = $group.Count
    distinct_content_count = $contentHashes.Count
    dedupe_status = $(if ($group.Count -gt 1) { "merged" } else { "unique" })
    domain = $domains
    primary_domain = Get-PrimaryDomain -Details $domainDetails -Domains $domains
    domain_detail = $domainDetails
    task_type = $taskTypes
    output_type = $outputTypes
    setup_level = $representative.setup_level
    status = "active"
    description = $representative.description
    short_description = $representative.short_description
    content_hashes = $contentHashes
    last_write_time = $representative.last_write_time
  }
}

$items = @($items | Sort-Object name)
$duplicateGroups = @($duplicateGroups | Sort-Object @{ Expression = "duplicate_count"; Descending = $true }, name)

$index = [pscustomobject]@{
  generated_at = (Get-Date).ToString("s")
  skills_root = $skillsRootResolved
  raw_total = $rawItems.Count
  total = $items.Count
  duplicate_groups = $duplicateGroups.Count
  duplicates_removed = ($rawItems.Count - $items.Count)
  skills = $items
  duplicates = $duplicateGroups
}

$index | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $OutputDir "skills-index.json") -Encoding UTF8

$routesDir = Join-Path $OutputDir "routes"
$primaryRoutesDir = Join-Path $routesDir "primary-domain"
$detailRoutesDir = Join-Path $routesDir "domain-detail"
$taskRoutesDir = Join-Path $routesDir "task-type"
New-Item -ItemType Directory -Force -Path $primaryRoutesDir, $detailRoutesDir, $taskRoutesDir | Out-Null

$routeSummary = [ordered]@{
  generated_at = $index.generated_at
  skills_root = $skillsRootResolved
  raw_total = $rawItems.Count
  total = $items.Count
  duplicate_groups = $duplicateGroups.Count
  duplicates_removed = ($rawItems.Count - $items.Count)
  route_rule = "Read this summary first, choose one primary_domain/domain_detail/task_type, then read only the matching route file before reading candidate SKILL.md files."
  primary_domain = @()
  domain_detail = @()
  task_type = @()
}

$routeSummaryLines = New-Object System.Collections.Generic.List[string]
$routeSummaryLines.Add("# Skill Route Summary")
$routeSummaryLines.Add("")
$routeSummaryLines.Add("- Generated: " + $index.generated_at)
$routeSummaryLines.Add("- Raw skills: " + $rawItems.Count)
$routeSummaryLines.Add("- Deduplicated skills: " + $items.Count)
$routeSummaryLines.Add("- Rule: determine category first, then read only the matching route file.")
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Primary Domain Routes")
$routeSummaryLines.Add("")
$items | Group-Object primary_domain | Sort-Object Count -Descending | ForEach-Object {
  $fileName = (Get-SafeFileName -Name $_.Name) + ".json"
  $routePath = Join-Path $primaryRoutesDir $fileName
  $entries = @($_.Group | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $routeObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "primary_domain"
    category = $_.Name
    count = $entries.Count
    candidates = $entries
  }
  $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
  $relativeRoutePath = "routes/primary-domain/" + $fileName
  $routeSummary.primary_domain += [pscustomobject]@{ name = $_.Name; count = $_.Count; file = $relativeRoutePath }
  $routeSummaryLines.Add(('- `{0}`: {1} -> `{2}`' -f $_.Name, $_.Count, $relativeRoutePath))
}
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Domain Detail Routes")
$routeSummaryLines.Add("")
$detailValues = Join-UniqueValues -Values ($items | ForEach-Object { $_.domain_detail })
foreach ($detail in $detailValues) {
  $groupItems = @($items | Where-Object { @($_.domain_detail) -contains $detail })
  $fileName = (Get-SafeFileName -Name $detail) + ".json"
  $routePath = Join-Path $detailRoutesDir $fileName
  $entries = @($groupItems | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $routeObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "domain_detail"
    category = $detail
    count = $entries.Count
    candidates = $entries
  }
  $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
  $relativeRoutePath = "routes/domain-detail/" + $fileName
  $routeSummary.domain_detail += [pscustomobject]@{ name = $detail; count = $entries.Count; file = $relativeRoutePath }
}
$routeSummary.domain_detail = @($routeSummary.domain_detail | Sort-Object @{ Expression = "count"; Descending = $true }, name)
$routeSummary.domain_detail | ForEach-Object {
  $routeSummaryLines.Add(('- `{0}`: {1} -> `{2}`' -f $_.name, $_.count, $_.file))
}
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Task Type Routes")
$routeSummaryLines.Add("")
$taskValues = Join-UniqueValues -Values ($items | ForEach-Object { $_.task_type })
foreach ($task in $taskValues) {
  $groupItems = @($items | Where-Object { @($_.task_type) -contains $task })
  $fileName = (Get-SafeFileName -Name $task) + ".json"
  $routePath = Join-Path $taskRoutesDir $fileName
  $entries = @($groupItems | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $routeObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "task_type"
    category = $task
    count = $entries.Count
    candidates = $entries
  }
  $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
  $relativeRoutePath = "routes/task-type/" + $fileName
  $routeSummary.task_type += [pscustomobject]@{ name = $task; count = $entries.Count; file = $relativeRoutePath }
}
$routeSummary.task_type = @($routeSummary.task_type | Sort-Object @{ Expression = "count"; Descending = $true }, name)
$routeSummary.task_type | ForEach-Object {
  $routeSummaryLines.Add(('- `{0}`: {1} -> `{2}`' -f $_.name, $_.count, $_.file))
}
$routeSummaryLines.Add("")

([pscustomobject]$routeSummary) | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutputDir "route-summary.json") -Encoding UTF8
Set-Content -LiteralPath (Join-Path $OutputDir "route-summary.md") -Value $routeSummaryLines -Encoding UTF8

$categoryLines = New-Object System.Collections.Generic.List[string]
$categoryLines.Add("# Local Skills Category Index")
$categoryLines.Add("")
$categoryLines.Add("- Generated: " + $index.generated_at)
$categoryLines.Add('- Skills root: `' + $skillsRootResolved + '`')
$categoryLines.Add("- Raw skills: " + $rawItems.Count)
$categoryLines.Add("- Deduplicated skills: " + $items.Count)
$categoryLines.Add("- Duplicate groups: " + $duplicateGroups.Count)
$categoryLines.Add("- Duplicates removed from index view: " + ($rawItems.Count - $items.Count))
$categoryLines.Add("")

$items | Group-Object origin | Sort-Object Name | ForEach-Object {
  $categoryLines.Add("## Origin: " + $_.Name)
  $categoryLines.Add("")
  $_.Group | Sort-Object name | ForEach-Object {
    $categoryLines.Add('- `' + $_.name + '` | primary: ' + $_.primary_domain + ' | detail: ' + ($_.domain_detail -join ', ') + ' | task: ' + ($_.task_type -join ', ') + ' | setup: ' + $_.setup_level + ' | dupes: ' + $_.duplicate_count)
  }
  $categoryLines.Add("")
}

$categoryLines.Add("## Duplicate Groups")
$categoryLines.Add("")
if ($duplicateGroups.Count -eq 0) {
  $categoryLines.Add("- None")
}
else {
  $duplicateGroups | Select-Object -First 200 | ForEach-Object {
    $categoryLines.Add('- `' + $_.name + '` | copies: ' + $_.duplicate_count + ' | distinct content: ' + $_.distinct_content_count + ' | origins: ' + ($_.source_origins -join ', '))
  }
}
$categoryLines.Add("")

Set-Content -LiteralPath (Join-Path $OutputDir "skills-categories.md") -Value $categoryLines -Encoding UTF8

$memoryPath = Join-Path $OutputDir "selection-memory.md"
if (-not (Test-Path -LiteralPath $memoryPath)) {
  @(
    "# Skill Selection Memory",
    "",
    "Use this file to record recurring user intents, good matches, missed matches, and category improvements.",
    "",
    "## Recurring Patterns",
    "",
    "## Missed Matches",
    "",
    "## Category Improvements"
  ) | Set-Content -LiteralPath $memoryPath -Encoding UTF8
}

[pscustomobject]@{
  SkillsRoot = $skillsRootResolved
  OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
  RawTotal = $rawItems.Count
  Total = $items.Count
  DuplicateGroups = $duplicateGroups.Count
  DuplicatesRemoved = ($rawItems.Count - $items.Count)
  Index = Join-Path $OutputDir "skills-index.json"
  Categories = Join-Path $OutputDir "skills-categories.md"
  RouteSummary = Join-Path $OutputDir "route-summary.json"
  RoutesDir = $routesDir
}
