@echo off
REM Obscura - Build Script for Windows
REM Creates a standalone executable and installer

echo ============================================
echo Obscura Build Script
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Step 1: Download model if not exists
echo.
echo [1/3] Checking for bundled model...
if not exist "models\gliner_small-v2.1" (
    echo Model not found. Downloading...
    python download_model.py
    if errorlevel 1 (
        echo ERROR: Failed to download model
        pause
        exit /b 1
    )
) else (
    echo Model already exists, skipping download.
)

REM Step 2: Build with PyInstaller
echo.
echo [2/3] Building executable with PyInstaller...
pyinstaller build_config\obscura.spec --noconfirm

if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build complete!
echo ============================================
echo.
echo Executable location: dist\Obscura\Obscura.exe
echo.

REM Step 3: Check for Inno Setup
where iscc >nul 2>&1
if errorlevel 1 (
    echo NOTE: Inno Setup not found in PATH.
    echo To create an installer, install Inno Setup from:
    echo https://jrsoftware.org/isinfo.php
    echo.
    echo Then run: iscc build_config\obscura_installer.iss
) else (
    echo [3/3] Creating installer with Inno Setup...
    iscc build_config\obscura_installer.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup build failed
    ) else (
        echo.
        echo Installer location: dist\installer\Obscura_Setup_v5.0.exe
    )
)

echo.
pause
