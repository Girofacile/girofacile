# Usage: .\scripts\osrm_prepare_windows.ps1 -Source <file.osm.pbf|URL> [-Basename name]
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$Basename,
    [string]$DataDirectory = $(if ($env:OSRM_DATA_DIR) { $env:OSRM_DATA_DIR } else { Join-Path $PSScriptRoot '../data/osrm' }),
    [string]$Image = $(if ($env:OSRM_IMAGE) { $env:OSRM_IMAGE } else { 'ghcr.io/project-osrm/osrm-backend@sha256:8a1b1bc938412f15f9b5b32d794c4ec6bf4a85dfbbabfa0a014b70b187edb53b' })
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Invoke-OsrmDocker {
    param([string[]]$DockerArguments)
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE). Preparation stopped." }
}
$isUrl = $Source -match '^https?://'
$filename = if ($isUrl) { [IO.Path]::GetFileName(([Uri]$Source).AbsolutePath) } else { [IO.Path]::GetFileName($Source) }
if (-not $filename.EndsWith('.osm.pbf', [StringComparison]::OrdinalIgnoreCase)) { throw 'Source must end in .osm.pbf' }
if (-not $Basename) { $Basename = $filename.Substring(0, $filename.Length - 8) }
if ($Basename -cnotmatch '^[a-zA-Z0-9][a-zA-Z0-9._-]*$') { throw 'Invalid dataset basename' }
Get-Command docker -ErrorAction Stop | Out-Null
Invoke-OsrmDocker -DockerArguments @('info') | Out-Null
New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
$dataPath = (Resolve-Path -LiteralPath $DataDirectory).Path
if (Get-ChildItem -LiteralPath $dataPath -Filter "$Basename.osrm*") { throw 'Dataset already exists. Choose a new basename; never overwrite a running dataset.' }
$pbf = Join-Path $dataPath "$Basename.osm.pbf"
if ($isUrl) {
    if ((Test-Path -LiteralPath $pbf) -or (Test-Path -LiteralPath "$pbf.part")) { throw 'Download destination already exists' }
    Invoke-WebRequest -Uri $Source -OutFile "$pbf.part" -UseBasicParsing
    Move-Item -LiteralPath "$pbf.part" -Destination $pbf
} else {
    $original = (Resolve-Path -LiteralPath $Source).Path
    if ($original -ne $pbf) {
        if (Test-Path -LiteralPath $pbf) { throw 'PBF destination already exists' }
        Copy-Item -LiteralPath $original -Destination $pbf
    }
}
if ((Get-Item -LiteralPath $pbf).Length -eq 0) { throw 'Empty PBF' }
$mount = "${dataPath}:/data"
Invoke-OsrmDocker -DockerArguments @('run', '--rm', '--volume', $mount, $Image, 'osrm-extract', '-p', '/opt/car.lua', "/data/$Basename.osm.pbf")
Invoke-OsrmDocker -DockerArguments @('run', '--rm', '--volume', $mount, $Image, 'osrm-partition', "/data/$Basename.osrm")
Invoke-OsrmDocker -DockerArguments @('run', '--rm', '--volume', $mount, $Image, 'osrm-customize', "/data/$Basename.osrm")
# .osrm is a basename; check the actual MLD and shared sidecar files.
foreach ($suffix in @('partition', 'cells', 'cell_metrics', 'mldgr', 'nbg_nodes', 'ebg_nodes', 'edges', 'geometry', 'names', 'properties', 'ramIndex', 'fileIndex')) {
    $output = Join-Path $dataPath "$Basename.osrm.$suffix"
    if (-not (Test-Path -LiteralPath $output -PathType Leaf)) { throw "Missing output: $Basename.osrm.$suffix" }
    if ((Get-Item -LiteralPath $output).Length -eq 0) { throw "Empty output: $Basename.osrm.$suffix" }
}
# Load all sidecars with the serving binary, then exit without starting a server.
Invoke-OsrmDocker -DockerArguments @('run', '--rm', '--volume', "${mount}:ro", $Image, 'osrm-routed', '--algorithm', 'mld', '--trial=1', "/data/$Basename.osrm")
Write-Host "Dataset ready: $pbf"
Write-Host "Set OSRM_DATASET_BASENAME=$Basename and change OSRM_CACHE_VERSION before restarting OSRM."
