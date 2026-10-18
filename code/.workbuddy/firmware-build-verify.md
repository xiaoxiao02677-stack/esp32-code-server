# 固件 B 线改动（设备配置云端记忆）构建验证报告

- 任务：#14 工程师：固件构建验证
- 执行：e-fw-build，2026-10-06
- 固件仓：`G:/demo/21_xiaozhi/code/yuhe-esp32`（ESP-IDF v6.1，target=esp32s3，board=my-s3-tft）
- 构建日志：`.workbuddy/fw_build.log`

## 1. 结论：本机可编 ✅

- 本机（G 盘机）装完整 ESP-IDF v6.1 工具链：`D:\INSTALL\esp`（esp-clang esp-21.1.3、xtensa-esp-elf esp-15.2.0、cmake 4.0.3、ninja 1.12.1、idf venv）。
- `idf.py build` 全量完成：**EXIT=0，约 19 分钟（2198 步）**，产物齐全：
  - `build/yuhe.bin`（2,702,656 B）、`build/bootloader/bootloader.bin`、`build/flash_args`
  - 烧录布局：`0x0 bootloader / 0x8000 partition-table / 0xd000 ota_data_initial / 0x20000 yuhe.bin / 0x800000 generated_assets.bin`（16MB flash）
- 4 个改动文件全部编译通过（ninja 记录）：
  | 文件 | 构建步 | 结果 |
  |---|---|---|
  | `main/application.cc`（L719 device_config 分支） | 2152 | ✅ |
  | `main/boards/common/board.cc`（L64 ApplyDeviceConfig + L13 cmath） | 2151 | ✅ |
  | `main/boards/my-s3-tft/my_s3_tft_board.cc`（删开机 SetOutputVolume(50)） | 2188 | ✅ |
  | `main/boards/common/board.h`（L98 声明，随各 .cc 实例化） | — | ✅ |
- 编译器警告：本次构建 0 条 C/C++ warning（仅有 venv 路径风格、组件校验、gdbinit 等基础设施 warning，与改动无关）。

### 静态走查补充（逐行确认项）
- `application.cc:719-742`：`cJSON_PrintUnformatted(payload)` 经 RAII `CJsonStringUniquePtr` 判空后才 `Schedule`；闭包捕获 `std::string` 副本 `payload_str`（规避回调线程内 `root` 被 `cJSON_Delete` 的悬垂引用），在 main 任务重新 `cJSON_Parse` 判空后调 `ApplyDeviceConfig`。
- `board.cc:64-122`：`volume`/`brightness` 均先做 `valuedouble` 整性（`dv==std::floor(dv)`）+ 0–100 钳制再取 `valueint`；幂等——仅当 `codec->output_volume() != v` / `backlight->brightness() != b` 才写；NVS 持久化由基类承担（`audio_codec.cc:40` `SetOutputVolume` 写 `audio/output_volume`，`SetBrightness(…, true)` 写 `display/brightness`）。
- `board.cc:76` 注释与实现一致：100.5 会被整性检查拒绝而非截断成 100。
- `my_s3_tft_board.cc:89-92`：已无开机 `SetOutputVolume(50)`，注释说明"开机音量由 AudioCodec 从 NVS (audio/output_volume) 恢复"，与 B 线设计（云端下发 → NVS → 开机恢复）闭环。

## 2. 真机烧录与验证步骤

### 2.1 烧录
```bat
cd /d G:\demo\21_xiaozhi\code\yuhe-esp32
yh_flash.bat            :: 自动探测 CP210x/CH340/USB-JTAG 串口；或 yh_flash.bat COM5
```
等效命令（yf_flash.bat 内部实现，esp32s3 + 16MB flash）：
```
python -m esptool --chip esp32s3 -p COM5 -b 460800 --before default-reset --after hard-reset ^
  write-flash "@flash_args" --flash-mode dio --flash-size 16MB --flash-freq 80m
```
或 `idf.py -p COM5 flash`（需先 export 环境，见 2.4）。

### 2.2 串口日志断言（115200）
监视：`python yh_monitor.py COM5` 或 `monitor.bat`（Ctrl+C 退出）。

按时间顺序应看到（TAG 已核对）：
1. 启动：`MyS3TftBoard: Board init done (audio in=.. Hz, out=.. Hz, volume restored from NVS)`
   —— 断言：**不再出现** `AudioCodec: Set output volume to 50`（旧硬编码已删）。
   - 若 NVS 中已有云端写入的音量：开机会有 `AudioCodec: Set output volume to <N>`（codec 恢复路径），N 应为上次云端值。
2. 联网后 hello：`WS: Server hello: sample_rate=..`（websocket）/ mqtt 侧无该日志则看 `MQTT` TAG 连接成功日志。
3. 服务端下发 device_config（Kawaii 控制台保存设备配置后重连触发）：
   - `Application: Received device_config: {"volume":..,"brightness":..}`
   - 有变更：`Board: 应用云端配置 volume=<N> brightness=<N|keep>` + 对应
     `AudioCodec: Set output volume to <N>`（音量）/ 背光亮度日志（亮度）
   - 无变更（幂等）：`Board: Cloud device config matches local state, nothing to apply`

### 2.3 幂等复验（ApplyDeviceConfig）
1. 控制台改音量 30 → 保存 → 设备重连：应见 `Set output volume to 30`。
2. 立即再触发一次相同下发（设备重连、不改值）：应见
   `Board: Cloud device config matches local state, nothing to apply`，**无** `Set output volume` 日志。
3. 断电重启：开机日志应恢复音量 30（`volume restored from NVS`），证明 NVS 记忆生效。
4. 异常值防护（可选，服务端手工发 `{"volume":100.5}`）：应见
   `Board: Ignore fractional/out-of-range device_config volume: 100.5`，硬件音量不变。

### 2.4 构建命令清单（本机/部署机）
工具链在 `D:\INSTALL\esp`，Git Bash 下直接调 `idf.py` 会因 `MSYSTEM=MINGW64` 被拒
（v6.1 仅警告但沙箱 `env -u` 失效导致无法干净剥离）。两种可用姿势：
```bat
:: 姿势 A（推荐，CMD/PowerShell 原生环境）
set IDF_TOOLS_PATH=D:\INSTALL\esp\tools
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set ESP_IDF_VERSION=6.1
D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe D:\INSTALL\esp\v6.1\esp-idf\tools\idf.py -DIDF_TARGET=esp32s3 -DBOARD_NAME=my-s3-tft build
```
```bash
# 姿势 B（Git Bash）：在 python -c 中 pop MSYSTEM/PYTHONPATH 后 runpy 执行 idf.py，
# 且需 PATH 前置 D:/INSTALL/esp/tools/cmake/4.0.3/bin;D:/INSTALL/esp/tools/ninja/1.12.1
# 本次成功构建即按此姿势执行（约 19 分钟全量）。
```
CI/部署机增量构建：同一命令即可（CMakeCache 已对齐当前路径 `G:/demo/21_xiaozhi/code/yuhe-esp32`）。

## 3. 已知风险
1. **`dv == std::floor(dv)` 整性判断**：对大数值 double 与 NaN 安全（NaN 比较为 false，会被拒），但依赖 JSON 数值先被 cJSON 存为 double；服务端若下发字符串 `"volume":"50"` 会走 `cJSON_IsNumber` false 分支被忽略并打 `Ignore invalid ... volume value` 警告——需要服务端严格下发 number 类型（建议 e-pi4-config-ui/e-pi5-mqtt 校验下发序列化）。
2. **Schedule 线程模型**：`ApplyDeviceConfig` 在 main task 执行（application.h:84 契约），其中 I2C（es8311/es8374）与 NVS 写均在 main task，与现有调用路径一致，无新增线程约束；但若未来在非 main task 直接调 `ApplyDeviceConfig` 会破坏该前提。
3. **brightness 钳制到 0**：`SetBrightness(0, true)` 会把背光写到全黑并持久化，属预期行为但用户可能"看不见"；建议控制台 UI 对 0 值加二次确认（P1-4 范围）。
4. **16MB flash 布局强耦合**：`0x800000 generated_assets.bin` 与 16m 分区表绑定；若 4M 设备误用本构建会烧录失败。
5. **构建环境脆弱点**：Git Bash/沙箱下 `MSYSTEM` 注入使 `idf.py` 告警，`env -u` 被 shim 拦截失效（本次已用 python 内 pop 绕过）；`yh_flash.bat` 的 `set MSYSTEM=` 在原生 cmd 下有效，CI 务必走 CMD/PowerShell 姿势 A。
6. **串口日志点依赖 TAG**：`Board`/`Application`/`AudioCodec` TAG 为中文日志混排，若后续改 TAG 名称需同步本断言清单。

## 4. 交付物
- `G:/demo/21_xiaozhi/code/.workbuddy/firmware-build-verify.md`（本文件）
- `G:/demo/21_xiaozhi/code/.workbuddy/fw_build.log`（完整构建日志，2198 步全通过）
- 源码零改动（仅生成 build/ 产物，属正常构建副作用）
