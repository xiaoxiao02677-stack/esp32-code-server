# 小智固件 · 多版型适配中心（hardware/sets）

一套固件源码 + N 套版型配置。在这里选一个版型，`build.py` 会自动完成
**同步 → 注册 → 编译 → 归档产物**，你不需要手工去改固件源码树里的任何文件。

**构建与烧录是两个脚本，职责分开：**

| 脚本 | 职责 |
|---|---|
| `build.py` | 选版型 → 同步 → 注册 → 编译 → 归档产物。**不做任何串口操作** |
| `flash.py` | **多线程并行探测 COM 口** → 选择设备 → esptool 烧录。**不编译** |

先 `build.py` 出产物，再 `flash.py` 烧进去；只想烧已有的产物就直接跑 `flash.py`。

固件源码（下文记作 `<FW>`）默认使用**本目录自带的副本**：

```
hardware/sets/xiaozhi-esp32/                    ← 默认：sets 自成一体，不碰上游工作区
hardware/small_screen_camera/xiaozhi-esp32/     ← 回退：副本不存在时才用
```

副本按「仅源码」维护（约 10 MB，不含 `build/` 与 `managed_components/`）。
首次编译若缺 `managed_components/`，脚本会**自动从上游目录本地拷贝**一份
（远比联网重下 758 MB 快）；上游也没有时才交给 ESP-IDF 联网拉取。

要改用别处的固件根，用 `--fw-root <DIR>` 或环境变量 `XIAOZHI_FW_ROOT`。

---

## 1. 一条命令起步

**不需要先激活 ESP-IDF 环境。** 脚本会自己把环境找齐：依次探测 `--python` →
`IDF_PYTHON_ENV_PATH` → `eim_idf.json`（Espressif IDE Manager 的安装记录）→
`IDF_TOOLS_PATH/python/*/venv` → 常见安装目录，然后把 IDF venv 的 python、
`IDF_PATH`、`IDF_TOOLS_PATH`、`ESP_IDF_VERSION`，以及 cmake / ninja / 交叉工具链的
PATH 一并交给编译子进程。所以用系统里任意一个 python 启动都可以：

```bat
python hardware/sets/build.py
```

跟着菜单走即可：输入编号或版型 id。

不想交互的话直接指定版型并跳过确认：

```bat
python hardware/sets/build.py --board yh-cam --yes
```

第一次拿到板子、只想验证「这套文件能不能被识别、能不能同步」时，用下面这条
（**不编译**，不会碰 ESP-IDF）：

```bat
python hardware/sets/build.py --board yh-cam --sync-only
```

要强制指定解释器就用 `--python`：

```bat
python hardware/sets/build.py --board yh-cam ^
  --python D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe
```

> **为什么要在意这件事**：PATH 里的 `python` 常常不是 IDF 的那个。本机就踩过
> `python` 解析到 `Python310-32`（32 位、没装 `rich_click`），固件的
> `scripts/build.py` 会用 `sys.executable` 把解释器一路传下去，于是报
> `No module named 'rich_click'` / `idf.py was not spawned within an ESP-IDF shell`。
> 现在脚本会自动切到 IDF venv，不再受 PATH 里是哪个 python 影响。编译前会打印
> 实际使用的 `IDF_PATH` / `IDF_TOOLS` / `IDF python` / 工具链目录数，方便核对。

---

## 2. 可用版型

| id | 名称 | 目标 | 引脚 |
|---|---|---|---|
| `yh-154tft-wifi` | 屿禾小方块 1.54 寸 TFT（Wi-Fi） | esp32s3 | ✅ 已验证 |
| `yh-big-ili9341` | 第二代大屏幕（ILI9341 2.8 寸 + ES8311） | esp32s3 | ⚠️ **未验证** |
| `yh-cam` | 屿禾 AI Camera（摄像头版） | esp32s3 | ✅ 已验证 |
| `yh-n16r8-st7789` | 第一代小方块（ESP32-S3-N16R8 / ST7789） | esp32s3 | ✅ 已验证 |

每个版型的详细引脚表与已知坑点，看 `boards/<id>/README.md`。
随时用 `python hardware/sets/build.py --list` 查看当前实际扫到的版型。

---

## 3. 目录结构

```
hardware/sets/
├── README.md            ← 本文件（用户导航）
├── SPEC.md              ← 版型作者规范（要新增版型先读它）
├── build.py             ← 编译入口（选版型 → 同步 → 注册 → 编译 → 归档）
├── flash.py             ← 烧录入口（多线程探测 COM 口 → esptool 烧录）
├── xiaozhi-esp32/       ← 固件源码副本 <FW>（仅源码；build/ 与 managed_components/ 不入库）
├── boards/
│   ├── yh-cam/          ← 一个版型一个目录
│   │   ├── set.json     ← 菜单数据源（build.py 读）
│   │   ├── config.json  ← 固件 scripts/build.py 读
│   │   ├── config.h     ← 引脚与参数宏
│   │   ├── <board>.cc   ← 板实现
│   │   └── README.md    ← 版型说明
│   └── ...
└── out/<id>/            ← 编译产物归档（--no-archive 可跳过）
```

**同步规则**：`build.py` 把 `boards/<id>/` 下除 `set.json`、`README.md` 之外的
`*.c / *.cc / *.cpp / *.h / *.hpp / *.json` 同步到
`<FW>/main/boards/yuhe/<id>/`。所以文档随便写，只有源码和 JSON 会进固件。

---

## 4. build.py 做了什么

```
[0/4] 准备依赖       <FW>/managed_components 缺失时，从上游目录本地拷贝一份
[1/4] 同步版型文件   boards/<id>  ->  <FW>/main/boards/yuhe/<id>
[2/4] 注册版型       幂等改写 <FW>/main/Kconfig.projbuild 与 main/CMakeLists.txt
                    的 SETS-BOARDS 标记块
[3/4] 编译           调用 <FW>/scripts/build.py <board_dir> --name <build_name>
[4/4] 归档           ->  hardware/sets/out/<id>/
     收尾           打印下一步该执行的 flash.py 命令（本脚本不烧录）
```

第 2 步是**幂等**的：它只替换 `# >>> SETS-BOARDS-BEGIN >>>` 和
`# <<< SETS-BOARDS-END <<<` 之间的内容，标记块之外一个字都不动；
内容没变时会输出「标记块内容已是最新，未改动」。
首次改写前会备份到 `<原文件>.bak-sets`，并打印改动的 diff 摘要。

注册的位置与内容：

- `main/Kconfig.projbuild`：块插在 `choice BOARD_TYPE` 的 `endchoice` **之前**，
  每个版型 3 行（`config` 前 4 空格，`bool` / `depends on` 前 8 空格）
- `main/CMakeLists.txt`：块插在 board 选择链（`if(CONFIG_BOARD_TYPE_BREAD_COMPACT_WIFI)`
  起）最后的 `else()` 之前；当前固件这条链没有 `else()`，所以落在闭合 `endif()` 之前。
  每个版型 **4 行**：

  ```cmake
  elseif(CONFIG_BOARD_TYPE_YUHE_SET_CAM)
      set(BOARD_DIR "yuhe/yh-cam")
      set(BUILTIN_TEXT_FONT font_noto_sans_basic_20_4)
      set(BUILTIN_ICON_FONT font_material_symbols_20_4)
      set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)
  ```

  `DEFAULT_EMOJI_COLLECTION` 默认 `noto-color-emoji_64`（与固件里 yuhe 系列现有分支
  一致），可在 `set.json` 里用可选的 `emoji_collection` 覆盖。

第 4 步归档的文件（文件名前缀为 `build_name`）：

| 产物 | 用途 |
|---|---|
| `<name>-merged-binary.bin` | 合并好的单文件，可直接 OTA 或首次烧录 |
| `<name>-xiaozhi.bin` | 应用分区 |
| `<name>-generated_assets.bin` | assets 分区（字体/图标），**首次必须全量烧录** |
| `<name>-bootloader.bin` | bootloader |
| `<name>-partition-table.bin` | 分区表 |
| `<name>-ota_data_initial.bin` | OTA data 初始内容 |

### 常用参数

| 参数 | 作用 |
|---|---|
| `--board <id>` | 直接指定版型，跳过交互选择 |
| `--list` | 只列出版型就退出 |
| `--sync-only` | 只做同步与注册，不编译（无需 ESP-IDF） |
| `-y` / `--yes` | 跳过所有确认，含引脚未验证警告 |
| `--no-archive` | 编译后不归档 |
| `--fw-arg=<ARG>` | 额外透传给 `<FW>/scripts/build.py`，可重复。**必须用等号**：`--fw-arg=--zip` |
| `--fw-root <DIR>` | 手动指定固件根目录（默认用 sets 自带副本 `sets/xiaozhi-esp32/`） |
| `--no-color` | 关闭彩色输出（日志重定向到文件时用） |

烧录不在这里，见下一节。

---

## 4.1 烧录：flash.py

独立的烧录脚本，核心是**多线程并行探测 COM 口**：宿主机「枚举到串口」并不等于
「口上有设备」，也不等于「能打开」（可能被串口监视器占用）。串行逐个 `open()`
的做法 N 个口要等 N × 超时（实测蓝牙虚拟口的 `open()` 能卡住 5～9 秒）；
`flash.py` 一个口起一个线程，整体耗时 ≈ 最慢的那个口，而且谁先探完先打印谁。

```bat
python hardware/sets/flash.py                    :: 探测串口并烧录（唯一设备时问一句）
python hardware/sets/flash.py --board yh-cam     :: 指定版型（校验产物是否对得上）
python hardware/sets/flash.py --list             :: 只探测列出，不烧录
python hardware/sets/flash.py --identify         :: 探测 + 复位读 ROM 日志识别芯片型号
python hardware/sets/flash.py --json             :: 探测结果输出 JSON（供脚本调用）
python hardware/sets/flash.py --port COM18 -y    :: 指定串口，跳过确认直接烧
python hardware/sets/flash.py --baud 921600      :: 提高烧录波特率
```

探测结果长这样（`[在线]` 表示口能打开、后面确实挂着设备）：

```
[探测] 枚举 3 个串口 → 并行探测 1 个 / 1 线程，单口超时 0.6s
  COM3     [跳过]  蓝牙链接上的标准串行 (COM3)  蓝牙虚拟串口，默认跳过
  COM4     [跳过]  蓝牙链接上的标准串行 (COM4)  蓝牙虚拟串口，默认跳过
  COM18    [在线]  USB-SERIAL CH340K (COM18)  数据=61B  样本='I (51458) SystemInfo: ...'  610ms
```

状态共四种：`[在线]` 能打开、`[被占用]` 被别的程序占着、`[打不开]` 驱动层报错、
`[跳过]` 蓝牙虚拟口。

| 参数 | 作用 |
|---|---|
| `--port COMx` | 指定串口，跳过探测（仍会尝试校验） |
| `--baud N` | 烧录波特率，默认 `460800` |
| `--list` | 只探测列出串口状态，不烧录 |
| `--json` | 以 JSON 输出探测结果（隐含 `--list`），诊断信息走 stderr 不污染 stdout |
| `--identify` | **会复位目标板**：读 ROM 启动日志判定是不是 ESP32、是哪一款 |
| `--timeout SEC` | 单口探测超时，默认 `0.6` |
| `--jobs N` | 探测线程数上限，默认 `8` |
| `--include-bluetooth` | 把蓝牙虚拟口也纳入探测（默认跳过） |
| `-y` / `--yes` | 跳过烧录确认 |
| `--board <id>` | 指定版型，用于提示 + 校验 `build/` 里的产物是不是这个版型编的 |
| `--no-reexec` | 缺 pyserial 时不自动换解释器（只枚举串口） |

烧录细节（与固件自带 `yh_flash.bat` 同源）：

- 优先按 `<FW>/build/flash_args` 烧录；若该文件不含 assets 分区，
  自动退回**显式全量烧录**：`bootloader + 分区表 + ota_data + app + assets(0x800000)`
- 固定参数：`esp32s3` / `460800` 波特 / `dio` / `16MB` / `80m`
- **assets 分区首次必须全量烧录**，之后 OTA 只刷 app 分区
- 产物不存在时会直接告诉你去跑 `build.py`，不会瞎烧

> 烧录是有副作用的物理操作，所以 `-y`/`--yes` 必须由你显式给出；
> 不加时脚本会问一句「是否把 …… 烧录到 COMxx？[y/N]」。
>
> 探测本身**不会复位设备**（打开串口前把 DTR/RTS 都置为不激活，避开经典自动复位
> 电路）；只有 `--identify` 会主动复位，且复位后仍以正常运行模式启动、不会停在
> 下载模式。

---

## 5. `pins_verified` 是什么

`set.json` 里的 `pins_verified` 表示**这套引脚有没有经过实物核实**。

- `false` 的版型在菜单里会显示 `[!]` 前缀和「引脚: 未验证」，
  选中后会打印一屏红色警告，**要求你手动输入 y 才能继续**（除非加了 `--yes`）。
- 这是有意设计的门槛：这种版型的引脚来自固件字符串推断，可能根本没有原理图，
  照着烧上去可能只是屏幕不亮，也可能把 I2S 音频接到错误的外设上。

**看到 `[!]` 请先去读 `boards/<id>/README.md`**，里面会列出
哪些引脚是原资料给的、哪些是作者补的、以及怎么去核实。
核实通过后把 `set.json` 里的 `pins_verified` 改成 `true`。

---

## 6. 如何新增一个版型

1. `mkdir hardware/sets/boards/<new-id>`
2. 按 `SPEC.md` 第 1 节放齐五件套：`set.json`、`config.json`、`config.h`、
   `<board>.cc`、`README.md`
3. `python hardware/sets/build.py --list` 确认能被扫到
   （扫不到就看有没有必填字段写错，脚本会直接把原因打印出来）
4. `python hardware/sets/build.py --board <new-id> --sync-only` 验证同步与注册
5. 再跑一次完整编译
6. `python hardware/sets/flash.py --list` 确认能看见设备，再 `flash.py` 烧进去

`set.json` 的 12 个必填字段：`id`、`name`、`description`、`manufacturer`、
`target`、`board_dir`、`kconfig_symbol`、`kconfig_prompt`、`text_font`、
`icon_font`、`build_name`、`pins_verified`。
可缺省：`sdkconfig_append`、`notes`、`cmake_extra`、`emoji_collection`。

几个容易踩的校验规则：

- `id` 必须与目录名完全一致
- `manufacturer` 固定 `yuhe`，且必须是 `board_dir` 的第一段
- `board_dir` 形如 `yuhe/<id>`
- `kconfig_symbol` 全大写、字母开头、**不带** `CONFIG_` 前缀，且全局不能重复
- `build_name` 全局不能重复
- 类名不要与 `<FW>/main/boards/` 下其它板重名（sets 下统一 `YhSet` 前缀风格）

详细规范见 `SPEC.md`。

---

## 7. 常见问题

**Q：改了 Kconfig / 切了版型，编译报 Kconfig 符号不被识别**
删掉 `<FW>\build` 目录再重跑：

```bat
rmdir /s /q G:\demo\21_xiaozhi\hardware\sets\xiaozhi-esp32\build
python hardware/sets/build.py --board yh-cam --yes
```

sdkconfig 的变更在老 build 目录里不会自动生效，这是 IDF 的常见行为。

> ⚠️ **切换版型必须全量重编**：`<FW>/build` 是所有版型共用的**单一**构建目录，
> 切换版型后 sdkconfig 会整体改变，Kconfig 可能不生效。
> 脚本在开始编译前会检查 `build/xiaozhi-build.sdkconfig.defaults`，
> 发现上次编译的是别的版型时会主动中文告警并给出删除命令——看到就照做。
> 另外切换前记得先归档（默认已归档到 `out/<id>/`）或自行备份产物。

**Q：提示「未检测到可用的 ESP-IDF 编译环境」**
先从上面那三种自动探测里找；全找不到时会打印下面两条路。手动激活参考固件自带的
`build_yuhe_cam.bat`：

```bat
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
```

或者直接把 IDF venv 的 python 指给脚本，连激活都省了：

```bat
D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe hardware/sets/build.py --board yh-cam
```

路径按你本机实际位置调整。只是同步/注册的话加 `--sync-only`，不需要 IDF。

> 注意 `IDF_TOOLS_PATH` 是 `D:\INSTALL\esp`（**不是** `...\esp\tools`）。这里工具装在
> `$IDF_TOOLS_PATH/tools/<name>/<version>`，所以少了 `\tools` 才是对的——本机用
> `idf_tools.py check` 实测验证过。官方生成的 `Microsoft.v6.1.PowerShell_profile.ps1`
> 里写的是 `...\esp\tools`，属于 eim 的命名偏差，别照抄。

**Q：报 `No module named 'rich_click'`**
说明 `idf.py` 被非 IDF 的 python 拉起来了。脚本已自动规避；若在别处遇到，
用 IDF venv 的 python 重跑，或加 `--python` 指定。

**Q：报 `Configuring incomplete` 且日志里有 `component_requires.temp.cmake`**
空/半成品 `build/` 目录下的已知抖动，再跑一次通常就好；稳定复现就删掉
`<FW>\build` 全量重配。

**Q：中文输出乱码**
脚本默认 UTF-8 输出，并会自动开 Windows 虚拟终端；GBK 控制台下会降级为
ASCII 而不是抛异常。如果还是乱，试试 `--no-color`，或把输出重定向到文件。

**Q：产物怎么烧**
先探测看看口上有没有设备（不烧、不复位）：

```bat
python hardware/sets/flash.py --list
```

确认后在烧：

```bat
python hardware/sets/flash.py --board <id>          :: 探测 + 烧录
python hardware/sets/flash.py --port COM18 -y       :: 指定串口直接烧
```

手工烧也行：`merged-binary.bin` 可直接用于 OTA 或首次烧录，
**assets 分区（`generated_assets.bin`）首次必须全量烧录**。
注意固件自带的 `yh_flash.bat` 硬编码指向上游目录
`hardware\small_screen_camera\xiaozhi-esp32`，用 sets 副本编译时请走 `flash.py`。

**Q：`flash.py` 说没有检测到可用设备，但我确实插着板子**
先看它是哪一种状态：

- `[跳过]` —— 蓝牙虚拟串口，本来就不是可烧录目标（想强行探测加 `--include-bluetooth`）
- `[被占用]` —— 关掉串口监视器 / 另一个烧录会话（同一串口同一时刻只能一个程序占用）
- `[打不开]` —— 串口驱动没装好，或换根能传数据的 USB 线
- 一个口都没枚举到 —— 大概率是纯充电线，或驱动没装

**Q：`flash.py` 提示当前解释器没有 pyserial**
脚本会自动改用 ESP-IDF venv 的 python 重跑（pyserial 与 esptool 都装在那里），
一般不用管。要手动指定就加 `--python D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe`。

**Q：可以直接改 `<FW>/main/` 下的文件吗**
不可以。`<FW>/main/Kconfig.projbuild`、`main/CMakeLists.txt` 以及
`main/` 下除 `boards/yuhe/<id>/` 之外的任何文件，都由 `build.py` 统一维护，
版型作者碰都不要碰。要改就改 `boards/<id>/` 下你自己的文件，然后重跑脚本。

**Q：源目录删掉的文件，目标目录里还有残留**
脚本会列出残留文件但**不会自动删除**（怕误删别人的成果），请你确认后手工清理。
