param([Parameter(Position=0)][string]$Command = 'start', [Parameter(ValueFromRemainingArguments=$true)][string[]]$Extra)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (Test-Path (Join-Path $root 'portable-manifest.json')) {
    $bundled = Join-Path $root 'runtime\python\python.exe'
    if (-not (Test-Path $bundled)) { throw 'Bundled Python is missing. Extract the complete prebuilt package again.' }
    & $bundled -I -B (Join-Path $PSScriptRoot 'portable_launcher.py') $Command @Extra
    exit $LASTEXITCODE
}
$candidates = @()
foreach ($name in @('py', 'python', 'python3')) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found -and $found.Source -notlike '*WindowsApps*') { $candidates += $found.Source }
}
foreach ($registry in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore')) {
    if (Test-Path $registry) {
        foreach ($item in Get-ChildItem $registry) {
            $key = Join-Path $item.PSPath 'InstallPath'
            if (Test-Path $key) {
                $location = (Get-ItemProperty $key).'(default)'
                if ($location -and (Test-Path (Join-Path $location 'python.exe'))) { $candidates += (Join-Path $location 'python.exe') }
            }
        }
    }
}
foreach ($python in ($candidates | Select-Object -Unique)) {
    $prefix = @()
    if ((Split-Path $python -Leaf) -match '^py(?:\.exe)?$') { $prefix = @('-3') }
    & $python @prefix -c 'import sys;sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $python @prefix -B (Join-Path $PSScriptRoot 'bootstrap.py') $Command @Extra
        exit $LASTEXITCODE
    }
}
Write-Error 'Python 3.12+ was not found. Install Python (or the bundled extras/python-installer.exe), then retry.'
exit 1
