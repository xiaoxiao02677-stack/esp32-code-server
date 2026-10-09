@echo off
rem ESP32 串口监视器 - 自动检测COM端口
setlocal enabledelayedexpansion

set "PORT=%~1"

if "%PORT%"=="" (
    echo [MONITOR] auto-detecting COM port...
    for /f "tokens=4" %%p in ('wmic path Win32_SerialPort where "Caption like '%%Silicon Labs%%' or Caption like '%%CH340%%' or Caption like '%%USB Serial%%' or Caption like '%%JTAG%%'" get Caption^,DeviceID /format:list ^| find "DeviceID="') do (
        set "PORT=%%p"
    )
)

if "%PORT%"=="" (
    echo [MONITOR][ERR] no COM port found. Usage: monitor.bat [COM_PORT]
    echo Example: monitor.bat COM3
    exit /b 1
)

echo [MONITOR] connecting to %PORT% at 115200 baud...
echo [MONITOR] Press Ctrl+C to exit
echo.

set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"

cd /d "G:\demo\21_xiaozhi\code\big_secreen\xiaozhi-esp32"
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
idf.py -p %PORT% monitor
