@echo off
rem Incremental build (no set-target / fullclean). Requires existing build dir.
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
if errorlevel 1 exit /b 1
cd /d G:\demo\21_xiaozhi\code\super_small_screen
python %IDF_PATH%\tools\idf.py build
exit /b %errorlevel%
