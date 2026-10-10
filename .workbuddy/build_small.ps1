$env:PYTHONPATH=''
$env:MSYSTEM=''
$env:IDF_TOOLS_PATH='D:\INSTALL\esp'
$env:IDF_PATH='D:\INSTALL\esp\v6.1\esp-idf'
$env:IDF_PYTHON_ENV_PATH='D:\INSTALL\esp\tools\python\v6.1\venv'
$env:IDF_GITHUB_ASSETS='dl.espressif.com/github_assets'
$env:ESP_IDF_VERSION='6.1.0'
$env:TEMP='D:\INSTALL\esp\tmp'
$env:TMP='D:\INSTALL\esp\tmp'
# 完整工具链 PATH（与 build_my_s3_tft.bat 一致 + cmake/ninja 工具目录）
$env:PATH='D:\INSTALL\esp\tools\python\v6.1\venv\Scripts;D:\INSTALL\esp\tools\cmake\4.0.3\bin;D:\INSTALL\esp\tools\ninja\1.12.1;D:\INSTALL\esp\tools\idf-exe\1.6.2;D:\INSTALL\Git\cmd;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem'
Set-Location 'G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32'
& 'D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe' 'scripts\build.py' my-s3-tft --name my-s3-tft
