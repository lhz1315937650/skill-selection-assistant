param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$targets = @(
  (Join-Path $repoRoot "dist"),
  (Join-Path $repoRoot "skill-selection-assistant\.skill-index")
)

$removed = @()
foreach ($target in $targets) {
  if (-not (Test-Path -LiteralPath $target)) { continue }
  $resolved = (Resolve-Path -LiteralPath $target).Path
  if (-not $resolved.StartsWith($repoRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean path outside repository: $resolved"
  }

  $removed += $resolved
  if (-not $WhatIf) {
    Remove-Item -LiteralPath $resolved -Recurse -Force
  }
}

[pscustomobject]@{
  Repository = $repoRoot.Path
  WhatIf = [bool]$WhatIf
  Removed = $removed
} | ConvertTo-Json -Depth 4
