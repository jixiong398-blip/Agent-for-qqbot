# Source-only candidate packaging; no installs, services, commits, tags or upload.
param([Parameter(Mandatory=$true)][string]$Output, [switch]$AcknowledgeUnverified)
$ErrorActionPreference = 'Stop'
if (-not $AcknowledgeUnverified) { throw 'Read MIGRATION.md and explicitly acknowledge this unverified source candidate.' }
$python = Get-Command python -ErrorAction Stop
& $python.Source -B (Join-Path $PSScriptRoot 'scripts\package_source.py') --output $Output --acknowledge-unverified
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Source stage only. Dependency bundles, tests and release/privacy/licence approval are not included.'
Write-Host 'Compile installer sources separately with PackageDir (Inno) or PACKAGE_DIR (NSIS) set to that stage.'
