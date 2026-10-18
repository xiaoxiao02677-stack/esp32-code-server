@echo off
rem ============================================================
rem  yuhe-esp32 one-click build (board: my-s3-tft)
rem  ESP-IDF v6.1 environment, same as build_my_s3_tft.bat
rem  usage: double-click, or "build_one_click.bat" / "build_one_click.bat clean"
rem ============================================================
setlocal
chcp 65001 >nul

rem ---- project dir = this script's dir, works from any cwd ----
cd /d "%~dp0"

echo ========================================
echo   一键编译 yuhe 固件 (my-s3-tft)
echo   项目目录: %CD%
echo ========================================
echo.

rem ---- optional clean rebuild ----
if /i "%~1"=="clean" (
    echo [CLEAN] 删除 build 目录, 全量重编...
    if exist build rmdir /s /q build
)

rem ---- stale cache check: project moved -> wipe build dir ----
if exist "build\CMakeCache.txt" (
    findstr /i /c:"CMAKE_HOME_DIRECTORY:INTERNAL=%CD:\=/%" build\CMakeCache.txt >nul 2>&1
    if errorlevel 1 (
        echo [CACHE] build 缓存来自旧目录, 自动清理后全量编译...
        rmdir /s /q build
    )
)

rem ---- ESP-IDF v6.1 environment ----
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
rem redirect TEMP away from %USERPROFILE% temp: antivirus intermittently
rem blocks gcc temp file writes (ccXXXXXX.s Permission denied)
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;D:\INSTALL\Git\cmd;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"

call D:\INSTALL\esp\v6.1\esp-idf\export.bat
if errorlevel 1 (
    echo [ERR] ESP-IDF 环境初始化失败
    pause
    exit /b 1
)

echo.
echo [BUILD] 开始编译, 首次/全量编译需几分钟, 请耐心等待...
python scripts\build.py my-s3-tft --name my-s3-tft
if errorlevel 1 (
    echo.
    echo [ERR] 编译失败, 请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo [OK] 编译成功!
echo      固件:   build\yuhe.bin
echo      烧录:   yh_flash.bat ^(自动探测 COM 口^)
pause
