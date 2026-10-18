# 小智固件构建操作手册（2026-10-11 预检版）

> 板型：`my-s3-tft` 圆屏（ESP32-S3 / 16MB Flash / MN7 自定义唤醒词）
> 本轮源码改动（全部已预检通过，**尚未构建**）：拼音表扩至 196 字、云端唤醒词"已生效"明示日志、cloud_config_synced_ 状态提示（配置同步中→唤醒词就绪→待命）、esp_mn_commands 返回值检查、NVS 带调拼音自愈、EraseKey dirty_ 修复
> 预检完成时间：2026-10-11 00:56

---

## ⚠️ 零、先读：为什么必须重新构建

`build/` 目录现存产物是 **00:21-00:22 构建的**，只包含昨晚的改动（196 字表 ✅ 已在 bin 内验证）。但以下两项是 **00:48-00:53 才落地的，不在现存 bin 里**：

- `application.cc` / `application.h`：cloud_config_synced_ 状态提示 + esp_timer 回落（00:48-00:52）
- `board.cc`："云端唤醒词已生效" 日志（00:53:40）

二进制抽查证据：00:22 的 `yuhe.bin` 中 `灵/琳/早/上/已丢弃该词/Discarded legacy` 均 FOUND，但 `云端唤醒词已生效/cloud_config_synced/配置同步` 均 MISSING。**直接烧现存 bin 会缺少状态提示和新日志，请务必按下面流程重新构建。**

---

## 一、构建（PowerShell / CMD 均可）

### 方式 A：一键脚本（推荐，与历史构建完全一致）

```bat
cd /d G:\demo\21_xiaozhi\code\small_secreen\yuhe-esp32
build_my_s3_tft.bat
```

脚本内部做了：环境变量（IDF v6.1、`IDF_TOOLS_PATH=D:\INSTALL\esp`、TEMP 重定向防杀软）→ `export.bat` → `python scripts\build.py my-s3-tft --name my-s3-tft`（自动增量编译 + merge-bin 出 `merged-binary.bin`）。

### 方式 B：PowerShell 手动配方

```powershell
$env:PYTHONPATH=""
$env:MSYSTEM=""
$env:IDF_TOOLS_PATH="D:\INSTALL\esp"
$env:IDF_PATH="D:\INSTALL\esp\v6.1\esp-idf"
$env:IDF_PYTHON_ENV_PATH="D:\INSTALL\esp\tools\python\v6.1\venv"
$env:IDF_GITHUB_ASSETS="dl.espressif.com/github_assets"
$env:TEMP="D:\INSTALL\esp\tmp"; $env:TMP="D:\INSTALL\esp\tmp"
& D:\INSTALL\esp\v6.1\esp-idf\export.ps1   # 若 export.ps1 报错就用 cmd: cmd /c "D:\INSTALL\esp\v6.1\esp-idf\export.bat && python scripts\build.py my-s3-tft --name my-s3-tft"
cd G:\demo\21_xiaozhi\code\small_secreen\yuhe-esp32
python scripts\build.py my-s3-tft --name my-s3-tft
```

### "被杀重跑"坑（重要）

- **构建中途被杀/断电/中断**：直接**重跑同一命令**即可。ninja 增量编译会续编，不会从头开始（约省 80% 时间）。
- 若重跑时报 **CMake 配置错误**（如 `CMakeCache.txt` 损坏、`build directory is invalid`）：
  ```bat
  cd /d G:\demo\21_xiaozhi\code\small_secreen\yuhe-esp32\build
  del CMakeCache.txt
  cd ..
  python scripts\build.py my-s3-tft --name my-s3-tft
  ```
- 若仍失败再考虑 `idf.py fullclean` 全量重建（约 15-25 分钟，一般用不到）。
- **杀软拦截 gcc 临时文件**（`ccXXXXXX.s Permission denied`）：脚本已把 TEMP 重定向到 `D:\INSTALL\esp\tmp`，若仍出现请临时关闭杀软实时防护。
- 构建成功标志：`Project build complete` + `build/merged-binary.bin` 时间戳刷新。

### 构建产物自查（烧录前）

| 文件 | 应满足 |
|------|--------|
| `build/yuhe.bin` | 时间戳 = 本次构建时间（> 01:00） |
| `build/generated_assets.bin` | 同上（assets 一般不变，时间可能不刷新，属正常） |
| `build/merged-binary.bin` | 时间戳 ≥ yuhe.bin（merge 是最后一步） |

---

## 二、烧录（全量五分区，含 0x800000）

> 分区表 `partitions/v2/16m.csv`：nvs 0x9000 / otadata 0xd000 / phy 0xf000 / ota_0 0x20000 / assets 0x800000(8M)。
> 烧录清单以 `build\flash_args` 为权威：0x0、0x8000、0xd000、0x20000、0x800000 共 **5 个分区**（phy_init 分区无需单独烧）。

### 方式 A：一键脚本（自动探测 COM 口）

```bat
cd /d G:\demo\21_xiaozhi\code\small_secreen\yuhe-esp32
yh_flash.bat            :: 或显式指定：yh_flash.bat COM5
```

### 方式 B：手动 esptool（COM 口按实际改）

```bat
cd /d G:\demo\21_xiaozhi\code\small_secreen\yuhe-esp32\build
python -m esptool --chip esp32s3 -p COM5 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0xd000 ota_data_initial.bin 0x20000 yuhe.bin 0x800000 generated_assets.bin
```

| 偏移 | 文件 | 说明 |
|------|------|------|
| `0x0` | `bootloader/bootloader.bin` | 引导器 |
| `0x8000` | `partition_table/partition-table.bin` | 分区表 |
| `0xd000` | `ota_data_initial.bin` | OTA 引导数据（保证从 ota_0 启动） |
| `0x20000` | `yuhe.bin` | 应用固件（本轮改动全在这） |
| `0x800000` | `generated_assets.bin` | **资产分区（MN7 模型+默认命令表，勿漏刷）** |

烧完自动复位重启。**烧录失败排查**：换数据线（部分线只供电）→ 按住 BOOT 上电进下载模式 → 关掉占用串口的监视器。

---

## 三、烧后验证清单（串口逐条核对）

接串口（115200），开机后按时间顺序应依次出现：

| # | 时间点 | 关键词（出现即 ✅） | 说明 |
|---|--------|---------------------|------|
| 1 | ~3s | `Command: ni hao xiao he, Text: 你好小禾, Action: wake` | 默认命令表从 assets 注册（index.json） |
| 2 | ~3s | `---------------------ACTIVE SPEECH COMMANDS---------------------` 后跟 `commans ID: 1, phrase_id: 0 --> ni hao xiao he` | MN7 激活命令打印（esp 库拼写就是 "commans"，不是 bug） |
| 3 | 3-10s | 屏显 **`配置同步中...`**（状态栏） | 新增：等云端配置期间的过渡文案 |
| 4 | 14-17s | `Received device_config:` 且含 `"wake_word"` | 云端配置推送到达 |
| 5 | 14-17s | `云端唤醒词已生效: N 个 [首个词]（开机即用，已存本地）` | **本轮新增日志**。N=后台配置的词数；后台配 3 个词则 N=3，且 ACTIVE SPEECH COMMANDS 重打为 3 条 `commans ID:` |
| 6 | 14-17s | `云端配置同步完成` + 屏显 **`唤醒词就绪`**，2 秒后回落 **`待命`** | **本轮新增**：cloud_config_synced_ 状态机 |
| 7 | （重启后） | `Restored N server wake-word command(s) from NVS` | NVS 缓存恢复，属正常 |
| 8 | （仅旧 NVS 有带调拼音时） | `Discarded legacy toned pinyin in NVS` | 自愈逻辑丢弃 `ni3 hao3` 旧格式 |

**负面关键词**（出现即异常，需排查）：

- `Add command N failed` / `Command rejected by multinet` → 拼音格式问题
- `唤醒词 'X' 含未收录字，无法转拼音，已丢弃该词` → 后台词表用了 196 字表外的字
- `云端唤醒词全部无法转换为拼音，忽略` → 全部词都转不了，会保持默认词

---

## 四、预期行为与唤醒测试

### 开机时间线（正常路径）

1. **0-3s**：连 WiFi → 初始化 MultiNet → 注册默认词"你好小禾"
2. **3-14s**：状态栏显示 **配置同步中...**（此时喊云端词可能不响应，喊"你好小禾"可以）
3. **14-17s**：`device_config` 到达 → 串口打 `云端唤醒词已生效` → 屏显 `唤醒词就绪` → 2 秒后 `待命`
4. **17s 后**：全部云端词可用

### 喊话测试

| 测试 | 预期 |
|------|------|
| 开机 17 秒内喊 **"你好小禾"** | 应唤醒（默认词先生效） |
| 同步完成后喊 **"琳琳"**（若后台已配） | 应唤醒，串口打 `Wake word detected: 琳琳` + `Custom wake word detected: command_id=...` |
| 同步完成后喊 "你好小禾" | 若云端词表已覆盖默认词，需看 `云端唤醒词已生效: N 个` 里是否含"你好小禾"；后台配了就应唤醒 |
| 唤醒后说"现在几点" | ASR → LLM → TTS 全链路语音回复 |

### 云端换词管理

后台：`https://sandyun.top:8001/admincc/#/admin/wake-word`（最多 10 词、每词 ≤30 字）。改词后**重启设备或断开重连生效**（配置仅连接时拉取）。清空词表 = 恢复默认词"你好小禾"。

---

## 五、本轮源码改动预检结果（存档）

| 文件 | 改动项 | 状态 |
|------|--------|------|
| `main/boards/common/board.cc` | 拼音表 196 字（灵 ling/早 zao/上 shang/琳 lin 等单字验证在位） | ✅ |
| `main/boards/common/board.cc` | 丢弃词明示日志 `已丢弃该词`（L257） | ✅ |
| `main/boards/common/board.cc` | 云端唤醒词已生效日志（L265，00:53 新增） | ✅ |
| `main/audio/wake_words/custom_wake_word.cc` | `esp_mn_commands_add/update` 返回值检查 ×3 处（L189-204/262-279/326-342） | ✅ |
| `main/audio/wake_words/custom_wake_word.cc` | NVS 带调拼音自愈 `Discarded legacy`（L155，含 EraseKey pinyins/displays） | ✅ |
| `main/audio/wake_words/custom_wake_word.cc` | 默认词快照+恢复（default_commands_，agent-4 设计已实施 L126-129/304-350） | ✅ |
| `main/application.cc/.h` | cloud_config_synced_ 状态提示 + esp_timer 2 秒回落 + 配置同步中→唤醒词就绪→待命 | ✅ |
| `main/settings.cc` | EraseKey 置 dirty_（L97，擦除落盘修复） | ✅ |
| 语法粗检 | 6 文件括号/圆括号平衡（raw-string 感知词法器）全过 | ✅ |
| 依赖检查 | display 接口 7 方法声明在位；`<esp_timer.h>` 已 include | ✅ |

---

## 六、常见问题

**Q1：构建报 `idf.py was not found` / python 报错？**
环境变量没生效。最稳的是直接用方式 A 的 `build_my_s3_tft.bat`（在 cmd 下跑）。

**Q2：烧完喊"琳琳"没反应？**
1. 先看第 5 条日志 `云端唤醒词已生效: N 个 [X]` 里有没有"琳琳"——没有说明后台没配上词，去管理后台加；
2. 有但仍喊不醒 → 阈值偏高，`main/boards/my-s3-tft/config.json` 里 `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD=40` 调到 30-35 重新构建；
3. 串口看 `已丢弃该词` WARN → 该词含未收录字。

**Q3：屏上一直停在"配置同步中"？**
说明 device_config 没到达。查服务器连通（`sandyun.top:12399`）、看串口有无 `Received device_config`。超 60 秒可重启设备重试。

**Q4：OTA 提示升级，要不要点？**
本轮是本地构建版本，OTA 会拉 `http://sandyun.top:8002/yuhe/ota/` 的服务器版本覆盖本地改动。**验证阶段请勿 OTA**。

---

*手册生成：2026-10-11 01:00 · 预检员 general-purpose-6 · 源码文件最后修改：board.cc 00:53 / application.cc 00:52 / custom_wake_word.cc 22:18(昨) / settings.cc 21:24(昨) · 现存 build 产物 00:22 已过期，必须重新构建*
