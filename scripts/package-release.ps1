param(
  [Parameter(Mandatory = $true)]
  [string]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$dist = Join-Path $repoRoot "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null

$zip = Join-Path $dist ("skill-selection-assistant-{0}.zip" -f $Version)
if (Test-Path -LiteralPath $zip) {
  Remove-Item -LiteralPath $zip -Force
}

$temp = Join-Path $env:TEMP ("skill-selection-assistant-{0}-{1}" -f $Version, [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temp | Out-Null

try {
  $topLevelItems = @(
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "INSTALLATION_BEHAVIOR.md",
    "SELF_GROWTH.md",
    "tests",
    ".github",
    "scripts"
  )

  foreach ($item in $topLevelItems) {
    $src = Join-Path $repoRoot $item
    if (Test-Path -LiteralPath $src) {
      Copy-Item -LiteralPath $src -Destination $temp -Recurse -Force
    }
  }

  $skillSrc = Join-Path $repoRoot "skill-selection-assistant"
  $skillDest = Join-Path $temp "skill-selection-assistant"
  New-Item -ItemType Directory -Force -Path $skillDest | Out-Null
  foreach ($item in @("SKILL.md", "agents", "rules", "scripts")) {
    $src = Join-Path $skillSrc $item
    if (Test-Path -LiteralPath $src) {
      Copy-Item -LiteralPath $src -Destination $skillDest -Recurse -Force
    }
  }

  Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $zip -Force

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
  try {
    $forbidden = @($archive.Entries | Where-Object {
      $_.FullName -like "*skill-index*" -or
      $_.FullName -like "dist/*"
    })
    if ($forbidden.Count -gt 0) {
      throw "Release package contains forbidden local artifacts: " + (($forbidden | Select-Object -First 5 -ExpandProperty FullName) -join ", ")
    }
  }
  finally {
    $archive.Dispose()
  }

  $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $zip
  [pscustomobject]@{
    Version = $Version
    Zip = $zip
    Length = (Get-Item -LiteralPath $zip).Length
    SHA256 = $hash.Hash
  } | ConvertTo-Json -Depth 4
}
finally {
  if (Test-Path -LiteralPath $temp) {
    Remove-Item -LiteralPath $temp -Recurse -Force
  }
}
