@echo off
REM ESP32-S3 WiFi 配网脚本 (Windows)
REM 用法: provision.bat "WiFi名" "密码"

set "WIFI_SSID=%~1"
set "WIFI_PASSWORD=%~2"

if "%WIFI_SSID%"=="" (
    echo 用法: provision.bat ^<WiFi名^> ^<密码^>
    echo 示例: provision.bat MyWiFi 12345678
    pause
    exit /b 1
)

echo ========================================
echo ESP32-S3 WiFi 配网工具
echo ========================================
echo 目标 WiFi: %WIFI_SSID%
echo 目标密码: %WIFI_PASSWORD%
echo.
echo 请确保:
echo   1. ESP32 已通电并显示 XZS3-XXXX AP
echo   2. 手机/电脑已连上 XZS3-XXXX
echo   3. 按任意键继续...
echo ========================================
pause >nul

python "%~dp0wifi_provision.py" --ssid "%WIFI_SSID%" --password "%WIFI_PASSWORD%"
