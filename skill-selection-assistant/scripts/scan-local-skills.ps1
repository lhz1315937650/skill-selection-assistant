param(
  [string]$SkillsRoot = "",
  [string]$OutputDir = "",
  [switch]$IncludeFullRoutes
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

function Get-ObjectProperty {
  param([object]$Object, [string]$Name, [object]$Default = $null)
  if ($null -eq $Object) { return $Default }
  if ($Object.PSObject.Properties.Name -contains $Name) {
    return $Object.PSObject.Properties[$Name].Value
  }
  return $Default
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

function Import-ParseCache {
  param([string]$Path)
  $items = @()
  if (-not (Test-Path -LiteralPath $Path)) { return $items }

  if ([IO.Path]::GetExtension($Path).Equals(".ndjson", [System.StringComparison]::OrdinalIgnoreCase)) {
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
      if ([string]::IsNullOrWhiteSpace($line)) { continue }
      $items += ($line | ConvertFrom-Json)
    }
    return $items
  }

  $cache = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
  return @($cache.items)
}

function Export-ParseCache {
  param([object[]]$Items, [string]$Path)
  $lines = @($Items | ForEach-Object { $_ | ConvertTo-Json -Depth 20 -Compress })
  Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
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
    if ($domainMap.ContainsKey($detail)) {
      return $domainMap[$detail]
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
    canonical_name = $Skill.canonical_name
    primary_domain = $Skill.primary_domain
    domain_detail = $Skill.domain_detail
    task_type = $Skill.task_type
    output_type = $Skill.output_type
    setup_level = $Skill.setup_level
    origin = $Skill.origin
    duplicate_count = $Skill.duplicate_count
    duplicate_name_count = $Skill.duplicate_name_count
    distinct_content_count = $Skill.distinct_content_count
    variant_id = $Skill.variant_id
    variant_index = $Skill.variant_index
    variant_count = $Skill.variant_count
    dedupe_status = $Skill.dedupe_status
    relative_path = $Skill.relative_path
    skill_md = $Skill.skill_md
    short_description = Get-ShortText -Text $descriptionText
  }
}

function Get-RoutePriority {
  param([object]$Entry)

  $score = 0
  switch ($Entry.origin) {
    "user-local" { $score += 50 }
    "official-system" { $score += 40 }
    "installed-topic" { $score += 35 }
    "linked-external" { $score += 10 }
    default { $score += 0 }
  }

  switch ($Entry.setup_level) {
    "none" { $score += 10 }
    "local-runtime" { $score += 8 }
    "account" { $score += 4 }
    "network" { $score += 2 }
    default { $score += 0 }
  }

  if ([int]$Entry.duplicate_count -gt 1) {
    $score += [Math]::Min([int]$Entry.duplicate_count, 6)
  }
  if ([int]$Entry.distinct_content_count -gt 1) {
    $score += 3
  }

  $routeText = (($Entry.name, $Entry.relative_path, $Entry.short_description) -join " ").ToLowerInvariant()
  if ($routeText -match "project|workspace|repo|repository|local") {
    $score += 50
  }
  if ($Entry.relative_path -notmatch "^(gh\d+|er\d+|baoyu-|composio-|awesome-|anthropic)") {
    $score += 20
  }

  return $score
}

function Add-RouteMapItem {
  param([hashtable]$Map, [string]$Key, [object]$Item)
  if ([string]::IsNullOrWhiteSpace($Key)) { $Key = "general" }
  $Key = [string]$Key
  if (-not $Map.ContainsKey($Key)) {
    $Map[$Key] = @()
  }
  $Map[$Key] = @($Map[$Key]) + $Item
}

$skillsRootResolved = Resolve-SkillsRoot -ExplicitRoot $SkillsRoot
$skillDir = Split-Path -Parent $PSScriptRoot
$ruleConfig = Import-RuleConfig -SkillDir $skillDir
$RulesSchemaVersion = [string]$ruleConfig.schema_version
$domainDetailRules = ConvertTo-OrderedHashtable -Object $ruleConfig.domain_detail_rules
$domainMap = ConvertTo-OrderedHashtable -Object $ruleConfig.primary_map
$taskRules = ConvertTo-OrderedHashtable -Object $ruleConfig.task_rules
$outputRules = ConvertTo-OrderedHashtable -Object $ruleConfig.output_rules
if (-not $OutputDir) {
  $OutputDir = Join-Path $skillDir ".skill-index"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputSchemaVersion = "1.5.10"
$ParserSchemaVersion = "1.0"
$manifestPath = Join-Path $OutputDir "manifest.json"
$parseCachePath = Join-Path $OutputDir "parsed-skills-cache.ndjson"
$legacyParseCachePath = Join-Path $OutputDir "parsed-skills-cache.json"
$previousManifestByPath = @{}
$previousCacheByPath = @{}
if (Test-Path -LiteralPath $manifestPath) {
  try {
    $previousManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $previousParserSchemaVersion = Get-ObjectProperty -Object $previousManifest -Name "parser_schema_version" -Default ""
    $previousRulesSchemaVersion = Get-ObjectProperty -Object $previousManifest -Name "rules_schema_version" -Default ""
    if (-not $previousParserSchemaVersion) { $previousParserSchemaVersion = "1.0" }
    if (-not $previousRulesSchemaVersion) { $previousRulesSchemaVersion = "1.0" }
    if (($previousParserSchemaVersion -eq $ParserSchemaVersion) -and ($previousRulesSchemaVersion -eq $RulesSchemaVersion)) {
      foreach ($entry in @($previousManifest.files)) {
        if ($entry.skill_md) {
          $previousManifestByPath[[string]$entry.skill_md] = $entry
        }
      }
    }
  }
  catch {
    $previousManifestByPath = @{}
  }
}
if ($previousManifestByPath.Count -gt 0) {
  try {
    $cacheFileName = Get-ObjectProperty -Object $previousManifest -Name "cache_file" -Default ""
    $previousParseCachePath = if ($cacheFileName) { Join-Path $OutputDir $cacheFileName } else { $legacyParseCachePath }
    if (-not (Test-Path -LiteralPath $previousParseCachePath)) { $previousParseCachePath = $legacyParseCachePath }
    foreach ($item in @(Import-ParseCache -Path $previousParseCachePath)) {
      if ($item.skill_md) {
        $previousCacheByPath[[string]$item.skill_md] = $item
      }
    }
  }
  catch {
    $previousCacheByPath = @{}
  }
}

$recursiveSkillFiles = Get-ChildItem -LiteralPath $skillsRootResolved -Filter "SKILL.md" -Recurse -Force -ErrorAction SilentlyContinue
$topLevelSkillFiles = Get-ChildItem -LiteralPath $skillsRootResolved -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  $skillPath = Join-Path $_.FullName "SKILL.md"
  if (Test-Path -LiteralPath $skillPath) {
    Get-Item -LiteralPath $skillPath
  }
}
$selfSkillPath = (Resolve-Path -LiteralPath (Join-Path $skillDir "SKILL.md")).Path
$skillFiles = @(@($recursiveSkillFiles) + @($topLevelSkillFiles)) |
  Where-Object { (Resolve-Path -LiteralPath $_.FullName).Path -ne $selfSkillPath } |
  Sort-Object FullName -Unique
$rawItems = @()

foreach ($file in $skillFiles) {
  $cached = $null
  if ($previousManifestByPath.ContainsKey($file.FullName)) {
    $previousEntry = $previousManifestByPath[$file.FullName]
    if (
      ([int64]$previousEntry.file_length -eq [int64]$file.Length) -and
      ([int64]$previousEntry.last_write_ticks -eq [int64]$file.LastWriteTime.Ticks) -and
      $previousCacheByPath.ContainsKey($file.FullName)
    ) {
      $cached = $previousCacheByPath[$file.FullName]
    }
  }

  if ($cached) {
    $rawItems += $cached
    continue
  }

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
    file_length = $file.Length
    last_write_time = $file.LastWriteTime.ToString("s")
    last_write_ticks = $file.LastWriteTime.Ticks
  }
}

$manifestFiles = @($rawItems | ForEach-Object {
  [pscustomobject]@{
    skill_md = $_.skill_md
    relative_path = $_.relative_path
    canonical_name = $_.canonical_name
    origin = $_.origin
    file_length = $_.file_length
    last_write_ticks = $_.last_write_ticks
    content_hash = $_.content_hash
  }
})

$manifest = [pscustomobject]@{
  generated_at = (Get-Date).ToString("s")
  output_schema_version = $OutputSchemaVersion
  parser_schema_version = $ParserSchemaVersion
  rules_schema_version = $RulesSchemaVersion
  skills_root = $skillsRootResolved
  cache_file = "parsed-skills-cache.ndjson"
  total = $manifestFiles.Count
  files = $manifestFiles
}
$manifest | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Export-ParseCache -Items $rawItems -Path $parseCachePath
if ((Test-Path -LiteralPath $legacyParseCachePath) -and ($legacyParseCachePath -ne $parseCachePath)) {
  Remove-Item -LiteralPath $legacyParseCachePath -Force
}

$items = @()
$duplicateGroups = @()

$rawItems | Group-Object canonical_name | ForEach-Object {
  $nameGroup = @($_.Group)
  $nameRepresentative = $nameGroup | Sort-Object origin_rank, setup_rank, @{ Expression = "last_write_ticks"; Descending = $true } | Select-Object -First 1
  $nameSourcePaths = Join-UniqueValues -Values ($nameGroup | ForEach-Object { $_.relative_path })
  $nameSourceOrigins = Join-UniqueValues -Values ($nameGroup | ForEach-Object { $_.origin })
  $nameContentHashes = Join-UniqueValues -Values ($nameGroup | ForEach-Object { $_.content_hash })
  $contentGroups = @($nameGroup | Group-Object content_hash | Sort-Object Name)
  $variantCount = $contentGroups.Count

  if ($nameGroup.Count -gt 1) {
    $duplicateGroups += [pscustomobject]@{
      name = $nameRepresentative.name
      canonical_name = $nameRepresentative.canonical_name
      duplicate_count = $nameGroup.Count
      distinct_content_count = $variantCount
      source_origins = $nameSourceOrigins
      source_paths = $nameSourcePaths
    }
  }

  $variantIndex = 0
  foreach ($contentGroupInfo in $contentGroups) {
    $variantIndex++
    $group = @($contentGroupInfo.Group)
    $representative = $group | Sort-Object origin_rank, setup_rank, @{ Expression = "last_write_ticks"; Descending = $true } | Select-Object -First 1

    $sourcePaths = Join-UniqueValues -Values ($group | ForEach-Object { $_.relative_path })
    $sourceSkillFiles = Join-UniqueValues -Values ($group | ForEach-Object { $_.skill_md })
    $sourceOrigins = Join-UniqueValues -Values ($group | ForEach-Object { $_.origin })
    $domains = Join-UniqueValues -Values ($group | ForEach-Object { $_.domain })
    $domainDetails = Join-UniqueValues -Values ($group | ForEach-Object { $_.domain_detail })
    $taskTypes = Join-UniqueValues -Values ($group | ForEach-Object { $_.task_type })
    $outputTypes = Join-UniqueValues -Values ($group | ForEach-Object { $_.output_type })
    $contentHash = $representative.content_hash
    $variantId = $representative.canonical_name + ":" + $contentHash.Substring(0, 12)

    $dedupeStatus = "unique"
    if ($variantCount -gt 1) { $dedupeStatus = "variant" }
    elseif ($group.Count -gt 1) { $dedupeStatus = "merged" }

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
      same_name_source_paths = $nameSourcePaths
      duplicate_count = $group.Count
      duplicate_name_count = $nameGroup.Count
      distinct_content_count = $variantCount
      variant_id = $variantId
      variant_index = $variantIndex
      variant_count = $variantCount
      dedupe_status = $dedupeStatus
      domain = $domains
      primary_domain = Get-PrimaryDomain -Details $domainDetails -Domains $domains
      domain_detail = $domainDetails
      task_type = $taskTypes
      output_type = $outputTypes
      setup_level = $representative.setup_level
      status = "active"
      description = $representative.description
      short_description = $representative.short_description
      content_hashes = @($contentHash)
      same_name_content_hashes = $nameContentHashes
      last_write_time = $representative.last_write_time
    }
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
$shortlistsDir = Join-Path $OutputDir "shortlists"
$primaryShortlistsDir = Join-Path $shortlistsDir "primary-domain"
$detailShortlistsDir = Join-Path $shortlistsDir "domain-detail"
$taskShortlistsDir = Join-Path $shortlistsDir "task-type"

$outputRoot = (Resolve-Path -LiteralPath $OutputDir).Path
foreach ($generatedDir in @($routesDir, $shortlistsDir)) {
  if (Test-Path -LiteralPath $generatedDir) {
    $resolvedGeneratedDir = (Resolve-Path -LiteralPath $generatedDir).Path
    if ($resolvedGeneratedDir.StartsWith($outputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
      Remove-Item -LiteralPath $resolvedGeneratedDir -Recurse -Force
    }
  }
}

if ($IncludeFullRoutes) {
  New-Item -ItemType Directory -Force -Path $primaryRoutesDir, $detailRoutesDir, $taskRoutesDir | Out-Null
}
New-Item -ItemType Directory -Force -Path $primaryShortlistsDir, $detailShortlistsDir, $taskShortlistsDir | Out-Null
$ShortlistLimit = 200
$primaryRouteMap = @{}
$detailRouteMap = @{}
$taskRouteMap = @{}
foreach ($item in $items) {
  Add-RouteMapItem -Map $primaryRouteMap -Key $item.primary_domain -Item $item
  foreach ($detail in @($item.domain_detail)) {
    Add-RouteMapItem -Map $detailRouteMap -Key $detail -Item $item
  }
  foreach ($task in @($item.task_type)) {
    Add-RouteMapItem -Map $taskRouteMap -Key $task -Item $item
  }
}

$routeSummary = [ordered]@{
  generated_at = $index.generated_at
  index_scope = "installing-user-local-skills"
  skill_instance_dir = $skillDir
  skills_root = $skillsRootResolved
  output_schema_version = $OutputSchemaVersion
  parser_schema_version = $ParserSchemaVersion
  rules_schema_version = $RulesSchemaVersion
  raw_total = $rawItems.Count
  total = $items.Count
  duplicate_groups = $duplicateGroups.Count
  duplicates_removed = ($rawItems.Count - $items.Count)
  full_routes_generated = [bool]$IncludeFullRoutes
  route_rule = "Read this summary first, choose one primary_domain/domain_detail/task_type, then read the matching shortlist before reading full route files or candidate SKILL.md files. Full route files are generated only when scan-local-skills.ps1 is run with -IncludeFullRoutes."
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
$routeSummaryLines.Add("- Shortlist limit per route: " + $ShortlistLimit)
$routeSummaryLines.Add("- Full routes generated: " + [bool]$IncludeFullRoutes)
$routeSummaryLines.Add("- Rule: determine category first, then read only the matching shortlist file. Generate full route files only for audits.")
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Primary Domain Routes")
$routeSummaryLines.Add("")
foreach ($routeEntry in $primaryRouteMap.GetEnumerator()) {
  $routeName = [string]$routeEntry.Key
  $routeItems = @($routeEntry.Value)
  $fileName = (Get-SafeFileName -Name $routeName) + ".json"
  $routePath = Join-Path $primaryRoutesDir $fileName
  $entries = @($routeItems | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $relativeRoutePath = ""
  if ($IncludeFullRoutes) {
    $routeObject = [pscustomobject]@{
      generated_at = $index.generated_at
      route_type = "primary_domain"
      category = $routeName
      count = $entries.Count
      candidates = $entries
    }
    $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
    $relativeRoutePath = "routes/primary-domain/" + $fileName
  }
  $shortlistPath = Join-Path $primaryShortlistsDir $fileName
  $shortlistEntries = @($entries | Sort-Object @{ Expression = { Get-RoutePriority -Entry $_ }; Descending = $true }, name | Select-Object -First $ShortlistLimit)
  $shortlistObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "primary_domain"
    category = $routeName
    source_count = $entries.Count
    count = $shortlistEntries.Count
    candidates = $shortlistEntries
  }
  $shortlistObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $shortlistPath -Encoding UTF8
  $relativeShortlistPath = "shortlists/primary-domain/" + $fileName
  $routeSummary.primary_domain += [pscustomobject]@{ name = $routeName; count = $routeItems.Count; file = $relativeRoutePath; shortlist_file = $relativeShortlistPath; shortlist_count = $shortlistEntries.Count }
  $routeSummaryLines.Add(('- `{0}`: {1}; route `{2}`; shortlist `{3}` ({4})' -f $routeName, $routeItems.Count, $(if ($relativeRoutePath) { $relativeRoutePath } else { "not generated" }), $relativeShortlistPath, $shortlistEntries.Count))
}
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Domain Detail Routes")
$routeSummaryLines.Add("")
foreach ($detailEntry in $detailRouteMap.GetEnumerator()) {
  $detail = [string]$detailEntry.Key
  $groupItems = @($detailEntry.Value)
  $fileName = (Get-SafeFileName -Name $detail) + ".json"
  $routePath = Join-Path $detailRoutesDir $fileName
  $entries = @($groupItems | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $relativeRoutePath = ""
  if ($IncludeFullRoutes) {
    $routeObject = [pscustomobject]@{
      generated_at = $index.generated_at
      route_type = "domain_detail"
      category = $detail
      count = $entries.Count
      candidates = $entries
    }
    $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
    $relativeRoutePath = "routes/domain-detail/" + $fileName
  }
  $shortlistPath = Join-Path $detailShortlistsDir $fileName
  $shortlistEntries = @($entries | Sort-Object @{ Expression = { Get-RoutePriority -Entry $_ }; Descending = $true }, name | Select-Object -First $ShortlistLimit)
  $shortlistObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "domain_detail"
    category = $detail
    source_count = $entries.Count
    count = $shortlistEntries.Count
    candidates = $shortlistEntries
  }
  $shortlistObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $shortlistPath -Encoding UTF8
  $relativeShortlistPath = "shortlists/domain-detail/" + $fileName
  $routeSummary.domain_detail += [pscustomobject]@{ name = $detail; count = $entries.Count; file = $relativeRoutePath; shortlist_file = $relativeShortlistPath; shortlist_count = $shortlistEntries.Count }
}
$routeSummary.domain_detail = @($routeSummary.domain_detail | Sort-Object @{ Expression = "count"; Descending = $true }, name)
$routeSummary.domain_detail | ForEach-Object {
  $routeSummaryLines.Add(('- `{0}`: {1}; route `{2}`; shortlist `{3}` ({4})' -f $_.name, $_.count, $(if ($_.file) { $_.file } else { "not generated" }), $_.shortlist_file, $_.shortlist_count))
}
$routeSummaryLines.Add("")

$routeSummaryLines.Add("## Task Type Routes")
$routeSummaryLines.Add("")
foreach ($taskEntry in $taskRouteMap.GetEnumerator()) {
  $task = [string]$taskEntry.Key
  $groupItems = @($taskEntry.Value)
  $fileName = (Get-SafeFileName -Name $task) + ".json"
  $routePath = Join-Path $taskRoutesDir $fileName
  $entries = @($groupItems | Sort-Object name | ForEach-Object { New-RouteEntry -Skill $_ })
  $relativeRoutePath = ""
  if ($IncludeFullRoutes) {
    $routeObject = [pscustomobject]@{
      generated_at = $index.generated_at
      route_type = "task_type"
      category = $task
      count = $entries.Count
      candidates = $entries
    }
    $routeObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $routePath -Encoding UTF8
    $relativeRoutePath = "routes/task-type/" + $fileName
  }
  $shortlistPath = Join-Path $taskShortlistsDir $fileName
  $shortlistEntries = @($entries | Sort-Object @{ Expression = { Get-RoutePriority -Entry $_ }; Descending = $true }, name | Select-Object -First $ShortlistLimit)
  $shortlistObject = [pscustomobject]@{
    generated_at = $index.generated_at
    route_type = "task_type"
    category = $task
    source_count = $entries.Count
    count = $shortlistEntries.Count
    candidates = $shortlistEntries
  }
  $shortlistObject | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $shortlistPath -Encoding UTF8
  $relativeShortlistPath = "shortlists/task-type/" + $fileName
  $routeSummary.task_type += [pscustomobject]@{ name = $task; count = $entries.Count; file = $relativeRoutePath; shortlist_file = $relativeShortlistPath; shortlist_count = $shortlistEntries.Count }
}
$routeSummary.task_type = @($routeSummary.task_type | Sort-Object @{ Expression = "count"; Descending = $true }, name)
$routeSummary.task_type | ForEach-Object {
  $routeSummaryLines.Add(('- `{0}`: {1}; route `{2}`; shortlist `{3}` ({4})' -f $_.name, $_.count, $(if ($_.file) { $_.file } else { "not generated" }), $_.shortlist_file, $_.shortlist_count))
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
  IndexScope = "installing-user-local-skills"
  SkillInstanceDir = $skillDir
  SkillsRoot = $skillsRootResolved
  OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
  OutputSchemaVersion = $OutputSchemaVersion
  ParserSchemaVersion = $ParserSchemaVersion
  RulesSchemaVersion = $RulesSchemaVersion
  RawTotal = $rawItems.Count
  Total = $items.Count
  DuplicateGroups = $duplicateGroups.Count
  DuplicatesRemoved = ($rawItems.Count - $items.Count)
  Index = Join-Path $OutputDir "skills-index.json"
  Manifest = $manifestPath
  ParseCache = $parseCachePath
  Categories = Join-Path $OutputDir "skills-categories.md"
  RouteSummary = Join-Path $OutputDir "route-summary.json"
  RoutesDir = $routesDir
  ShortlistsDir = $shortlistsDir
}
