# Builds dist\CheckProg\ (PyInstaller onedir), dist\CheckProg-<version>-Portable.zip
# and dist\CheckProg-<version>-Setup.exe.
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
# Native tools are checked via $LASTEXITCODE; "Stop" would treat PyInstaller's
# stderr logging as a failure when output is redirected.
# Everything runs in the project's own .venv, never in the global Python.

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-Exit($Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE)" }
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "== Creating .venv"
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { python -m venv .venv }
    Assert-Exit "venv"
}
Write-Host "== Installing dependencies into .venv"
& $Py -m pip install --disable-pip-version-check -q -r requirements-dev.txt
Assert-Exit "pip install"

Write-Host "== Running tests"
& $Py -m pytest -q -p no:cacheprovider
Assert-Exit "Tests"

$Version = (& $Py -c "import checkprog; print(checkprog.__version__)").Trim()
Assert-Exit "Reading version"
Write-Host "== Version $Version"

$Icon = Join-Path $Root "checkprog\icon.ico"
if (-not (Test-Path $Icon)) {
    & $Py packaging\make_icon.py
    Assert-Exit "Icon generation"
}

Write-Host "== PyInstaller"
$Dist = Join-Path $Root "dist"
$AppDir = Join-Path $Dist "CheckProg"
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
& $Py -m PyInstaller --noconfirm --clean --onedir --windowed --name CheckProg `
    --icon $Icon --add-data "$Icon;checkprog" --paths $Root `
    --exclude-module tkinter --exclude-module _tkinter `
    --exclude-module ssl --exclude-module _ssl --exclude-module _hashlib `
    --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick --exclude-module PySide6.QtSql `
    --exclude-module PySide6.QtOpenGL --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtSvg --exclude-module PySide6.QtDBus `
    --distpath $Dist `
    --workpath (Join-Path $Root "build\pyinstaller") `
    --specpath (Join-Path $Root "build") `
    (Join-Path $Root "packaging\launcher.py")
Assert-Exit "PyInstaller"

Write-Host "== Trimming"
# Software OpenGL fallback: Qt Widgets never needs it. Keep only Russian Qt texts.
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $AppDir "_internal\PySide6\opengl32sw.dll")
Get-ChildItem (Join-Path $AppDir "_internal\PySide6\translations") -File |
    Where-Object { $_.Name -notlike "qtbase_ru*.qm" } | Remove-Item -Force

Write-Host "== Portable zip"
$Portable = Join-Path $Dist "CheckProg-Portable"
if (Test-Path $Portable) { Remove-Item -Recurse -Force $Portable }
New-Item -ItemType Directory $Portable | Out-Null
Copy-Item -Recurse $AppDir (Join-Path $Portable "CheckProg")
Copy-Item (Join-Path $Root "README.md") (Join-Path $Portable "CheckProg")
Set-Content -Path (Join-Path $Portable "CheckProg\portable.flag") -Encoding ASCII -Value @(
    "Portable mode marker for CheckProg.",
    "While this file sits next to CheckProg.exe, settings.json and the lists folder",
    "are kept here. Delete it to store settings in %APPDATA%\CheckProg instead.")
$Zip = Join-Path $Dist "CheckProg-$Version-Portable.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $Portable "CheckProg") -DestinationPath $Zip

Write-Host "== Installer"
$IsccCandidates = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($Iscc) {
    & $Iscc "/DAppVersion=$Version" "/O$Dist" (Join-Path $Root "packaging\installer.iss")
    Assert-Exit "Inno Setup"
} else {
    Write-Warning "Inno Setup 6 not found, installer skipped. Install it: winget install JRSoftware.InnoSetup"
}

Write-Host "== Done"
$Size = (Get-ChildItem $AppDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("App folder: {0:N1} MB" -f $Size)
Get-ChildItem $Dist -File | Format-Table Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}}
