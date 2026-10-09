@echo off
rem Build my-s3-tft with round-screen UI (same env as build_my_s3_tft.bat)
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;D:\INSTALL\Git\cmd;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"
cd /d G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
python scripts\build.py my-s3-tft --name my-s3-tft
