[CmdletBinding()]
param(
  [string]$OutputDirectory = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $repositoryRoot "artifacts\images"
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

function Invoke-Docker([string[]]$Arguments) {
  if ($DryRun) {
    Write-Host ("docker " + ($Arguments -join " "))
    return
  }
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker command failed with exit code $LASTEXITCODE."
  }
}

if (-not $DryRun) {
  try {
    & docker info --format "{{.OSType}}" 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon is unavailable." }
  } catch {
    throw "Docker daemon is unavailable. Start Docker Desktop with Linux containers before building."
  }
  $osType = (& docker info --format "{{.OSType}}").Trim()
  if ($osType -ne "linux") {
    throw "Docker must use Linux containers; detected OSTYPE='$osType'."
  }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$commonBackendArgs = @(
  "--build-arg", "DEBIAN_MIRROR=https://mirrors.cloud.tencent.com/debian",
  "--build-arg", "DEBIAN_SECURITY_MIRROR=https://mirrors.cloud.tencent.com/debian-security",
  "--build-arg", "PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/"
)
$commonFrontendArgs = @(
  "--build-arg", "NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/",
  "--build-arg", "VITE_MAP_ENGINE=maplibre"
)

foreach ($architecture in @("amd64", "arm64")) {
  $platform = "linux/$architecture"
  $tag = "offline-$architecture"
  $backendImage = "pygeomodel/backend:$tag"
  $frontendImage = "pygeomodel/frontend:$tag"
  $backendArchive = Join-Path $OutputDirectory "pygeomodel-backend-linux-$architecture.tar"
  $frontendArchive = Join-Path $OutputDirectory "pygeomodel-frontend-linux-$architecture.tar"

  Write-Host "Building $backendImage for $platform"
  Invoke-Docker (@("buildx", "build", "--platform", $platform, "--load", "--tag", $backendImage, "--file", (Join-Path $repositoryRoot "backend/Dockerfile")) + $commonBackendArgs + @($repositoryRoot))
  Invoke-Docker @("save", "--output", $backendArchive, $backendImage)

  Write-Host "Building $frontendImage for $platform"
  Invoke-Docker (@("buildx", "build", "--platform", $platform, "--load", "--tag", $frontendImage, "--file", (Join-Path $repositoryRoot "frontend/Dockerfile")) + $commonFrontendArgs + @($repositoryRoot))
  Invoke-Docker @("save", "--output", $frontendArchive, $frontendImage)

  if (-not $DryRun) {
    $backendArchitecture = (& docker image inspect $backendImage --format "{{.Architecture}}").Trim()
    $frontendArchitecture = (& docker image inspect $frontendImage --format "{{.Architecture}}").Trim()
    if ($backendArchitecture -ne $architecture -or $frontendArchitecture -ne $architecture) {
      throw "Architecture verification failed for ${architecture}: backend=$backendArchitecture frontend=$frontendArchitecture."
    }
  }
}

Write-Host "Offline image archives written to $OutputDirectory"
