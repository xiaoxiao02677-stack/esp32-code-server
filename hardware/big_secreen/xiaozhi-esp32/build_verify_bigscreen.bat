@echo off
rem ============================================================
rem  build_verify_bigscreen.bat : no-pause build verify for bigscreen-s3
rem  Same env as build-bigscreen.bat but non-interactive (CI-style)
rem ============================================================
cd /d "%~dp0"
set "BOARD=bigscreen-s3"

rem ---------- ASCII build path (cmake 4.x crashes 0xC0000409 on non-ASCII paths) ----------
set "LINK=C:\bsfw_verify"
if exist "%LINK%" rmdir "%LINK%" >nul 2>&1
mklink /J "%LINK%" "%~dp0." >nul 2>&1
if not exist "%LINK%\CMakeLists.txt" (
    echo [ERROR] cannot create ASCII junction %LINK%
    exit /b 1
)
cd /d "%LINK%"

rem ---------- ESP-IDF v6.1 EIM layout ----------
set MSYSTEM=
rem NOTE: esp_video 2.5.0 registry metadata adds a $CONFIG{ESP_VIDEO_USE_CUSTOMIZED_ESP_H264_VERSION}
rem matches clause on its esp_h264 dep; the symbol is defined only in 2.5.0's own Kconfig, so the
rem component-manager new-version check against installed 2.4.1 fails with MissingKconfigError.
rem Fixed at dependency level in main/idf_component.yml: esp_video pinned to ==2.4.1
rem (2026-10-15 verified).
set "IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf"
set "IDF_TOOLS_PATH=D:\INSTALL\esp\tools"
set "IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv"
set "ESP_IDF_VERSION=6.1"
set "PATH=D:\INSTALL\esp\tools\python\v6.1\venv\Scripts;D:\INSTALL\esp\tools\idf-exe\1.0.3;D:\INSTALL\esp\tools\cmake\4.0.3\bin;D:\INSTALL\esp\tools\ninja\1.12.1;D:\INSTALL\esp\tools\xtensa-esp-elf\esp-15.2.0_20251204\xtensa-esp-elf\bin;D:\INSTALL\esp\tools\ccache\4.12.1\ccache-4.12.1-windows-x86_64;D:\INSTALL\Git\cmd;C:\Windows\System32;C:\Windows"
set "PYTHON=D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe"

echo [2/3] Building %BOARD% ...
"%PYTHON%" scripts/build.py %BOARD%
if errorlevel 1 goto build_fail

echo.
echo ============================================================
echo   BUILD OK: %BOARD%
echo ============================================================
exit /b 0

:build_fail
echo.
echo ============================================================
echo   [FAILED] Build error.
echo ============================================================
exit /b 1