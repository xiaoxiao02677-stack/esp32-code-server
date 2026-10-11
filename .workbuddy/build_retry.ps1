$env:PYTHONPATH=''
$env:MSYSTEM=''
$env:IDF_TOOLS_PATH='D:\INSTALL\esp'
$env:IDF_PATH='D:\INSTALL\esp\v6.1\esp-idf'
$env:IDF_PYTHON_ENV_PATH='D:\INSTALL\esp\tools\python\v6.1\venv'
$env:IDF_GITHUB_ASSETS='dl.espressif.com/github_assets'
$env:ESP_IDF_VERSION='6.1.0'
$env:TEMP='D:\INSTALL\esp\tmp'
$env:TMP='D:\INSTALL\esp\tmp'
$env:PATH='D:\INSTALL\esp\tools\python\v6.1\venv\Scripts;D:\INSTALL\esp\tools\cmake\4.0.3\bin;D:\INSTALL\esp\tools\ninja\1.12.1;D:\INSTALL\Git\cmd;C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem'
Set-Location 'G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32'
# 重试循环：进程被杀（防病毒）则自动重启构建，ninja 增量续跑
for ($i = 1; $i -le 10; $i++) {
    Write-Output "===== 构建尝试 $i ====="
    & 'D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe' 'scripts\build.py' my-s3-tft --name my-s3-tft 2>&1 | Select-Object -Last 4
    if ($LASTEXITCODE -eq 0) {
        Write-Output "===== BUILD SUCCESS at attempt $i ====="
        break
    }
    Write-Output "attempt $i failed (exit=$LASTEXITCODE), retrying in 5s..."
    Start-Sleep -Seconds 5
}
