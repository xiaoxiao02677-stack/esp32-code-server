@echo off
rem ============================================================
rem  yuhe-esp32 一键编译 (摄像头板: yuhe/cam  屿禾 Yuhe AI Camera)
rem  板型依据: hardware/small_screen_camera/camera硬件信息.md
rem            文档给出的板级标识即 yuhe/cam, 该板源码与文档逐项吻合
rem  编码约定: UTF-8 无 BOM + CRLF, 不加 chcp (与 yh_flash.bat 保持一致)
rem  用法: 双击运行, 或 "build_yuhe_cam.bat" / "build_yuhe_cam.bat clean"
rem ============================================================
setlocal

rem ---- 工程目录 = 本脚本所在目录, 任意 cwd 下均可运行 ----
cd /d "%~dp0"

echo ========================================
echo   一键编译 yuhe 固件
echo   板型: yuhe/cam  屿禾 AI Camera (Wi-Fi)
echo   项目目录: %CD%
echo ========================================
echo.

rem ---- 可选: clean 全量重编 ----
if /i "%~1"=="clean" (
    echo [步骤0] 删除 build 目录, 全量重编...
    if exist build rmdir /s /q build
)

rem ---- 陈旧缓存检查: 工程换过目录时清理 build ----
if exist "build\CMakeCache.txt" (
    findstr /i /c:"CMAKE_HOME_DIRECTORY:INTERNAL=%CD:\=/%" build\CMakeCache.txt >nul 2>&1
    if errorlevel 1 (
        echo [步骤0] build 缓存来自旧目录, 自动清理后全量编译...
        rmdir /s /q build
    )
)

rem ---- ESP-IDF v6.1 环境 ----
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
rem 把 TEMP 重定向出 %USERPROFILE%, 否则杀软会间歇性拦截 gcc 临时文件写入
rem 报 ccXXXXXX.s Permission denied, 导致编译失败
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
rem wbem 必须带上: wmic.exe 只在 System32\wbem 下
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;D:\INSTALL\Git\cmd;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"

echo.
echo [步骤1/3] 正在设置 ESP-IDF v6.1 编译环境...
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
if errorlevel 1 (
    echo [错误] ESP-IDF 环境初始化失败
    pause
    exit /b 1
)
echo [步骤1/3] 环境就绪, IDF_PATH=%IDF_PATH%

echo.
echo [步骤2/3] 开始编译 yuhe/cam
echo           编译命令: python scripts\build.py yuhe/cam
echo           首次编译或全量编译需几分钟, 请耐心等待...
python scripts\build.py yuhe/cam
if errorlevel 1 (
    echo.
    echo [错误] 编译失败, 请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo [步骤3/3] 编译成功!
echo   产物目录:     %CD%\build
echo   merged 固件:  %CD%\build\merged-binary.bin
echo   资源分区镜像: %CD%\build\generated_assets.bin
echo.
echo 下一步烧录, 把 COMx 换成实际串口号:
echo   yh_flash.bat COMx
echo 或显式全量烧录, 在工程目录下执行:
echo   python -m esptool --chip esp32s3 -p COMx -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0xd000 build\ota_data_initial.bin 0x20000 build\yuhe.bin 0x800000 build\generated_assets.bin
echo 提示: assets 分区必须全量烧录, 后续 OTA 只刷 app 分区
pause
