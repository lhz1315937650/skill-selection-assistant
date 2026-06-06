param(
  [Parameter(Mandatory = $true)]
  [string]$Query,

  [ValidateSet("selected", "missed", "rejected", "setup-failed", "new-skill-needed", "overlap-note")]
  [string]$Outcome = "selected",

  [string]$SelectedSkill = "",
  [string]$RouteType = "",
  [string]$Category = "",
  [string]$Notes = "",
  [string]$IndexDir = ""
)

$ErrorActionPreference = "Stop"

function Get-ShortText {
  param([string]$Text, [int]$MaxLength = 300)
  if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
  $flat = (($Text -replace "\s+", " ").Trim())
  if ($flat.Length -le $MaxLength) { return $flat }
  return $flat.Substring(0, $MaxLength).Trim() + "..."
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
$entry.Add("- query: " + (Get-ShortText -Text $Query))
if (-not [string]::IsNullOrWhiteSpace($SelectedSkill)) {
  $entry.Add(('- selected_skill: `{0}`' -f $SelectedSkill))
}
if (-not [string]::IsNullOrWhiteSpace($RouteType) -or -not [string]::IsNullOrWhiteSpace($Category)) {
  $entry.Add(('- route: `{0}` / `{1}`' -f $RouteType, $Category))
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
  memory = $memoryPath
} | ConvertTo-Json -Depth 4
