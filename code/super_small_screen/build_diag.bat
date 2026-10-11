@echo off
rem Build WiFi diagnostic firmware (channel-hopping test)
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;D:\INSTALL\Git\cmd;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
if errorlevel 1 exit /b 1
cd /d G:\demo\21_xiaozhi\code\super_small_screen\diag
python %IDF_PATH%\tools\idf.py set-target esp32s3 build
if errorlevel 1 exit /b 1
echo === DIAGNOSTIC BINARY ===
dir build\*.bin
pause
