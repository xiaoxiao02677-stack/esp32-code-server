@echo off
rem YH firmware flash script - auto detect COM port
setlocal enabledelayedexpansion

set "PORT=%~1"

rem ---- 未传参则自动探测 CP210x / CH340 / USB JTAG 串口 ----
if "%PORT%"=="" (
    echo [YH-FLASH] auto-detecting COM port...
    for /f "tokens=4" %%p in ('wmic path Win32_SerialPort where "Caption like '%%Silicon Labs%%' or Caption like '%%CH340%%' or Caption like '%%USB Serial%%' or Caption like '%%JTAG%%'" get Caption^,DeviceID /format:list ^| find "DeviceID="') do (
        set "PORT=%%p"
    )
)

if "%PORT%"=="" (
    echo [YH-FLASH][ERR] no COM port found. Usage: yh_flash.bat COM5
    exit /b 1
)
echo [YH-FLASH] using %PORT%

rem ---- IDF 环境 ----
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
set "PATH=C:\Windows\System32;C:\Windows;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"

cd /d "G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32"

rem ---- 烧录 + 复位 ----
python -m esptool --chip esp32s3 -p %PORT% -b 460800 --before default-reset --after hard-reset write-flash "@flash_args" --flash-mode dio --flash-size 16MB --flash-freq 80m

if errorlevel 1 (
    echo [YH-FLASH][ERR] flash failed on %PORT%
    exit /b 1
)
echo [YH-FLASH] done. device rebooted. watch serial for [YH] logs.
