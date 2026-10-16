# hardware/sets 版型适配规范（版型作者必读）

`hardware/sets` 是**多版型适配中心**：一套固件源码 + N 套版型配置，
由 `build.py` 在编译前让你选版型，自动同步、注册、编译、（可选）烧录。

固件源码（下文记作 `<FW>`）默认是 **sets 自带的副本**：

```
hardware/sets/xiaozhi-esp32/                    ← 默认（sets 自成一体）
hardware/small_screen_camera/xiaozhi-esp32/     ← 回退（副本不存在时才用）
```

副本按「仅源码」维护，不含 `build/` 与 `managed_components/`；
首次编译缺依赖时脚本会自动从上游本地拷贝一份。可用 `--fw-root` 或
环境变量 `XIAOZHI_FW_ROOT` 指定别处的固件根。

**版型作者仍然只放差异文件**：不要往 `boards/<id>/` 里塞固件源码，
也不要手改 `<FW>/main/` 下任何文件——同步与注册由 `build.py` 统一负责。

---

## 1. 目录约定

```
hardware/sets/
├── README.md                 # 用户导航（怎么用）
├── SPEC.md                   # 本文件（怎么写版型）
├── build.py                  # 编译 + 烧录入口（唯一入口）
├── xiaozhi-esp32/            # 固件源码副本 <FW>（仅源码；产物与依赖不入库）
└── boards/
    └── <id>/                 # 一个版型一个目录，id 用小写短横线
        ├── set.json          # 【必需】版型元数据，build.py 读它出菜单
        ├── config.json       # 【必需】固件 scripts/build.py 读它
        ├── config.h          # 【必需】引脚与参数宏
        ├── <board>.cc        # 【必需】板实现，末尾 DECLARE_BOARD(...)
        ├── *.h               # 【可选】私有头文件（如 power_manager.h、lcd_display.h）
        └── README.md         # 【必需】版型说明 + 已知注意点
```

同步规则：`build.py` 把 `<id>/` 下 **除 `set.json`、`README.md`** 之外的
`*.c / *.cc / *.h / *.json` 复制到 `<FW>/main/boards/yuhe/<id>/`。

---

## 2. set.json（build.py 的菜单数据源）

```json
{
  "id": "yh-cam",
  "name": "屿禾 AI Camera（摄像头版）",
  "description": "ESP32-S3 + OV2640 + ES8311/ES7210 + ST7789 320x240，带 AEC 回采",
  "manufacturer": "yuhe",
  "target": "esp32s3",
  "board_dir": "yuhe/yh-cam",
  "kconfig_symbol": "BOARD_TYPE_YUHE_SET_CAM",
  "kconfig_prompt": "Yuhe AI Camera (sets)",
  "text_font": "font_noto_sans_basic_20_4",
  "icon_font": "font_material_symbols_20_4",
  "build_name": "yh-cam",
  "sdkconfig_append": [],
  "pins_verified": true,
  "notes": "功放由 PCA9557 P1 控制；LCD 无 CS/RST，RST 由 PCA9557 P0 软控"
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 目录名，全小写短横线。**必须**与目录名一致 |
| `name` | ✅ | 菜单里显示的中文名 |
| `description` | ✅ | 菜单里显示的一行说明 |
| `manufacturer` | ✅ | **固定 `yuhe`**（固件 build.py 会拿它和 board_dir 第一层做一致性校验） |
| `target` | ✅ | 如 `esp32s3` |
| `board_dir` | ✅ | 同步目标 `main/boards/<board_dir>`，形如 `yuhe/<id>` |
| `kconfig_symbol` | ✅ | Kconfig 符号，**不带** `CONFIG_` 前缀，全大写，不能以数字开头 |
| `kconfig_prompt` | ✅ | menuconfig 里显示的名字 |
| `text_font` / `icon_font` | ✅ | 内置字体，见 `<FW>/main/CMakeLists.txt` 里其它板用的两个 `set(BUILTIN_*_FONT ...)` |
| `emoji_collection` | ⭕ | 表情集合，省略则用 `noto-color-emoji_64`。`build.py` 总会为每套版型生成 `set(DEFAULT_EMOJI_COLLECTION ...)` 行——**这一行不能省**，源板 `yuhe/cam`、`yuhe/1.54tft-wifi` 的第 4 行就是它 |
| `build_name` | ✅ | OTA 上报的板名，通常与 `id` 相同 |
| `sdkconfig_append` | ✅ | **增量追加层，正常情况留 `[]`**（语义见下方说明） |
| `pins_verified` | ✅ | **引脚是否已实物核实**。`false` 会在编译前打醒目警告 |
| `notes` | ✅ | 已知坑点，会打印在选择确认后 |

---

## 3. config.json（固件 scripts/build.py 读）

```json
{
    "manufacturer": "yuhe",
    "type": "yh-cam",
    "target": "esp32s3",
    "builds": [
        { "name": "yh-cam", "sdkconfig_append": [] }
    ]
}
```

硬约束（来自 `<FW>/scripts/build.py` 的校验）：
- `manufacturer` **必须**等于 `config.json` 所在目录路径的第一层 → 统一写 `yuhe`
- `target` 非空字符串
- `builds[].name` 非空；`builds` 至少一项

**还有两条全局查重，违反会直接让编译终止**（`scripts/build.py` 的 `_collect_variants()` 会
`main/boards/**/config.json` 全量 `rglob` 后逐条比对）：
- `type` **全局唯一**，且必须匹配 `^[a-z0-9.-]+$`（只允许小写字母、数字、`.`、`-`，**下划线非法**）
- `builds[].name` **全局唯一**

新增版型前，先确认 `type` / `name` 不与 `main/boards/` 下任何现存板撞车。

### 3.1 两个 `sdkconfig_append` 的分工（容易搞混，务必看清）

`set.json` 和 `config.json` 里**都有** `sdkconfig_append`，作用完全不同：

| 文件 | 角色 | 正常该填什么 |
|---|---|---|
| `config.json` | **权威真源**，固件 `scripts/build.py` 直接读它生成 sdkconfig | 该版型**完整**的 sdkconfig 追加项 |
| `set.json` | **增量追加层**，`hardware/sets/build.py` 读它 | **留 `[]`** |

`build.py` 的 `write_build_config()` 是「追加 + 去重」语义：

```python
append = list(board.get("sdkconfig_append") or [])   # 来自 set.json
if not append:
    return "config.json", []          # 为空 → 零副作用，直接回落 config.json
merged = [str(i) for i in (entry.get("sdkconfig_append") or [])]   # config.json 的
for line in append:
    if line not in merged:            # 去重
        merged.append(line)           # 追加
```

所以：**在 `set.json` 里重复抄一遍 `config.json` 的内容不会报错，但会造成两处维护、改一处忘另一处。**
只有临时调试（例如临时关掉 AEC 验证问题）才往 `set.json` 里写。

### 3.2 屿禾版型的公共 sdkconfig 组

四套版型统一接入屿禾私有服务器，`config.json` 里都应包含这几组（以 `boards/yh-cam/config.json` 为准）：

- **YH 私有协议**：`YH_PROTOCOL_ENABLED` / `YH_SERVER_HOST` / `YH_SERVER_PORT` / `OTA_URL`
- **语音打断防护**：`YH_VAD_MODE` / `YH_VAD_MIN_SPEECH_MS` / `YH_VAD_MIN_NOISE_MS` /
  `YH_VAD_SPEECH_CONFIRM_MS` / `YH_VAD_SILENCE_CONFIRM_MS` / `YH_INTERRUPT_GUARD_MS`
  —— 这组是治「TTS 播到一半被自己打断」的，**不要删**（详见 `<FW>/main/Kconfig.projbuild` 的
  menu "YH Voice Interrupt Tuning"）
- **自定义唤醒词**：`USE_CUSTOM_WAKE_WORD` / `CUSTOM_WAKE_WORD="ni hao xiao he"` / `THRESHOLD` /
  `SR_MN_CN_MULTINET7_QUANT` / `SR_WN_WN9_NIHAOXIAOZHI_TTS=n`
- **16MB flash 与分区**：`ESPTOOLPY_FLASHSIZE_16MB` / `PARTITION_TABLE_CUSTOM` /
  `PARTITION_TABLE_CUSTOM_FILENAME="partitions/v2/16m.csv"` / `FLASHMODE_DIO`
  （flash 容量与分区表**必须同时改**，只改一个会导致镜像超出容量而烧录失败）
- **资源烧录**：`FLASH_DEFAULT_ASSETS=y`（`partitions/v2/16m.csv` 含 8M 的 assets 分区）

**按硬件能力取舍的两条**：
- 有 codec 回采通道的版型才加 `USE_DEVICE_AEC=y`（目前只有 `yh-cam`）。
  ES8311 单 codec（`es8311_audio_codec.cc` 的 `input_reference_` 硬编码为 `false`）
  和 `NoAudioCodecSimplex` 都**没有**回采，加了也不生效。
- 有摄像头才加 `CAMERA_PSRAM_DMA=y`（目前只有 `yh-cam`）。

> 历史背景：源板 `yuhe/1.54tft-wifi` 的 `sdkconfig_append` 原本是 `[]`（走官方小智服务器），
> 与 `yuhe/cam` 的 31 条（走屿禾私有）不同源。经确认，四套版型现已统一接入屿禾私有服务器。

---

## 4. 板实现 `<board>.cc` 要求

- 末尾必须有 `DECLARE_BOARD(YourBoardClass);`
- 类名不要与 `<FW>/main/boards/` 下其它板重名（sets 下统一加 `YhSet` 前缀风格，如 `YhSetCamBoard`）
- `config.h` 只放宏；引脚相关一律进 `config.h`，**不要**在 `.cc` 里硬编码 GPIO
- 引用头文件用相对路径：`#include "config.h"`、`#include "power_manager.h"`
- 需要 `../common/` 下的公共组件（button / led / display / i2c_device 等）时直接 include，
  `main/CMakeLists.txt` 已把 `boards/common` 加入 include 目录
- 复用 `<FW>/main/boards/yuhe/` 下已有实现时，**整体复制后改名**，不要跨目录 include

## 5. 编码约定

- 源文件：UTF-8 **无 BOM**，换行 LF；中文注释照常写
- 不要引入 PowerShell 5.1 不兼容的东西（本套脚本在 Git Bash / PowerShell 下都要能跑）
- 不要在 `.cc` 里写绝对路径，全部相对

## 6. 禁止事项

- ❌ 不要修改 `<FW>/main/Kconfig.projbuild` 和 `<FW>/main/CMakeLists.txt`
  —— 注册由 `build.py` 统一自动维护（标记块内），版型作者碰都不要碰
- ❌ 不要修改 `<FW>/main/` 下除 `boards/yuhe/<id>/` 之外的任何文件
- ❌ 不要复制固件源码树到 sets 下
- ❌ 不要在 `config.h` 里 `using namespace`

## 7. 新增一个版型的完整流程

1. `mkdir hardware/sets/boards/<new-id>`
2. 按第 1 节放齐 `set.json` / `config.json` / `config.h` / `<board>.cc` / `README.md`
3. 跑 `python hardware/sets/build.py --list` 确认能扫到
4. 跑一次编译验证（不需要真的烧录）

`build.py` 会自动完成：菜单选择 → 文件同步 → Kconfig/CMakeLists 注册 → 调用固件 build.py。
