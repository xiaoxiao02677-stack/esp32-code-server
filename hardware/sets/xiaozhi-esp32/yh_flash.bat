@echo off
rem YH firmware flash script - auto detect COM port
rem 摄像头板 yuhe/cam (屿禾 Yuhe AI Camera), Flash 16MB DIO 80MHz
setlocal enabledelayedexpansion

rem ---- 工程路径 (script self-locating: works for both this copy and upstream) ----
rem 原值把 PROJECT_DIR 硬编码到上游工作区 small_screen_camera\xiaozhi-esp32，
rem 在 sets 副本里运行会烧错 build，故改为取脚本自身所在目录。
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "BUILD_DIR=%PROJECT_DIR%\build"

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
rem wbem 必须带上：wmic.exe 只在 System32\wbem 下，缺了自动探测 COM 口会失败
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\wbem;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"

if not exist "%BUILD_DIR%" (
    echo [YH-FLASH][ERR] build 目录不存在: %BUILD_DIR%
    echo [YH-FLASH][ERR] 请先运行 build_yuhe_cam.bat 编译
    exit /b 1
)

rem ---- 判断 flash_args 是否含 assets ----
rem 本项目硬约束: assets 分区 0x800000 必须全量烧录, 之后 OTA 只刷 app 分区
findstr /i /c:"generated_assets" "%BUILD_DIR%\flash_args" >nul 2>&1
if errorlevel 1 (
    echo [YH-FLASH] flash_args 未包含 assets, 改用显式全量烧录命令...
    cd /d "%PROJECT_DIR%"
    python -m esptool --chip esp32s3 -p %PORT% -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0xd000 build\ota_data_initial.bin 0x20000 build\xiaozhi.bin 0x800000 build\generated_assets.bin
    goto :done
)

rem ---- flash_args 由 idf.py 生成在 build\ 目录, esptool 按当前目录解析 @flash_args ----
cd /d "%BUILD_DIR%"
python -m esptool --chip esp32s3 -p %PORT% -b 460800 --before default-reset --after hard-reset write-flash "@flash_args" --flash-mode dio --flash-size 16MB --flash-freq 80m

:done
if errorlevel 1 (
    echo [YH-FLASH][ERR] flash failed on %PORT%
    exit /b 1
)
echo [YH-FLASH] done. device rebooted. watch serial for [YH] logs.
