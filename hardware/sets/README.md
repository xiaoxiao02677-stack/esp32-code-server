# 小智固件 · 多版型适配中心（hardware/sets）

一套固件源码 + N 套版型配置。在这里选一个版型，`build.py` 会自动完成
**同步 → 注册 → 编译 → 归档产物**，你不需要手工去改固件源码树里的任何文件。

**构建 / 烧录 / 诊断是三个脚本，职责分开：**

| 脚本 | 职责 |
|---|---|
| `build.py` | 选版型 → 同步 → 注册 → 编译 → 归档产物。**不做任何串口操作** |
| `flash.py` | **多线程并行探测 COM 口** → 复位线序识别 → 把芯片送进下载模式 → 烧录 → **烧录前后自检 + 回读校验 + 启动检查**。两种方式：`--mode idf`（直接吃 `build/flash_args`，最省事）/ `--mode staged`（逐段 + 切块，默认）。**不编译** |
| `diag.py` | **只读**回读设备 flash，与 `<FW>/build` 产物逐字节比对，判定「烧录问题 / 产物问题」。**不写不擦** |

先 `build.py` 出产物，再 `flash.py` 烧进去；只想烧已有的产物就直接跑 `flash.py`；
刷完起不来（例如屏幕不亮、无限重启）就先跑 `diag.py` 体检。

**屏幕界面**：四个 `yh-*` 版型统一使用屿禾「小柚」皮肤（共享层
`main/display/yh_skin/`，上电首帧即品牌画面，不使用 xiaozhi 原生 UI）。
布局规格、开机时间线、状态映射与踩坑清单见 **[`UI_SKIN.md`](UI_SKIN.md)**。

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
python hardware/sets/flash.py --manual           :: 手动进下载模式（按住 BOOT + 点 RST）
python hardware/sets/flash.py --reset none -y    :: 设备已手动进下载模式，不再复位
python hardware/sets/flash.py --port COM18 --clean   :: 先整片擦除，再全量重烧
python hardware/sets/flash.py --port COM18 --baud 460800   :: 想快点（线材好时用，默认 230400）
python hardware/sets/flash.py --port COM18 --chunk-size 512K  :: 大镜像还断就用更小的块
python hardware/sets/flash.py --port COM18 --skip-assets   :: 跳过 3.9MB assets，先确认 app 能起来
python hardware/sets/flash.py --single           :: 退回「一次会话写完所有镜像」的旧行为
python hardware/sets/flash.py --port COM18 --mode idf      :: 用 build/flash_args 一次写完（最省事）
python hardware/sets/flash.py --port COM18 --mode staged   :: 强制走逐段加固流程
python hardware/sets/flash.py --port COM18 --mode diag     :: 只回读体检，不写 flash
```

### 两种烧录方式（`--mode`，交互式终端会弹菜单）

不给 `--mode`、又是在真终端里跑，脚本会先问一句：

```
请选择烧录方式（直接回车 = 1）：
  1) idf.py 快速烧录   —— 直接用 build/flash_args 一次写完，最省事
  2) 分段加固烧录      —— 逐段写 + 1MB 切块 + 双端校验，链路不稳时用
  d) 只体检不烧录      —— 回读设备内容与产物逐字节比对（不改 flash）
```

| 方式 | 做什么 | 什么时候用 |
|---|---|---|
| `idf` | 直接用项目里的 `build` 目录：读 `build/flash_args`，**一条命令**写完所有镜像。标准接线时就是真的 `idf.py flash` | 日常烧录，最省事 |
| `staged` | 逐段 + 切块 + 探活 + 自愈，断了只补那一段 | 链路不稳、assets 老断链、排查启动问题（默认） |
| `diag` | 只回读比对，不写 flash（等价于 `diag.py`） | 怀疑「烧了没生效」时先取证 |

两种方式**共用同一套闸门**：烧录前核对地址与分区表同源、烧录后回读比对 + 复位读串口。

> **反相接线的板子（本项目 1.54 寸板）走 `idf` 时用「等价写法」**：`idf.py` 的
> `--before` 是编译期从 `sdkconfig` 的 `CONFIG_ESPTOOLPY_BEFORE` 固化的，命令行改不了
> （实测 `write-flash --before no-reset` 被 esptool 拒绝：`No such option '--before'`，
> 而 `--extra-args` 只能把参数追加在 `write-flash` **后面**）。它那次 `default-reset`
> 在这类板子上会把芯片留在应用态，必然报 `Invalid head of packet (0x49)`。所以这种
> 板子改用「同一份 `build/flash_args` + 一条 `write-flash`」，只把那次复位换成脚本
> 按正确时序送进下载模式 —— 写入内容、地址、速度都和 `idf.py flash` 一致。

`idf` 模式默认沿用 IDF 的快速重烧（只写与上次成功烧录不同的扇区，写完 MD5 校验，
校验不过会自动全量重写）；要每次都全量写就加 `--idf-all`。

**默认逐段写入**：一个镜像一个 esptool 会话，顺序按地址升序 ——
`bootloader(0x0) → 分区表(0x8000) → otadata(0xd000) → app(0x20000) → assets(0x800000)`。
每段写之前先 `flash-id` 探活；失败按 `波特率降档 → 换复位线序` 自愈。
大镜像再按 **1MB 切块**（app 3 块、assets 4 块），崩一次只重写 1MB，不用从头再来。

`assets` 特意排在最后：它最大（3.9MB）也最容易断，但它断了设备照样能启动 ——
缺的只是字库 / 表情 / 唤醒词。旧顺序（照 `flash_args` 书写顺序）把 assets 排在
app **前面**，assets 一断 app 就一个字节也没写，设备留着上一次的旧 app，看起来
像「烧了但没生效」。

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
| `--baud N` | 烧录波特率，默认 `230400`。`460800` 更快，但长线 / 劣质线材 + 4MB 大镜像时容易断链（实机踩过） |
| `--list` | 只探测列出串口状态，不烧录 |
| `--json` | 以 JSON 输出探测结果（隐含 `--list`），诊断信息走 stderr 不污染 stdout |
| `--identify` | **会复位目标板**：读 ROM 启动日志判定是不是 ESP32、是哪一款，还会报告复位线序 |
| `--timeout SEC` | 单口探测超时，默认 `0.6` |
| `--jobs N` | 探测线程数上限，默认 `8` |
| `--include-bluetooth` | 把蓝牙虚拟口也纳入探测（默认跳过） |
| `-y` / `--yes` | 跳过烧录确认，也不再弹方式选择菜单（非交互式默认走 `staged`） |
| `--mode {idf,staged,diag}` | 烧录方式：`idf`=用 `build/flash_args` 一次写完；`staged`=逐段加固（默认）；`diag`=只体检。不指定且是交互式终端时会让你选 |
| `--board <id>` | 指定版型，用于提示 + 校验 `build/` 里的产物是不是这个版型编的 |
| `--reset {auto,esptool,reversed,none}` | 烧录前如何让芯片进下载模式，默认 `auto`（自动识别线序） |
| `--manual` | 打印手动进下载模式步骤并等回车，随后按 `no-reset` 连接 |
| `--before MODE` / `--after MODE` | 直接指定 esptool 的 `--before` / `--after`。`--after` 默认 `auto`：反相板用 `no-reset`，标准板用 `hard-reset` |
| `--attempts N` | 每段连接的**探活次数**，默认 `3`；用完降速再来一轮，仍未成会换复位线序 |
| `--single` | 一次性写完所有镜像（默认逐段写，断了只补那一段） |
| `--skip-assets` | 不写 assets 分区（3.9MB）。排查启动问题时跳过最慢的一段 |
| `--only NAME` | 只写指定镜像（逗号分隔，可用 `bootloader` / `partition-table` / `otadata` / `app` / `assets`）。例：`--only assets` 只补资源分区 |
| `--chunk-size BYTES` | 大镜像切块大小，默认 `1M`（可写 `512K` / `1M`）。块越小越不容易断，断了只重写这一块 |
| `--no-chunk` | 关掉切块（大镜像整段写），只在链路非常稳时用 |
| `--idf-all` | `idf` 模式强制全量写（`idf.py flash --all`），关掉 IDF 的快速重烧 |
| `--clean` | 烧录前先 `erase-flash` 整片擦除：板子里是别的固件、或分区表被外来固件改过时用 |
| `--no-verify` | 跳过烧录后的回读比对与启动检查（默认都做） |
| `--boot-check SEC` | 烧完复位并读串口的时长，默认 `8` 秒；`0` = 不做启动检查 |
| `--no-reexec` | 缺 pyserial 时不自动换解释器（只枚举串口） |

### 为什么会「连接失败」「烧录失败」，以及现在怎么兜住

两条失败路径被分开处理，不再混成一句「连不上芯片」：

| 失败点 | 以前 | 现在 |
|---|---|---|
| **连接** | 直接拿 `write-flash` 试，失败就退出 | 每段写之前先用 `flash-id` **探活**（约 1.8 秒）：失败重试 3 次 → 降速再试 → 还不行就**换另一条复位线序**再试（自动识别偶尔认错，认对的那条会沿用到后面所有段） |
| **传输** | 一条命令写 5 个镜像，断一次全废 | 按地址升序逐段写；大镜像再按 **1MB 切块**，单块崩了只重写这 1MB。块边界与 4KB sector 对齐，相邻块不会互相擦掉 |

最坏情况下的重试组合是：`3 次探活 × 2 种线序 × 2~3 档波特率` —— 全用完才报错，
而且报错时会明确说清是"连接阶段没上去"还是"传输中途断了"，并给出下一步命令。

默认波特率从 `460800` 降到 `230400` 就是这个取舍：写 4MB 慢约一倍，但不赌线材。

### 刷完起不来？烧录前后各有一道闸

`flash.py` 默认在烧录**前**核对地址、烧录**后**核对内容和启动结果：

```
[自检] 烧录地址与分区表一致
  0x0         bootloader.bin                   15536 字节
  0x8000      partition-table.bin               3072 字节
  0xd000      ota_data_initial.bin              8192 字节
  0x20000     xiaozhi.bin                    2757424 字节
  0x800000    generated_assets.bin           4054873 字节
…
[烧录] 逐段写入：一个镜像一个 esptool 会话，某段断了只补这一段
  [1/5] bootloader.bin
  0x0         bootloader.bin                   15536 字节   @ 460800
        OK
  …
[校验] 回读刚写入的区域，与本地产物逐字节比对
  bootloader.bin             0x0         [一致] 全量（15536 字节）
  ota_data_initial.bin       0xd000      [信息] 已选中 ota_0（ota_seq=1）—— 设备启动过，属正常状态
  …
[启动检查] 复位设备并读 8 秒串口日志
  串口日志: '.ESP-ROM:esp32s3-20210327...rst:0x1 (POWERON)..boot:0x1b (SPI_FAST_FLASH_BOOT)..I (123) cpu_start: ...'
  设备已正常启动（读到了应用运行日志）
```

> `ota_data_initial.bin` 永远显示 `[信息]` 而不是 `[一致]`：它是全 `0xFF`（"从未 OTA
> 启动过"），而设备只要成功启动一次，bootloader 就会把 `ota_seq=1` 写进去表示"正在用
> ota_0"。按逐字节比对只会每次启动后误报，所以这里只报状态。

第一道闸解决的是**「分区表与 app 不同源」**这一类死机：分区表写的是 16MB 布局
（`ota_0 @ 0x20000`），app 却按 4MB 布局写到了 `0x10000` —— bootloader 在
`0x20000` 根本找不到合法镜像（首字节不是 `0xE9`），于是按
`bootloader_utility.c` 里的 `bootloader_reset()` 自杀重启，观感就是**屏幕不亮 +
无限重启**。现在这种情况会在烧录前被直接拒掉：

```
[自检] 烧录地址与分区表对不上
        · xiaozhi.bin 要写到 0x10000，但分区表里没有任何分区起始于该地址
        · app 要写到 0x10000，而分区表里的 app 分区在 0x20000、0x410000 —— 布局不同源
```

第二道闸（启动检查）会明确回报 `已正常启动 / 在**循环重启**`：判定依据是
ROM 的 `ESP-ROM:` 横幅一定会打（ROM 代码，不受 sdkconfig 影响），8 秒里出现两次
以上就是在循环重启。

台账里已经有别的固件、或你不确定板子被谁刷过什么，直接加 `--clean`：先整片擦除
再全量写入，不给「残留分区表 + 外来 app」任何混用的机会。

### 写到一半断链：`No more data to read from the serial port`

这是**写入过程中链路断了**，不是"连不上芯片"。典型日志：

```
Writing 'generated_assets.bin' at 0x00800000...
Compressed 4054876 bytes to 2938793...
Writing at 0x00981b87 [========>          ]  32.3% 950272/2938793 bytes...
Hard resetting via RTS pin...
A fatal error occurred: No more data to read from the serial port.
```

逐条读：

- **`Hard resetting via RTS pin` 是收尾动作**，说明写入流程已经走到最后一步；
  在这块**反相接线**的板子上它拉的是 GPIO0（不是 EN），所以复位语义是反的，
  在收尾阶段等着读响应自然读不到 → 冒出 `No more data`。现在 `--after auto`
  对反相板改用 `no-reset`，改由脚本自己按正确时序复位。
- **进度条停在 32% 也可能已经写完**：esptool 的进度按"已发送的压缩字节"计，
  最后一屏常常来不及刷到 100%。
- **真正要确认的是「谁没写进去」**：跑 `diag.py`，它会逐段告诉你。实机遇到过
  app 段停在**上一次编译**的版本（`esp_app_desc` 时间戳对不上），原因就是旧流程
  把 3.9MB 的 assets 排在 app 前面，assets 一断 app 根本没轮到 —— 现在按地址升序，
  app 先落盘，assets 垫底。

按这个顺序处理（**前两条现在已经是默认行为**，正常情况直接跑第一条就行）：

```bat
python hardware/sets/flash.py --port COM18                     :: 逐段 + 1MB 切块 + 230400，断了自动重来
python hardware/sets/flash.py --port COM18 --chunk-size 512K   :: 还断就切更细
python hardware/sets/flash.py --port COM18 --baud 115200       :: 再降一档波特率
python hardware/sets/flash.py --port COM18 --skip-assets       :: 先跳过 3.9MB，确认应用能起来
```

反复断更可能是**供电**问题（写 4MB 时电流冲击最大）：换 USB 口、拔掉外设、
用带供电的 HUB、或先把背光调暗。

### 刷完还是不对？用 diag.py 回读体检

`diag.py` 是**只读**工具（不写、不擦、不改 eFuse，跑完把设备复位回运行态），
回答一个问题：**芯片里存的，和本地编出来的，是不是一回事？**

```bat
python hardware/sets/diag.py                     :: 自动探测串口 + 复位线序
python hardware/sets/diag.py --port COM18        :: 指定串口
python hardware/sets/diag.py --board yh-154tft-wifi --full-app   :: 连 app 全量比对
```

它回读 `flash-id`、`0x0`~`0x10000`（bootloader + 分区表 + otadata）、`0x20000`
（app 头部或全量）、`0x800000`（**assets 头 4KB + 尾 4KB**），与 `<FW>/build/*.bin`
逐字节比对，会指出**首个不同的偏移**，然后给结论：

> assets 尾部那 4KB 是关键：它对应资源的最后一段，实测出现过「assets 写到 95%
> 就断、尾部 192KB 全 `0xFF`」而设备照样能启动（排在 app 后面），此时缺的是
> 部分表情 / 字库。`diag.py` 现在能直接把它揪出来。

| 结论 | 含义 | 下一步 |
|---|---|---|
| `[一致]` | 写进去的和编出来的一样 | 不是烧录问题 → 打开 bootloader 日志（`CONFIG_BOOTLOADER_LOG_LEVEL_INFO=y`）看它卡在哪 |
| `[空白]`（全 `0xFF`） | 这块区域根本没写进去 | `flash.py --clean` 全量重烧 |
| `[另一份构建]` | 设备上那份 app 来自**另一个编译批次**（`esp_app_desc` 的版本/日期/时间对不上） | 不算写坏，能启动；想让设备与 `build/` 完全对齐就重烧一次 |
| `[不一致]` + 首个不同偏移 | 写了一半 / 写到了别处 / 板子里是别的固件 | 同上，`--clean` 重烧后再跑 diag 复核 |
| `[信息]`（otadata） | 只是状态播报，不判对错 | 无 |

`[另一份构建]` 这个判定很关键：换一次编译，镜像头 `+0x4` 的入口地址、`+0x1c` 的
校验和、以及 `esp_app_desc` 里的编译时间全都会变，**逐字节比对必然不同**。
拿它去区分「写坏了」和「只是编了两次」，能把排查方向一次拨正 ——
实机就出现过「`+0x4` 差 8 字节」被误判成写坏，实际设备上是 21:22 那份、本地是
23:04 那份，同版型、同功能，只是两次编译。

### 复位线序：为什么这块板「按住 BOOT 也没用」

Espressif 参考设计里是 **DTR→GPIO0、RTS→EN**，esptool 的 `ClassicReset`
（就是 `--before default-reset`）按这个假定发时序。**本项目部分板子是反相接线
（DTR→EN、RTS→GPIO0）**，后果是：

- `--before default-reset` 只会让芯片**正常运行**（`boot:0x1b (SPI_FAST_FLASH_BOOT)`），
  接着应用日志刷到串口上，日志首字节 `I`(0x49) 被 esptool 当成数据包包头，于是报
  `Failed to connect to ESP32-S3: Invalid head of packet (0x49)`；
- **「按住 BOOT 开机」救不了它** —— esptool 连接阶段还会自己再复位一次，
  那一次复位就把手动进下载模式的结果冲掉了。

所以 `flash.py` 默认（`--reset auto`）会先复位一两次把线序认出来：

```
[复位] 识别本板复位线序（最多复位两次，约 3~5 秒）
  已按反相时序送进下载模式    ESP-ROM:esp32s3-20210327..boot:0x13 (DOWNLOAD(USB/UART0))..waiting for
```

识别结果决定两条路：

| 线序 | 行为 |
|---|---|
| **反相**（本项目这类板） | 脚本按镜像时序把芯片送进下载模式，再用 `--before no-reset` 交给 esptool |
| **标准**（绝大多数开发板） | 什么都不改，仍旧交给 esptool 的 `default-reset` |

要绕开自动识别：`--reset esptool`（强制老行为）、`--reset reversed`（强制脚本复位）、
`--reset none`（不复位，用于你已手动进下载模式）、`--before <MODE>`（直接透传给 esptool）。

适配器根本不支持控制 DTR/RTS（少数 USB 转串口），或线路没接 EN/GPIO0 时，
用 `--manual`：脚本会打印「按住 BOOT → 点 RST → 松开 BOOT」并等你按回车，
再用 `no-reset` 连上去。

## 4.2 烧录细节

烧录细节（与固件自带 `yh_flash.bat` 同源）：

- 优先按 `<FW>/build/flash_args` 烧录；若该文件不含 assets 分区，
  自动退回**显式全量烧录**：`bootloader + 分区表 + ota_data + app + assets(0x800000)`
- 固定参数：`esp32s3` / `460800` 波特 / `dio` / `16MB` / `80m`；`flash_args` 里已写明的
  参数不会重复追加
- **assets 分区首次必须全量烧录**，之后 OTA 只刷 app 分区
- 产物不存在时会直接告诉你去跑 `build.py`，不会瞎烧
- 连不上时（esptool 返回码 2）脚本会**回读串口**告诉你设备此刻在干什么：
  在读应用日志 = 没进下载模式；安静 = 已在下载模式（那就该怀疑波特率/线材）

> 烧录是有副作用的物理操作，所以 `-y`/`--yes` 必须由你显式给出；
> 不加时脚本会问一句「是否把 …… 烧录到 COMxx？[y/N]」。
>
> 探测（`--list` / 默认那次快速探测）本身**不会复位设备**（打开串口前把 DTR/RTS
> 都置为不激活，避开经典自动复位电路）；会复位设备的只有 `--identify`
> 和真正烧录前的那一步线序识别。`--identify` 复位完会把设备还原成正常运行状态。

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

**Q：报 `A fatal error occurred: Failed to connect to ESP32-S3: Invalid head of packet (0x49)`**
**0x49 就是字符 `I`**，是应用日志（`I (123) Tag: ...`）的首字节 —— 说明芯片在跑应用、
根本没进下载模式，esptool 把日志当成了应答包。这是**复位线序**问题，不是线材问题，
也不是「没按住 BOOT」：按住 BOOT 也无效，因为 esptool 连接时还会自己再复位一次。

`flash.py` 默认的 `--reset auto` 已经能处理（自动识别 + 自己送进下载模式），
直接重跑即可：

```bat
python hardware/sets/flash.py --board <id>
```

如果报错信息不一样（比如 `No serial data received`、`The chip may not be in
bootloader mode`），或者自动识别报「未能识别复位线序」，就手动走一遍：

```bat
python hardware/sets/flash.py --manual
```

它会提示你「按住 BOOT → 点一下 RST → 松开 BOOT」，然后按回车继续。也可以自己
手动进下载模式后加 `--reset none`。

想确认这块板到底是哪种线序：

```bat
python hardware/sets/flash.py --list --identify --port COM18
```

输出里 `芯片=esp32s3  复位线序=反相` 就是反相板（由脚本送进下载模式），
`复位线序=标准` 则交给 esptool 自己复位。

**Q：刷完屏幕一直不亮 / 串口里在无限重启（`bootloader_reset at bootloader_utility.c:1163`）**
这通常不是固件写坏了，而是**板子里的内容与分区表不同源**。实机验证过的一种形态：

- 设备里的分区表是 **16MB 布局**（`ota_0 @ 0x20000`）；
- 而 app 却按 **4MB 布局**（`partitions/v2/4m.csv` 的 `factory` 分区，`0x10000`）写了进去。

于是 bootloader 在 `0x20000` 找不到合法 app 镜像（首字节必须是 `0xE9`，实际是一段
字符串），调用 `esp_rom_software_reset_system()` 自杀重启 →
`Saved PC: bootloader_reset at bootloader_utility.c:1163`、`rst:0x3 (RTC_SW_SYS_RST)`
一路循环，屏幕从头到尾不亮。`CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y` 时 bootloader
一句话都不打，看着就像「什么都没发生」。

先体检（**只读**，不写设备、不擦 flash）：

```bat
python hardware/sets/diag.py --board <id>
```

它回读 `0x0`~`0x10000`（bootloader + 分区表 + otadata）与 `0x20000`（app），与
`<FW>/build/*.bin` 逐字节比对，逐段给出 `[一致]` / `[空白]` / `[不一致]` 和**首个
不同的偏移**。只要有一段不一致，就整片擦除重烧：

```bat
python hardware/sets/flash.py --port COM18 --clean
```

`--clean` 先 `erase-flash` 清掉外来的分区表/固件残骸，再全量写入；随后 `flash.py`
会回读校验、复位读串口，直接回报「已正常启动」或「在循环重启」。

如果 diag 报全部 `[一致]` 却依然不启动，那就不是烧录问题 —— 打开 bootloader 日志
再看它为什么退出：在版型 `config.json` 的 `sdkconfig_append` 里加
`CONFIG_BOOTLOADER_LOG_LEVEL_INFO=y`，重编重烧。

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
