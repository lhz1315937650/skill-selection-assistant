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
  if ($hits.Count -eq 0) {
    $hits += $Fallback
  }
  return $hits
}

$domainRules = @{
  writing = "write|writing|article|blog|copy|markdown|translate|proofread"
  research = "research|paper|academic|literature|citation"
  coding = "code|coding|test|debug|frontend|api|mcp|git"
  data = "data|excel|xlsx|stata|python|analysis"
  design = "image|design|diagram|cover|comic|visual"
  documents = "pdf|docx|pptx|document|slide"
  publishing = "post|publish|wechat|weibo|xhs|twitter"
  safety = "security|guardrail|risk"
}

$taskRules = @{
  summarize = "summar"
  review = "review|audit"
  generate = "generate|create|write"
  transform = "transform|convert|format"
  "test-debug" = "test|debug"
  extract = "extract|parse"
  publish = "publish|post"
  plan = "plan|strategy"
  analyze = "analy"
}

$outputRules = @{
  markdown = "markdown|md"
  image = "image|png|jpg"
  pptx = "pptx|slide|deck|ppt"
  docx = "docx|word"
  xlsx = "xlsx|excel|spreadsheet"
  html = "html|web"
  code = "code|script"
  report = "report"
}

function Get-SetupLevel {
  param([string]$Text)
  if ($Text -match "api key|token|account|login|oauth") { return "account" }
  if ($Text -match "install|download|npm|pip|python|node|browser") { return "local-runtime" }
  if ($Text -match "web|http|github|network") { return "network" }
  return "none"
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
$items = @()

foreach ($file in $skillFiles) {
  $dir = Split-Path -Parent $file.FullName
  $dirItem = Get-Item -LiteralPath $dir
  $relative = $dir.Substring($skillsRootResolved.Length).TrimStart([char[]]@('\', '/'))
  $lines = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -ErrorAction SilentlyContinue
  $preview = ($lines | Select-Object -First 80) -join "`n"
  $name = Get-FrontmatterValue -Lines $lines -Key "name"
  if (-not $name) { $name = Split-Path -Leaf $dir }
  $description = Get-FrontmatterValue -Lines $lines -Key "description"
  $short = Get-FrontmatterValue -Lines $lines -Key "short-description"
  $combined = "$name`n$description`n$short`n$preview".ToLowerInvariant()

  $origin = "user-local"
  if ($relative.StartsWith(".system")) { $origin = "official-system" }
  elseif ($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { $origin = "linked-external" }
  elseif ($name -match "^baoyu-" -or $relative -match "^baoyu-") { $origin = "installed-topic" }

  $items += [pscustomobject]@{
    name = $name
    folder = Split-Path -Leaf $dir
    relative_path = $relative
    skill_md = $file.FullName
    origin = $origin
    domain = @(Get-CategoryMatches -Text $combined -Rules $domainRules -Fallback "general")
    task_type = @(Get-CategoryMatches -Text $combined -Rules $taskRules -Fallback "workflow")
    output_type = @(Get-CategoryMatches -Text $combined -Rules $outputRules -Fallback "workflow")
    setup_level = Get-SetupLevel -Text $combined
    status = "active"
    description = $description
    short_description = $short
    last_write_time = $file.LastWriteTime.ToString("s")
  }
}

$index = [pscustomobject]@{
  generated_at = (Get-Date).ToString("s")
  skills_root = $skillsRootResolved
  total = $items.Count
  skills = $items
}

$index | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutputDir "skills-index.json") -Encoding UTF8

$categoryLines = New-Object System.Collections.Generic.List[string]
$categoryLines.Add("# Local Skills Category Index")
$categoryLines.Add("")
$categoryLines.Add("- Generated: " + $index.generated_at)
$categoryLines.Add('- Skills root: `' + $skillsRootResolved + '`')
$categoryLines.Add("- Total skills: " + $items.Count)
$categoryLines.Add("")

$items | Group-Object origin | Sort-Object Name | ForEach-Object {
  $categoryLines.Add("## Origin: " + $_.Name)
  $categoryLines.Add("")
  $_.Group | Sort-Object name | ForEach-Object {
    $categoryLines.Add('- `' + $_.name + '` | domain: ' + ($_.domain -join ', ') + ' | task: ' + ($_.task_type -join ', ') + ' | setup: ' + $_.setup_level)
  }
  $categoryLines.Add("")
}

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
  Total = $items.Count
  Index = Join-Path $OutputDir "skills-index.json"
  Categories = Join-Path $OutputDir "skills-categories.md"
}
