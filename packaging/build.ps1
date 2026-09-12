# Builds dist\CheckProg-<version>-Portable.zip and dist\CheckProg-<version>-Setup.exe.
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
# Native tools are checked via $LASTEXITCODE; "Stop" would treat PyInstaller's
# stderr logging as a failure when output is redirected.

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-Exit($Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE)" }
}

Write-Host "== Running tests"
python -m unittest discover -s tests -t .
Assert-Exit "Tests"

$Version = (python -c "import checkprog; print(checkprog.__version__)").Trim()
Assert-Exit "Reading version"
Write-Host "== Version $Version"

$Icon = Join-Path $Root "checkprog\icon.ico"
if (-not (Test-Path $Icon)) {
    python packaging\make_icon.py
    Assert-Exit "Icon generation"
}

Write-Host "== PyInstaller"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CheckProg `
    --icon $Icon --add-data "$Icon;checkprog" --paths $Root `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build\pyinstaller") `
    --specpath (Join-Path $Root "build") `
    (Join-Path $Root "packaging\launcher.py")
Assert-Exit "PyInstaller"

Write-Host "== Portable zip"
$Portable = Join-Path $Root "dist\CheckProg-Portable"
if (Test-Path $Portable) { Remove-Item -Recurse -Force $Portable }
New-Item -ItemType Directory $Portable | Out-Null
Copy-Item (Join-Path $Root "dist\CheckProg.exe") $Portable
Copy-Item (Join-Path $Root "README.md") $Portable
Set-Content -Path (Join-Path $Portable "portable.flag") -Encoding ASCII -Value @(
    "Portable mode marker for CheckProg.",
    "While this file sits next to CheckProg.exe, settings.json and the lists folder",
    "are kept here. Delete it to store settings in %APPDATA%\CheckProg instead.")
$Zip = Join-Path $Root "dist\CheckProg-$Version-Portable.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $Portable "*") -DestinationPath $Zip

Write-Host "== Installer"
$IsccCandidates = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($Iscc) {
    & $Iscc "/DAppVersion=$Version" "/O$(Join-Path $Root 'dist')" (Join-Path $Root "packaging\installer.iss")
    Assert-Exit "Inno Setup"
} else {
    Write-Warning "Inno Setup 6 not found, installer skipped. Install it: winget install JRSoftware.InnoSetup"
}

Write-Host "== Done"
Get-ChildItem (Join-Path $Root "dist") -File | Format-Table Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}}
