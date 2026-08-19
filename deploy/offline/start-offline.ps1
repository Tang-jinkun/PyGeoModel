[CmdletBinding()]
param(
  [string]$ArtifactRoot = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$defaultRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
if (-not $ArtifactRoot) { $ArtifactRoot = $defaultRoot }
$ArtifactRoot = [IO.Path]::GetFullPath($ArtifactRoot)

$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if ($architecture -eq "x64") {
  $architecture = "amd64"
} elseif ($architecture -ne "arm64") {
  throw "Unsupported host architecture '$architecture'. Use Windows/Linux x64 or ARM64."
}

$composeFile = Join-Path $ArtifactRoot "deploy\offline\docker-compose.yml"
$imageDirectory = Join-Path $ArtifactRoot "images"
$archives = @(
  (Join-Path $imageDirectory "pygeomodel-backend-linux-$architecture.tar"),
  (Join-Path $imageDirectory "pygeomodel-frontend-linux-$architecture.tar")
)
if (-not (Test-Path -LiteralPath $composeFile)) { throw "Offline Compose file not found: $composeFile" }
foreach ($archive in $archives) {
  if (-not (Test-Path -LiteralPath $archive)) { throw "Required image archive not found: $archive" }
}

if (-not $DryRun) {
  try {
    & docker info --format "{{.OSType}}" 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon is unavailable." }
  } catch {
    throw "Docker daemon is unavailable. Start Docker Desktop/Engine before starting the offline package."
  }
  $osType = (& docker info --format "{{.OSType}}").Trim()
  if ($osType -ne "linux") { throw "Docker must use Linux containers; detected OSTYPE='$osType'." }
}

foreach ($archive in $archives) {
  if ($DryRun) {
    Write-Host "docker load --input $archive"
  } else {
    Write-Host "Loading $archive"
    & docker load --input $archive
    if ($LASTEXITCODE -ne 0) { throw "Failed to load image archive: $archive" }
  }
}

$env:PYGEOMODEL_IMAGE_TAG = "offline-$architecture"
$env:PYGEOMODEL_OFFLINE = "1"
$composeArguments = @("compose", "-f", $composeFile, "up", "-d", "--no-build")
if ($DryRun) {
  Write-Host ("docker " + ($composeArguments -join " "))
} else {
  Push-Location $ArtifactRoot
  try {
    & docker @composeArguments
    if ($LASTEXITCODE -ne 0) { throw "Offline Compose startup failed." }
  } finally {
    Pop-Location
  }
}

Write-Host "Offline PyGeoModel selected linux/$architecture images."
