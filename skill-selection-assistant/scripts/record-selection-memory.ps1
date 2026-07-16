param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [ValidateSet("selected", "missed", "rejected", "setup-failed", "new-skill-needed", "overlap-note")]
  [string]$Outcome = "selected",

  [string]$SelectedSkill = "",
  [string]$RouteType = "",
  [string]$Category = "",
  [string]$Notes = "",
  [string]$IndexDir = "",
  [switch]$StoreQuery
)

$ErrorActionPreference = "Stop"

$pythonScript = Join-Path $PSScriptRoot "record-selection-memory.py"
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python -and (Test-Path -LiteralPath $pythonScript)) {
  $arguments = @(
    $pythonScript,
    "--query", $Query,
    "--outcome", $Outcome
  )
  if ($SelectedSkill) { $arguments += @("--selected-skill", $SelectedSkill) }
  if ($RouteType) { $arguments += @("--route-type", $RouteType) }
  if ($Category) { $arguments += @("--category", $Category) }
  if ($Notes) { $arguments += @("--notes", $Notes) }
  if ($IndexDir) { $arguments += @("--index-dir", $IndexDir) }
  if ($StoreQuery) { $arguments += "--store-query" }
  & $python.Source @arguments
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  return
}

function Get-ShortText {
  param([string]$Text, [int]$MaxLength = 300)
  if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
  $flat = (($Text -replace "\s+", " ").Trim())
  $safe = $flat.Replace('`', 'ˋ')
  if ($safe.Length -le $MaxLength) { return $safe }
  return $safe.Substring(0, $MaxLength).Trim() + "..."
}

if (-not $IndexDir) {
  $skillDir = Split-Path -Parent $PSScriptRoot
  $IndexDir = Join-Path $skillDir ".skill-index"
}

New-Item -ItemType Directory -Force -Path $IndexDir | Out-Null
$memoryPath = Join-Path $IndexDir "selection-memory.md"

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
    "## Category Improvements",
    "",
    "## Selection Log"
  ) | Set-Content -LiteralPath $memoryPath -Encoding UTF8
}

$existing = Get-Content -LiteralPath $memoryPath -Raw -Encoding UTF8
if ($existing -notmatch "(?m)^## Selection Log\s*$") {
  Add-Content -LiteralPath $memoryPath -Encoding UTF8 -Value @("", "## Selection Log")
}

$timestamp = (Get-Date).ToString("s")
$entry = New-Object System.Collections.Generic.List[string]
$entry.Add("")
$entry.Add("### $timestamp")
$entry.Add("")
$entry.Add(('- outcome: `{0}`' -f $Outcome))
$entry.Add("- query: " + $(if ($StoreQuery) { Get-ShortText -Text $Query } else { "[not stored]" }))
if (-not [string]::IsNullOrWhiteSpace($SelectedSkill)) {
  $entry.Add(('- selected_skill: `{0}`' -f (Get-ShortText -Text $SelectedSkill)))
}
if (-not [string]::IsNullOrWhiteSpace($RouteType) -or -not [string]::IsNullOrWhiteSpace($Category)) {
  $entry.Add(('- route: `{0}` / `{1}`' -f (Get-ShortText -Text $RouteType), (Get-ShortText -Text $Category)))
}
if (-not [string]::IsNullOrWhiteSpace($Notes)) {
  $entry.Add("- notes: " + (Get-ShortText -Text $Notes))
}

Add-Content -LiteralPath $memoryPath -Encoding UTF8 -Value $entry

[pscustomobject]@{
  status = "recorded"
  outcome = $Outcome
  selected_skill = $SelectedSkill
  route_type = $RouteType
  category = $Category
  query_stored = [bool]$StoreQuery
  memory = $memoryPath
} | ConvertTo-Json -Depth 4
