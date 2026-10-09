@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==== 1/4  Preparing tools ====
python -m pip install --upgrade pyinstaller
if exist requirements.txt python -m pip install -r requirements.txt

echo ==== 2/4  Cleaning old build ====
if exist build rmdir /s /q build
if exist dist\LabSystem rmdir /s /q dist\LabSystem
if exist build_tmp rmdir /s /q build_tmp

echo ==== 3/4  Staging data folders (without customer uploads) ====
mkdir build_tmp
set ADD=
for %%D in (templates icon fonts) do (
    if exist "%%D" set ADD=!ADD! --add-data "%%D;%%D"
)
if exist static (
    robocopy "static" "build_tmp\static" /E /XD uploads whatsapp_pdfs >nul
    set ADD=!ADD! --add-data "build_tmp\static;static"
)

echo ==== 4/4  Building LabSystem.exe with PyInstaller ====
python -m PyInstaller --noconfirm --clean --onedir --name LabSystem --icon "icon\lab-icon.ico" !ADD! app.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED - read the errors above.
    pause
    exit /b 1
)

rmdir /s /q build_tmp
if exist VERSION copy /y VERSION dist\LabSystem\VERSION >nul
echo.
echo Build OK: dist\LabSystem\LabSystem.exe
echo Now open installer.iss in Inno Setup and press Ctrl+F9 (Compile).
echo Output: installer_output\LabSystem_Setup.exe
pause
