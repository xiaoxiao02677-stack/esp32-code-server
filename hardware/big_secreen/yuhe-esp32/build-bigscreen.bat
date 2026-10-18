@echo off
rem ============================================================
rem  build-bigscreen.bat : one-click build for bigscreen-s3
rem  Board: ESP32-S3 + ES8311 audio + ILI9341 2.8" SPI LCD
rem  Usage: double-click, or run from this directory
rem  Toolchain: ESP-IDF v6.1 EIM layout (D:\INSTALL\esp)
rem ============================================================
cd /d "%~dp0"
set "BOARD=bigscreen-s3"

rem ---------- ASCII build path (cmake 4.x crashes 0xC0000409 on non-ASCII paths) ----------
set "LINK=C:\bsfw"
if exist "%LINK%" rmdir "%LINK%" >nul 2>&1
mklink /J "%LINK%" "%~dp0." >nul 2>&1
if not exist "%LINK%\CMakeLists.txt" (
    echo [ERROR] cannot create ASCII junction %LINK% to this dir
    pause
    exit /b 1
)
cd /d "%LINK%"

echo ============================================================
echo   One-click build: %BOARD%
echo ============================================================
echo.

rem ---------- 0. component manager workarounds ----------
rem esp_video 2.5.0 的 esp_h264 依赖带 matches
rem "$CONFIG{ESP_VIDEO_USE_CUSTOMIZED_ESP_H264_VERSION} == False"，
rem esp32s3 构建时该 Kconfig 变量未定义（esp_h264 是 p4-only 依赖），
rem 组件管理器的"新版本检查"（check_for_new_component_versions）求值
rem 该条件抛 MissingKconfigError 导致 configure FATAL。关掉检查即可，
rem 不影响 dependencies.lock 锁定的版本（2026-10-15 经验）。
set IDF_COMPONENT_CHECK_NEW_VERSION=0
set IDF_COMPONENT_SUPPRESS_UNKNOWN_FILE_WARNINGS=1

rem ---------- 1. ESP-IDF environment ----------
rem EIM layout: set toolchain vars directly (proven in P19-R build)
if not exist "D:\INSTALL\esp\v6.1\esp-idf\tools\cmake\project.cmake" (
    echo [ERROR] ESP-IDF v6.1 not found at D:\INSTALL\esp\v6.1\esp-idf
    echo         Fix: set ESP_IDF_PATH^/edit this script to your IDF location
    pause
    exit /b 1
)
set MSYSTEM=
set "IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf"
set "IDF_TOOLS_PATH=D:\INSTALL\esp\tools"
set "IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv"
set "ESP_IDF_VERSION=6.1"
set "PATH=D:\INSTALL\esp\tools\python\v6.1\venv\Scripts;D:\INSTALL\esp\tools\idf-exe\1.0.3;D:\INSTALL\esp\tools\cmake\4.0.3\bin;D:\INSTALL\esp\tools\ninja\1.12.1;D:\INSTALL\esp\tools\xtensa-esp-elf\esp-15.2.0_20251204\xtensa-esp-elf\bin;D:\INSTALL\esp\tools\ccache\4.12.1\ccache-4.12.1-windows-x86_64;D:\INSTALL\Git\cmd;C:\Windows\System32;C:\Windows"
set "PYTHON=D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe"
echo [1/3] ESP-IDF v6.1 environment ready (EIM layout)

rem ---------- 2. build ----------
echo.
echo [2/3] Building %BOARD% ...
echo       command: python scripts/build.py %BOARD%
echo.
"%PYTHON%" scripts/build.py %BOARD%
if errorlevel 1 goto build_fail

rem ---------- 3. done ----------
echo.
echo [3/3] Done.
echo ============================================================
echo   BUILD OK: %BOARD%
echo ============================================================
echo Artifacts:
if exist "build\merged-binary.bin" echo   Merged : build\merged-binary.bin
if exist "build\%BOARD%\merged-binary.bin" echo   Merged : build\%BOARD%\merged-binary.bin
if not exist "build\merged-binary.bin" if not exist "build\%BOARD%\merged-binary.bin" echo   (bins under build\ , or use idf.py flash directly)
echo.
echo Next (flash on COM10):
echo   "%PYTHON%" -m idf_py -p COM10 flash monitor
echo Docs : main\boards\bigscreen-s3\BUILD.md
echo Pins : main\boards\bigscreen-s3\PINOUT.md
echo ============================================================
echo.
pause
exit /b 0

:build_fail
echo.
echo ============================================================
echo   [FAILED] Build error. Check messages above.
echo   Hints:
echo     - board files : main\boards\bigscreen-s3\
echo     - network     : re-run (component download flake)
echo     - cmake 0xC0000409 : non-ASCII path, this script already builds via %LINK%
echo ============================================================
echo.
pause
exit /b 1
