@echo off
rem ESP-IDF v6.1 env: IDF=D:\INSTALL\esp\v6.1\esp-idf, tools root=D:\INSTALL\esp
rem Project now lives at an ASCII-only path (G:\demo\21_xiaozhi\code\xiaozhi-esp32);
rem the old G:\xiaozhi-fw junction workaround for Chinese+space paths is retired
rem and the dead link has been removed.
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set IDF_GITHUB_ASSETS=dl.espressif.com/github_assets
rem Redirect TEMP away from %USERPROFILE%\AppData\Local\Temp to avoid antivirus
rem intermittently blocking gcc temp file writes (ccXXXXXX.s Permission denied)
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;D:\INSTALL\Git\cmd;D:\INSTALL\esp\tools\python\v6.1\venv\Scripts"
rem ESP-IDF linker breaks on spaces in project path (esp_audio_codec/esp_image_effects
rem -L flags). Those components' CMakeLists are patched in managed_components:
rem "-L <dir>" -> "-L<dir>" so the whole path is passed as one quoted argument.
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
rem self-adaptive: was hardcoded to the pre-2026-10-15 repo layout
cd /d "%~dp0"
python scripts\build.py my-s3-tft --name my-s3-tft
