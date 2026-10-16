@echo off
rem ESP32 完整开发工作流
rem 用法: workflow.bat [build|flash|monitor|all]

setlocal enabledelayedexpansion

rem 统一以本脚本所在目录为工作目录，避免从别处双击时找不到子脚本
cd /d "%~dp0"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=all"

echo ========================================
echo   ESP32 开发工作流
echo ========================================
echo.

if "%ACTION%"=="build" goto :build
if "%ACTION%"=="flash" goto :flash
if "%ACTION%"=="monitor" goto :monitor
if "%ACTION%"=="all" goto :all

:build
echo [1/3] 编译固件 lckfb/szpi-esp32s3 ...
call build_lckfb_s3.bat
if errorlevel 1 (
    echo [ERR] 编译失败
    exit /b 1
)
echo [OK] 编译完成
goto :eof

:flash
echo [2/3] 烧录固件...
call yh_flash.bat
if errorlevel 1 (
    echo [ERR] 烧录失败
    exit /b 1
)
echo [OK] 烧录完成
goto :eof

:monitor
echo [3/3] 启动串口监视...
call monitor.bat
goto :eof

:all
echo [1/3] 编译固件 lckfb/szpi-esp32s3 ...
call build_lckfb_s3.bat
if errorlevel 1 (
    echo [ERR] 编译失败
    exit /b 1
)
echo [OK] 编译完成
echo.
echo [2/3] 烧录固件...
call yh_flash.bat
if errorlevel 1 (
    echo [ERR] 烧录失败
    exit /b 1
)
echo [OK] 烧录完成
echo.
echo [3/3] 启动串口监视...
echo 请按 Ctrl+C 退出监视
echo.
call monitor.bat
goto :eof
