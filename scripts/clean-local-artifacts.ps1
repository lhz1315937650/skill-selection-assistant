param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$targets = @(
  (Join-Path $repoRoot "dist"),
  (Join-Path $repoRoot "skill-selection-assistant\.skill-index")
)

$cacheDirectoryNames = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
$repoResolved = [IO.Path]::GetFullPath($repoRoot.Path)
$targets += @(
  Get-ChildItem -LiteralPath $repoRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -in $cacheDirectoryNames -and
      $_.FullName.StartsWith($repoResolved, [System.StringComparison]::OrdinalIgnoreCase)
    } |
    ForEach-Object { $_.FullName }
)
$targets = @($targets | Sort-Object -Unique)

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

$cacheFiles = @(
  Get-ChildItem -LiteralPath $repoRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
      $_.FullName.StartsWith($repoResolved, [System.StringComparison]::OrdinalIgnoreCase) -and
      ($_.Name -like "*.pyc" -or $_.Name -eq ".coverage" -or $_.Name -eq "coverage.xml")
    }
)
foreach ($file in $cacheFiles) {
  $removed += $file.FullName
  if (-not $WhatIf) {
    Remove-Item -LiteralPath $file.FullName -Force
  }
}

[pscustomobject]@{
  Repository = $repoRoot.Path
  WhatIf = [bool]$WhatIf
  Removed = $removed
} | ConvertTo-Json -Depth 4
