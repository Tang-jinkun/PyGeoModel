[CmdletBinding()]
param(
  [string]$OutputDirectory = "",
  [string]$ImageDirectory = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
if (-not $ImageDirectory) { $ImageDirectory = Join-Path $repositoryRoot "artifacts\images" }
$ImageDirectory = [IO.Path]::GetFullPath($ImageDirectory)
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $repositoryRoot ("artifacts\pygeomodel-offline-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

if (Test-Path -LiteralPath $OutputDirectory) {
  throw "Output directory already exists; choose a new path: $OutputDirectory"
}
if (-not (Test-Path -LiteralPath $ImageDirectory)) {
  throw "Image directory not found: $ImageDirectory. Build the offline image archives first."
}

$requiredImages = @(
  "pygeomodel-backend-linux-amd64.tar",
  "pygeomodel-frontend-linux-amd64.tar",
  "pygeomodel-backend-linux-arm64.tar",
  "pygeomodel-frontend-linux-arm64.tar"
)
foreach ($imageName in $requiredImages) {
  if (-not (Test-Path -LiteralPath (Join-Path $ImageDirectory $imageName))) {
    throw "Required image archive not found: $(Join-Path $ImageDirectory $imageName)"
  }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

function Copy-Tree([string]$RelativeSource, [string]$RelativeDestination, [string[]]$ExcludedPattern = @()) {
  $source = Join-Path $repositoryRoot $RelativeSource
  if (-not (Test-Path -LiteralPath $source)) { throw "Required source path not found: $source" }
  $destination = Join-Path $OutputDirectory $RelativeDestination
  New-Item -ItemType Directory -Force -Path $destination | Out-Null
  $sourceRoot = [IO.Path]::GetFullPath($source).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
  foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -Recurse -File) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $normalized = $relative.Replace("\", "/")
    $excluded = $false
    foreach ($pattern in $ExcludedPattern) {
      if ($normalized -like $pattern) { $excluded = $true; break }
    }
    if ($excluded) { continue }
    $target = Join-Path $destination $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target
  }
}

function Copy-RootFile([string]$RelativePath) {
  $source = Join-Path $repositoryRoot $RelativePath
  if (-not (Test-Path -LiteralPath $source)) { throw "Required root file not found: $source" }
  $target = Join-Path $OutputDirectory $RelativePath
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  Copy-Item -LiteralPath $source -Destination $target
}

foreach ($rootFile in @(".dockerignore", ".env.example", "docker-compose.yml", "README.md")) {
  Copy-RootFile $rootFile
}

Copy-Tree "backend" "backend" @("*__pycache__*", "*pytest_cache*", ".venv/*", "venv/*", "*.log", "*.local.*")
Copy-Tree "frontend" "frontend" @("dist/*", ".vite/*", "vite.local.*", "*.local.log", "*node_modules/.cache*", "*__pycache__*", "*pytest_cache*", "*.vite*")
Copy-Tree "scripts" "scripts" @("*__pycache__*", "*.log", "*.local.*")
Copy-Tree "deploy" "deploy" @("*__pycache__*", "*pytest_cache*", "*.log", "*.local.*")
Copy-Tree "docs" "docs" @("superpowers/*", "*.log", "*.local.*")

$demoDem = "data/dem/dem_20260713_080113_884937cf"
Copy-Tree $demoDem "data/dem/dem_20260713_080113_884937cf"
Copy-RootFile "data/dem/river_network_demo.tif"
Copy-Tree "data/demo-scenarios" "data/demo-scenarios"
foreach ($runtimeDirectory in @("data/tasks", "data/outputs", "data/uploads")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $OutputDirectory $runtimeDirectory) | Out-Null
}

New-Item -ItemType Directory -Force -Path (Join-Path $OutputDirectory "images") | Out-Null
foreach ($imageName in $requiredImages) {
  Copy-Item -LiteralPath (Join-Path $ImageDirectory $imageName) -Destination (Join-Path $OutputDirectory "images")
}

$manifestPath = Join-Path $OutputDirectory "MANIFEST.txt"
$manifestLines = @(
  "PyGeoModel offline delivery",
  "Generated: $(Get-Date -Format o)",
  "Targets: linux/amd64 (Windows x64 Docker Desktop Linux containers), linux/arm64 (ARM Linux)",
  "",
  "Included:",
  "- backend and frontend source code",
  "- frontend/node_modules dependency snapshot",
  "- demo DEM, COG, scenarios, and empty runtime data directories",
  "- four Docker-loadable image archives",
  "- offline deployment scripts and documentation",
  "",
  "Excluded:",
  "- .git, .tools, PyGeoModel-前端重设计, logs, caches, frontend/dist, historical tasks/outputs"
)
[IO.File]::WriteAllLines($manifestPath, $manifestLines, [Text.UTF8Encoding]::new($false))

$checksumPath = Join-Path $OutputDirectory "SHA256SUMS"
$checksumLines = foreach ($file in Get-ChildItem -LiteralPath $OutputDirectory -Recurse -File | Where-Object { $_.FullName -ne $checksumPath } | Sort-Object FullName) {
  $relative = $file.FullName.Substring($OutputDirectory.Length).TrimStart([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar).Replace("\", "/")
  $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  "$hash  $relative"
}
[IO.File]::WriteAllLines($checksumPath, $checksumLines, [Text.UTF8Encoding]::new($false))

$fileCount = (Get-ChildItem -LiteralPath $OutputDirectory -Recurse -File | Measure-Object).Count
$sizeBytes = (Get-ChildItem -LiteralPath $OutputDirectory -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host "Offline delivery created: $OutputDirectory"
Write-Host "Files: $fileCount; bytes: $sizeBytes"
