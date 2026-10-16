# 立创实战派 S3 实机首跑排障手册

> ❌ **2026-10-16 07:55 根本性更正：板型从一开始就是错的。**
> 权威文档 `hardware/small_screen_camera/camera硬件信息.md` 明确写 **板级标识 `yuhe/cam`**，
> 仓库里 `main/boards/yuhe/cam` 与该文档**逐项吻合，无需任何改动**。
> 本项目已切到 `CONFIG_BOARD_TYPE_YUHE_CAM=y`，详见 **`docs/yuhe-cam-板型切换说明.md`**。
> **本文档整体作废**，仅作历史记录保留。

> ⚠️ **2026-10-16 04:29：本文档记录的代码改动已全部回退。**
> `main/boards/lckfb/szpi-esp32s3/config.h` 与 `lichuang_dev_board.cc` 已恢复为**上游原始版本**
> （config.h 62 行 / .cc 316 行；md5 `c6c3ae8e…` / `2e5c8896…`，与 camera / big_secreen /
> small_secreen / small_secreen_test 四棵原始树一致）。
> 回退前的版本备份在 **`hardware/small_screen_camera/_revert_backup_20261016_0429/`**。
> 下文（尤其 §8.5、§8.6 的 `spi_mode=0`、`LCD_PROBE_PHASE`、I2C 扫描等）**仅作排查记录，
> 与当前代码状态不符**，请勿据此判断现有代码。

> 适用板型：`lckfb/szpi-esp32s3`（ESP32-S3 / ESP-IDF v6.1 / xiaozhi-esp32 v2.5.1）
> 面向场景：**首次上电后摄像头报 0x106、触摸报 0x108**，按本文档重编译 → 看串口 → 判读 → 兜底排查。
> 决策依据与改动理由见 `docs/lckfb-szpi-摄像头板适配说明.md` §4.4；本文是**操作手册**，只讲"怎么做"。

---

## 0. 一分钟速查

```
1. 编译：build_lckfb_s3.bat            （改过板代码就加 clean）
2. 烧录：yh_flash.bat COM3              （必须含 assets 0x800000）
3. 看日志：monitor.bat COM3             （115200，务必看到 2.2s 之后）
4. 只搜 5 个关键字：
   I2C scan[            → 谁在总线上
   Camera power polarity resolved:   → bit2 极性定案
   PCA9557 bit0 (LCD/touch reset, active-low) held at ?  → 屏幕复位是否已释放（应为 1）
   touch: probe 0x??    → 触摸候选地址扫了谁
   Board init done (... camera=?)     → 摄像头最终状态
```

> 屏幕侧（背光 / 复位 / FPC 引脚）的权威依据已由用户提供的 TFT 原理图确认，见 §2。

三条核心判据先记住：

| 判据 | 一句话 |
| --- | --- |
| 摄像头 `0x106` | **不是驱动没编进去**，是 SCCB 对全部候选地址 NACK（没上电 / 没焊 / 排线断 / XCLK 没起） |
| 触摸 `0x108` | **地址 NACK**（不是超时、不是速率），即 0x38 这个设备此刻根本不在总线上 |
| bit2 | 已改为**自适应极性探测**（先试 1、扫不到再试 0），并且**已在触摸之前上电**，重烧后直接看日志定案 |

---

## 1. 本次故障时间线（现象 → 误判 → 真因 → 已做的修复）

### 1.1 现象

编译烧录成功，串口日志（115200）：

```
I (382) LcdDisplay: Turning display on / Initialize LVGL library / Added 2560KB LVGL pool in PSRAM
E ×9  lcd_panel.io.i2c: panel_io_i2c_tx_buffer(197): i2c transaction failed
E (462) FT5x06: esp_lcd_touch_new_i2c_ft5x06(161): FT5x06 init failed
E (472) FT5x06: Error (0x108)! Touch controller FT5x06 initialization failed!
I (492) cam_hal: cam init ok
E (502) camera: Detected camera not supported.
E (502) camera: Camera probe failed with error 0x106(ESP_ERR_NOT_SUPPORTED)
I (622) BoxAudioCodec: BoxAudioDevice initialized （ES8311/ES7210 四麦 TDM 正常）
I (632) SystemInfo: free sram: 186927 minimal sram: 85400
```

### 1.2 走过的误判（不要再踩）

| # | 当时的误判 | 为什么错 |
| --- | --- | --- |
| 1 | "0x106 = 摄像头驱动没编进固件，把 `CONFIG_CAMERA_OV2640` 等改成 y 就好" | 真正门控是 esp32-camera 的 **`CONFIG_<型号>_SUPPORT`**（本工程 15 个全 `=y`，早已编进去）；`CONFIG_CAMERA_<型号>` 属 esp_cam_sensor，而 legacy `esp_camera_init()` 路径**根本绕开它**，改它对本故障无效 |
| 2 | "bit2 是低有效上电，写 `SetOutputState(2,0)` 就上电了" | 若 0=上电，开机默认输出 `0x03`（bit2=0）时摄像头即带电，SCCB 必然应答——与"全地址 NACK"矛盾。反推应为**高有效** |
| 3 | "bit0 是低有效复位，LCD init 后要置 1 释放" | ⚠ **此条已被 TFT 原理图推翻**（见 §2）：RESET 经 R76(10k) 上拉到 3V3，**低电平复位**，因此 **1 才是释放态**。旧结论"0 是释放态"是凭 LCD 能点亮反推的，不可靠（即使被按住复位，背光仍会亮）。现已改为规范脉冲并在末态保持 **bit0=1** |
| 4 | "`camera=ready` 说明摄像头能用" | 旧代码 init 失败仍保留非空指针，`camera=ready` **不可信** |
| 5 | "`Backlight: Set brightness to 75` 说明 NVS 恢复成功" | 75 是**默认值**，不是从 NVS 读回的 |

### 1.3 真因（按可信度排序）

| 设备 | 真因 | 说明 |
| --- | --- | --- |
| 摄像头 ① | **XCLK 接在 NC 脚**（旧值 GPIO5，原理图 V1.0.1 标注 GPIO5 = NC） | `esp_camera.c`：`cam_init()`(L303) 早于 `camera_probe()`(L310)，S3 的 XCLK 由 `ll_cam.c:414 gpio_matrix_out(pin_xclk, CAM_CLK_IDX,…)` 输出 ⇒ **探测时时钟已在跑**。时钟没到传感器 ⇒ SCCB 从机不回应 ⇒ 全 NACK ⇒ 0x106。**已按原理图改到 GPIO17** |
| 摄像头 ② | **一直按在 power-down**（bit2=DVP_PWDN 被当"高有效使能"，探测后停在 1） | bit2 是 **DVP_PWDN，高=掉电**。改为 `EnableCameraPower()` 固定置 **0**，不再做极性自适应翻转 |
| 摄像头 ③ | 其次才是排线/焊接/模组供电 | 0x106 的唯一正解就是"所有候选 SCCB 地址都没 ACK" |
| 触摸 | **未焊 / 未供电 / 被复位钳住（~80%）**；实际型号是 CST816S(0x15) 或 GT911(0x5D)（~15%）；速率（~3%） | `0x108 = ESP_ERR_INVALID_RESPONSE`，**只由地址 NACK 产生**；超时是 `0x107`；速率/格式问题不会让**地址字节** NACK |
| 关联假设 | bit2 那一路电源可能是**摄像头与触摸的共用电源域**，而原流程里触摸探测发生在摄像头上电**之前** → 触摸没电 | 已调整初始化顺序验证 |

### 1.4 已落地的修复（重烧即生效）

| # | 修复 | 位置 |
| --- | --- | --- |
| 1 | **改为 `EnableCameraPower()`**：官方 wiki＋V1.0.1 原理图已确认 **bit2 = DVP_PWDN（高=掉电）**，直接固定置 **0**，**不再做"先试 1 再试 0"的极性自适应**（那个自适应会把摄像头按在掉电态当默认，正是根因②） | `lichuang_dev_board.cc` |
| 2 | 上电**提前到触摸之前**：`InitializeI2c()` → `EnableCameraPower()` → SPI/LCD → `InitializeTouch()` → … → `InitializeCamera()` | 板构造函数 |
| 3 | 回退 bit0 误改：LCD init 后**不再改写 bit0**，只打印观测值 | `InitializeSt7789Display()` |
| 4 | 触摸前加 `i2c_master_probe(0x38)` 前置探测：不在就直接跳过，消除 9 条 `panel_io_i2c_tx_buffer` 刷屏，并打印"0x38 NACK / 换 CST816S·GT911"提示 | `InitializeTouch()` |
| 5 | 摄像头失败日志改写：直接说明 0x106=全地址 NACK，并打印实测 bit2 / SCCB 引脚 / XCLK | `InitializeCamera()` |
| 6 | `Board init done` 的 camera 字段改真实状态：`camera=ready` 或 `camera=DISABLED(probe failed)` | 板构造函数 |
| 7 | **背光极性最终定为 `true`（低电平导通点亮）**：中途按 TFT 原理图改过 `false`，实机仍黑且与"Q2 栅极 R21(10k) 上拉 3V3 ⇒ P 沟道 ⇒ 拉低导通"矛盾；上游 pristine `config.h:39` 与 `camera板子信息.md:60` 均为 `true`。**以 `true` 为准**，若"亮度调高反而变暗"再改 `false` | `config.h` |
| 8 | **bit0 = LCD_CS（低电平选通），稳态 0**：`SetOutputState(0,1)` → 延时 10ms → `SetOutputState(0,0)`，释放后等 120ms 再 `esp_lcd_panel_init()`，再补 130ms（IDF 的 `panel_st7789_init()` 只发 `0x11 SLPOUT` 且仅等 100ms、**不发 `0x29`**）。打印 `bit0 (LCD_CS / reset-release, active-low) = 0 (selected)`。⚠ 原理图备注确认"LCD_CS：IO 扩展芯片输出，非 ESP32-S3 原生 GPIO" | `InitializeSt7789Display()` |
| 9 | **触摸改多型号自动识别**：依次 probe `0x38` FT5x06 / `0x5D`·`0x14` GT911 / `0x15` CST816S / `0x55` ST7123 / `0x5A` CST9217，命中即初始化，全失败**不阻塞开机** | `InitializeTouch()` |
| 10 | 摄像头供电保持 §1.4-1 的自适应极性探测（bit2 先试 1 再试 0；两轮不命中按反推默认保持 bit2=1 并告警） | `PowerOnCameraWithPolarityProbe()` |

> 第 7/8/9 项的硬件依据来自用户提供的 TFT 原理图（FPC 座 AFC01-S14FCC-00），详见 §2。

### 1.5 全板原理图校准（ESP32-S3 V1.0.1，板名"摄像头"）

> 用户随后提供了**完整全板原理图说明**，其优先级**高于** §2 的 TFT 片段图和所有旧档案。
> 全板图把摄像头 DVP 引脚**几乎全部推翻**（详见下表），并确认了 bit0=LCD_CS 的结论。

**已确认一致、无需改动的部分（好消息）**

| 模块 | 原理图 | 代码 | 结论 |
| --- | --- | --- | --- |
| TFT SPI | MOSI 40 / SCLK 41 / DC 39 / BL 42 | 同 | ✅ 一致 |
| LCD_CS | "IO 扩展芯片输出，非 ESP32-S3 原生 GPIO" | bit0，稳态 0 | ✅ 结论获终局确认 |
| I2C | SDA 1 / SCL 2 | 同 | ✅ 一致 |
| I2S | MCLK 38 / WS 13 / BCLK 14 / DIN 12 / DOUT 45 | 同 | ✅ 一致 |
| 音频 ADC 地址 | ES8720 @**0x41**(7-bit) | `0x82`(8-bit 写) = 0x41 | ✅ 地址一致，仅型号名不同，驱动沿用 ES7210 |
| 摄像头掉电 | DVP_PWDN = IO 扩展输出 | bit2=0 使能 | ✅ 一致 |

**已按原理图重映射的 DVP 引脚（`config.h`）**

| 信号 | 旧(错) | 新 | 信号 | 旧(错) | 新 |
| --- | --- | --- | --- | --- | --- |
| XCLK | 5 (NC!) | **17** | D3 | 17 | **6** |
| PCLK | 7 | **16** | D4 | 15 | **8** |
| HREF | 46 | **18** | D5 | 6 | **9** |
| VSYNC | 3 | **21** | D6 | 4 | **11** |
| D0 | 16 | **7** | D7 | 9 | **15** |
| D1 | 18 | **4** | D2 | 8 | **10**（⚠ 暂定） |

**改动后空出的脚**：GPIO3（原理图=用户按键）、GPIO46 —— 这两个现在**没有**任何驱动占用，音量键若要恢复只能接它们。

---

## 2. 屏幕原理图校准（SPI TFT FPC AFC01-S14FCC-00）

> **本章为屏幕侧的权威依据**，来自用户提供的 TFT 接口原理图，**覆盖此前所有基于"档案文字 / 点亮现象反推"的猜测**（含 §1.2-3 的旧 bit0 结论）。
> 结论：屏幕是 **SPI 接口 TFT 彩屏**，FPC 座 `AFC01-S14FCC-00`（FPC4），供电 **3V3**；FPC 为 16pin 座、**实际使用 15 脚**。

### 2.1 FPC 引脚映射表（照抄原理图，权威）

| FPC 脚号 | 信号 | ESP32 / 网络 | 说明 |
| --- | --- | --- | --- |
| FPC5 | LEDA | 背光阳极，经 R20(10Ω) 限流 | 由 Q2 驱动，见 §2.2 |
| FPC6 | RESET | 经 R76(10k) 上拉至 3V3 | **低电平复位**；原理图备注 **未直连 ESP32**，图内未接到 ESP32（需额外接线） |
| FPC7 | LCD_DC | **GPIO39** | 数据/命令选择 |
| FPC8 | LCD_MOSI | **GPIO40** | SPI MOSI（单向，无 MISO） |
| FPC9 | LCD_SCK | **GPIO41** | SPI 时钟 |
| FPC10 | 3V3 | 电源 | 屏供电 |
| FPC11 | 3V3 | 电源 | 屏供电（与 FPC10 并联） |
| FPC15 | GND | 地 | — |
| — | LCD_BL | **GPIO42** | 背光控制（PWM），走 Q2 驱动级，非 FPC 直连 |
| FPC4 | 座型号 | `AFC01-S14FCC-00` | FPC 16pin 座，实际用到 15 脚 |

补充事实：

| 项 | 结论 |
| --- | --- |
| CS | **无 CS 引脚**，硬件接地（常选通） → 固件侧 `CS=NC` 正确 |
| MISO | **无 MISO**，SPI 单向写（3 线 + DC） |
| SPI 驱动方式 | DC / MOSI / SCK 由 GPIO39/40/41 **直接驱动**，中间无缓冲/电平转换 |
| 屏类型 | SPI TFT 彩屏（非 8080 并口、非 RGB 并口） |

### 2.2 背光电路与极性结论

链路：**GPIO42 (PWM) → R23(1k) 基极/栅极限流 → Q2 MOS 管 → LEDA 经 R20(10Ω) 限流 → 背光 LED**；栅极另有 **R21(10k) 上拉至 3V3**。

| 元件 | 值 | 作用 |
| --- | --- | --- |
| R23 | 1k | IO42 → Q2 栅/基极限流 |
| R21 | 10k | Q2 栅极上拉至 3V3（**默认态 = 导通 = 背光默认亮**） |
| R20 | 10Ω | LEDA 回路限流 |
| Q2 | MOS 管 | 背光开关/调光 |

| 结论 | 内容 |
| --- | --- |
| **极性** | **IO42 高电平 → Q2 导通 → 点亮背光（高电平有效）** |
| 固件对应 | `DISPLAY_BACKLIGHT_OUTPUT_INVERT` 由 `true` 改为 **`false`**（PWM **不反相**） |
| 旧说法 | 早前档案的"低电平有效 / 主动低"**已被原理图推翻**，不再采用 |
| 回退方式 | 若实测"亮度条越高越暗"，把 `DISPLAY_BACKLIGHT_OUTPUT_INVERT` 改回 `true` |
| 副作用提示 | R21 上拉使 Q2 在 IO42 **高阻（未初始化）时也导通**，故上电瞬间背光可能先亮一下，属硬件正常现象 |

### 2.3 复位电路与极性结论

链路：**RESET(FPC6) 经 R76(10k) 上拉至 3V3**，由 PCA9557 **bit0** 驱动（LCD 与触摸共享此线）。

| 结论 | 内容 |
| --- | --- |
| **极性** | **低电平复位**（上拉保证默认不复位） |
| 释放态 | **bit0 = 1（不复位）** |
| 固件对应 | `InitializeSt7789Display()` 改为规范脉冲：**bit0=0 保持 20ms → bit0=1 保持 50ms**，末态保持 **1** |
| 旧代码问题 | 原 `SetOutputState(0, 0)` 会把屏幕**一直按住复位**（低电平复位下 0 = 复位中） |
| 关联影响 | 触摸与 LCD 共享 bit0；此前 bit0 恒为 0 是**触摸 0x38 NACK 的可能原因之一** |
| 日志 | `PCA9557 bit0 (LCD/touch reset, active-low) held at 1 (1=no reset)` |
| 原理图备注 | **RESET 未直连 ESP32**，图内未画出到 ESP32 的连接，实机需确认是否已额外接线；若未接，bit0 的复位脉冲不会到达屏幕（此时靠 R76 上拉也能自行释放） |

### 2.4 无 CS / 无触摸线推论

| 推论 | 依据 | 影响 |
| --- | --- | --- |
| **无 CS** | 原理图无 CS 网络，CS 硬件接地 | 固件 `CS=NC` 正确；SPI 上只有本屏一个从设备，无需片选 |
| **无 MISO** | 原理图无 MISO 网络 | 只能写不能读；读 ID / 读状态类操作不可用，不要据此判"屏坏了" |
| **本屏 FPC 无触摸线** | FPC 引脚列表中**没有任何 SDA / SCL / INT / RST 触摸信号** | 该屏**本身不带触摸**；若板上另有触摸排线/芯片则另说，需单独确认 |
| 触摸日志预期 | 6 个候选地址（0x38/0x5D/0x14/0x15/0x55/0x5A）**全 NACK** | **属预期，不是故障**；功能不受影响（BOOT 键 + 语音可用） |

---

## 3. 重编译与烧录

### 3.1 编译

| 方式 | 命令 | 说明 |
| --- | --- | --- |
| 推荐（一键） | `build_lckfb_s3.bat` | 自动配好 IDF v6.1 环境，内部执行 `python scripts\build.py lckfb/szpi-esp32s3` |
| 全量重编 | `build_lckfb_s3.bat clean` | 改过 `config.h` / `config.json` / 板代码后**建议用这个**，避免增量缓存吃旧配置 |
| 手动等价 | 见下 | 已配好 IDF 环境时可用 |

```batch
cd /d G:\demo\21_xiaozhi\hardware\small_screen_camera\xiaozhi-esp32
build_lckfb_s3.bat clean
```

手动等价命令（需先 `call D:\INSTALL\esp\v6.1\esp-idf\export.bat`）：

```batch
python scripts\build.py lckfb/szpi-esp32s3
```

产物：

| 文件 | 路径 |
| --- | --- |
| 应用固件 | `build\xiaozhi.bin` |
| 合并固件 | `build\merged-binary.bin` |
| 资源分区 | `build\generated_assets.bin` |

> 已知坑：首次构建报 `sdkconfig was not generated` → **重跑一次** `build_lckfb_s3.bat` 即可。

### 3.2 烧录（必须含 assets）

```batch
yh_flash.bat COM3          :: COM3 换成实际串口号；不传参会自动探测 CP210x/CH340/USB JTAG
```

`yh_flash.bat` 会检查 `build\flash_args` 是否含 `generated_assets`；**不含则自动走显式全量烧录**（脚本已内置，无需手工）。如需手工执行：

```batch
python -m esptool --chip esp32s3 -p COM3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0xd000 build\ota_data_initial.bin 0x20000 build\xiaozhi.bin 0x800000 build\generated_assets.bin
```

| 检查项 | 要求 |
| --- | --- |
| assets 地址 | **必须 0x800000**，否则界面乱码/缺字 |
| Flash 参数 | `--flash-mode dio --flash-size 16MB --flash-freq 80m`（本板强制 DIO） |
| OTA 与 assets | OTA **只刷 app 分区**，不刷 assets；换板/换固件后必须全量重烧 |

### 3.3 看日志

```batch
monitor.bat COM3           :: 115200，Ctrl+C 退出
```

建议直接把完整启动日志（**至少到上电后 2.2s 之后**）复制出来再判读；日志被截断会误以为"卡在 starting"。

---

## 4. 串口日志判读表（核心）

### 4.1 总流程与 stage 标签

| 顺序 | stage 标签 | 含义 |
| --- | --- | --- |
| 1 | `after-i2c-init` | I2C + PCA9557 建好、**摄像头还没上电**的基线扫描 |
| 2 | `cam-pwr-bit2=1` | 试 **bit2=1**（高有效上电）后扫描 + SCCB 探测 |
| 3 | `cam-pwr-bit2=0` | 仅当第 2 步未命中才出现，试 **bit2=0**（低有效上电） |
| 4 | `pre-camera-init` | `esp_camera_init()` 前的最终确认 |

每行扫描的汇总格式：

```
I (xxx) LichuangDevBoard: I2C scan[<stage>]: total N device(s); touch 0x38=YES/NO, cam SCCB 0x21/0x30/0x3C=YES/NO/...
```

### 4.2 判读表

| 日志特征 | 结论 | 下一步 |
| --- | --- | --- |
| `I2C scan[after-i2c-init]` 汇总行 `touch 0x38=NO` | 此刻触摸不在总线上（正常，尚未上电/未释放复位） | 看 `cam-pwr-bit2=?` 之后的扫描 |
| `I2C scan[cam-pwr-bit2=1]` 汇总行 `touch 0x38=YES` | 触摸在线；且证实"上电后才有" → **bit2 是摄像头与触摸的共用电源域**，原假设成立 | 触摸应能正常初始化；继续看摄像头 |
| 直到 `pre-camera-init` 仍 `touch 0x38=NO` | 触摸**未焊 / 未供电 / 被复位钳住**，或型号不是 FT5x06 | 转 §5 硬件排查；若扫描里出现 0x15 / 0x5D → 转 §6 换驱动 |
| `[cam-pwr-bit2=1] camera SCCB candidates matched: 1`（并伴随 `camera SCCB 0x30 -> ACK` 之类） | **bit2 高有效上电确认**，摄像头已带电，可用 | 随后应看到 `Camera power polarity resolved: PCA9557 bit2=1 (active-high power enable)` 和 `camera=ready` |
| `Camera power polarity resolved: PCA9557 bit2=1 (active-high power enable)` | 极性定案为高有效，代码已采用 bit2=1 | 无需改代码 |
| bit2=1 那段**没有** `-> ACK`，但 `cam-pwr-bit2=0` 段出现 `-> ACK` + `... bit2=0 (active-low power enable)` | **低有效上电**，代码已自动采用 bit2=0 | 无需改代码；记回适配说明 §3 风险表 |
| 两种极性下皆无 `-> ACK`，且出现 `未检测到摄像头 SCCB 地址：检查排线/模组供电/XCLK(GPIO5 20MHz)` | 供电极性已排除，属**硬件问题** | 转 §5：排线/FPC、模组 VDD、XCLK、是否 OV 系列 |
| `Camera power keep bit2=1 (...)` | `InitializeCamera()` 保持探测到的电平、未翻转（正确；翻转会把刚上电的摄像头掉电） | 正常 |
| `camera: Camera probe failed with error 0x106` + `Camera unavailable, disabled.` | SCCB 全地址 NACK（**不是驱动没编进去**） | 看 `cam-pwr-bit2=?` 扫描是否有 ACK → 无则 §5 |
| `camera: Detected camera not supported.` | 同上，0x106 的伴随日志 | 同上 |
| `cam_hal: cam init ok` | **只代表 cam_hal 层初始化成功**，不代表传感器探测成功 | 不要据此认为摄像头可用；以 `camera=ready` / `DISABLED` 为准 |
| `FT5x06 detected at 0x38, sda=1 scl=2` | 触摸在总线上（0x38 命中），已开始初始化 | 等 `Board init done` |
| `FT5x06 init failed at 400kHz, retry at 100kHz` → `FT5x06 initialized at 100kHz` | **速率问题，已自动降级到 100kHz 并成功** | 无需处理；若长期丢点可把默认改成 100kHz |
| `touch: probe 0x38 -> NACK`（且 0x5D/0x14/0x15/0x55/0x5A **全部 NACK**） | **该屏 FPC 无触摸线，属预期**（§2.4）；代码已不阻塞开机 | **无需处理**；功能不受影响（BOOT 键 + 语音可用）。不要当成故障反复刷机 |
| `touch: probe 0x5D -> ACK` / `0x14 -> ACK` / `0x15 -> ACK` | 板上**另有触摸芯片**（本屏 FPC 之外单独排线），已按日志自动识别型号初始化 | 按日志识别出的型号处理（GT911 / CST816S）；核对 `x_max/y_max/swap_xy/mirror_x` |
| `Board init done (... camera=ready, yh_led=nc(no-op))` | 摄像头探测成功 | 做 §4.3 功能验证 |
| `Board init done (... camera=DISABLED(probe failed), yh_led=nc(no-op))` | 摄像头探测失败、已置空（**不会**再虚假上报 ready） | 按本表上半部分定位 |

#### 4.2.1 重编译后判读表（屏幕侧，按 §2 原理图校准后新增）

| 日志 | 结论 | 动作 |
| --- | --- | --- |
| `PCA9557 bit0 (LCD/touch reset, active-low) held at 1` | 复位**已释放**（1=不复位，低电平复位），屏幕应出画面 | 正常；若仍无画面继续看下面两行 |
| `PCA9557 bit0 (...) held at 0` | 复位线仍被拉低，屏幕被按住复位 | 查 PCA9557(0x19) I2C 通信与 `InitializeSt7789Display()` 的脉冲代码 |
| 屏幕仍无画面（背光不亮 / 全黑） | 背光或 SPI/供电问题 | ① 把亮度拉到 100 看是否亮；**若亮度越高越暗说明极性仍反** → 把 `DISPLAY_BACKLIGHT_OUTPUT_INVERT` 改回 `true`；② 查 SPI **GPIO39/40/41** 与 FPC7/8/9 焊接；③ 查 **3V3(FPC10/11)** 与 **GND(FPC15)** |
| `touch: probe 0x38 -> NACK` 且 6 个候选（0x38/0x5D/0x14/0x15/0x55/0x5A）**全 NACK** | 该屏 FPC **无触摸线**，属预期（§2.4） | **不是故障**；功能不受影响（BOOT 键 + 语音可用），无需处理 |
| 日志中 **0x5D / 0x14 / 0x15** 出现 `-> ACK` | 板上**另有触摸芯片**（非本屏 FPC） | 按日志自动识别出的型号处理（GT911 / CST816S），再核对触摸映射参数 |

### 4.3 判读后的功能验证

| 项 | 操作 | 预期 |
| --- | --- | --- |
| 屏幕 | 上电 | 320×240 横屏点亮，方向正确 |
| 触摸 | 四角点按 | 触点与手指一致（偏移则核对 `swap_xy=1 / mirror_x=1 / x_max / y_max`） |
| 摄像头 | 让服务端调用摄像头 MCP 工具取图 | 返回 JPEG（quality 12）、画面不花屏 |
| 音频 | 播放 TTS / 对话 | ES8311 出声、ES7210 采到数据 |
| 状态灯 | 观察 GPIO48 | 随状态变化（YH 的 SET_LED 为空操作，预期） |

---

## 5. 硬件兜底排查清单

> 只适用于"两种 bit2 极性下 SCCB 均无 ACK"，或"板上确有触摸芯片但仍 NACK"（**注意**：本屏 FPC 无触摸线，6 地址全 NACK 属预期，见 §2.4，不需要排查）。

### 5.1 摄像头

| # | 检查 | 方法 | 预期 |
| --- | --- | --- | --- |
| 1 | 模组 VDD | 万用表量摄像头模组电源脚（AVDD/DOVDD/DVDD），在 `Camera power keep` 打印之后量 | 应有 2.8V / 1.8V / 1.2V 等级电压；**0V = 供电没过来**，回头查 bit2 那一路的 MOS/负载开关 |
| 2 | 排线 / FPC | 看排线是否插反、未插到底、金手指氧化、折痕断裂；重插一次 | 接触良好、卡扣扣紧 |
| 3 | 模组型号 | 看模组丝印（OV2640 / OV5640 / GC0308 / GC032A / SC031GS…） | 丝印对应的 SCCB 地址应出现在扫描里（0x30=O2640/SC031GS，0x3C=OV5640/OV3660/GC2145，0x21=OV7670/OV7725/GC0308/GC032A） |
| 4 | XCLK | 示波器/频率计量 GPIO5 | **20MHz** 方波；无时钟则 SCCB 可能不响应 |
| 5 | SCCB 引脚 | 对照 `config.h`：`SIOD=GPIO1`、`SIOC=GPIO2`、`XCLK=GPIO5`、`PWDN=NC`、`RESET=NC` | 与原理图一致 |
| 6 | 换模组 | 借一块确认好的同封装模组替换 | 换后能扫到地址 = 原模组坏 |

### 5.2 触摸

> 前提：**本屏 FPC 无触摸信号线**（§2.4），因此"6 个候选地址全 NACK"是默认预期，**不要**按本节排查。
> 本节只在"板上另有触摸排线/芯片"且其地址仍 NACK 时使用。

| # | 检查 | 方法 | 预期 |
| --- | --- | --- | --- |
| 1 | 芯片丝印 | 看触摸芯片型号丝印：**FT5206/FT5x06(0x38)**、**CST816S(0x15)**、**GT911(0x5D/0x14)**、ST7123(0x55)、CST9217(0x5A) | 丝印决定驱动选型；与代码不一致 → 转 §6 |
| 2 | 供电 | 量触摸芯片 VDD；注意它可能与摄像头共用 bit2 那一路 | 上电后应有电压 |
| 3 | 复位线 | bit0 是**低电平复位**（§2.3，R76 上拉）：释放态应为 **1**；若为 0，芯片被一直按住复位 → 永远 NACK（旧文档"高有效复位、释放态 0"已被原理图推翻） | `PCA9557 bit0 (LCD/touch reset, active-low) held at 1 (1=no reset)` |
| 4 | 焊接 | 放大镜检查芯片/QFN 引脚虚焊、连锡 | 无虚焊连锡 |
| 5 | 总线占用 | 扫描里是否同时看到 ES8311(0x18)、ES7210(0x82 为 0x40/0x41)、PCA9557(0x19) | 这些在 → 总线本身没问题，问题在触摸那一颗 |
| 6 | 触摸排线 | 确认板上是否另有独立触摸排线（本屏 FPC 不含 SDA/SCL/INT） | 没有独立排线 → 该屏无触摸，属预期 |

---

## 6. 如果触摸型号确实不是 FT5x06

> 现状：触摸已内置**多型号自动识别**（0x38 FT5x06 / 0x5D·0x14 GT911 / 0x15 CST816S / 0x55 ST7123 / 0x5A CST9217），
> 扫描里谁 ACK 就用谁，**无需手工换驱动**。本节仅在自动识别仍不成功、或需要调整映射参数时参考。

判据：扫描里**没有 0x38**，但出现了 **0x15（CST816S）** 或 **0x5D / 0x14（GT911）**。

### 6.1 依赖（多半已具备，先确认）

`main/idf_component.yml` 中以下两项**已存在**，通常无需新增：

```yaml
  espressif/esp_lcd_touch_cst816s: ^1.1.2
  espressif/esp_lcd_touch_gt911: ^1.2.1
```

若缺失，按同文件现有风格补一行（版本号与同文件保持一致），然后**全量重编**（组件清单变化不会增量生效）。

### 6.2 换驱动要点（不给完整实现）

| 步骤 | 要点 |
| --- | --- |
| 1. 头文件 | `lichuang_dev_board.cc` 顶部把 `esp_lcd_touch_ft5x06.h` 换成 `esp_lcd_touch_cst816s.h` / `esp_lcd_touch_gt911.h` |
| 2. 设备地址 | 把 `ESP_LCD_TOUCH_IO_I2C_FT5x06_ADDRESS`(0x38) 换成 `ESP_LCD_TOUCH_IO_I2C_CST816S_ADDRESS`(0x15) 或 GT911 的 0x5D；**前置 probe 的地址也要同步改**，否则仍会被"未探测到"直接跳过 |
| 3. IO 配置 | CST816S / GT911 的 `esp_lcd_panel_io_i2c_config_t` 与 FT5x06 略有差异（control phase / 寄存器位宽），照所选驱动 README 的示例填，不要照抄 FT5x06 的 `disable_control_phase` |
| 4. `esp_lcd_touch_config_t` | `x_max/y_max/swap_xy/mirror_x` 沿用现配置；GT911 通常需要 `rst_gpio_num`/`int_gpio_num`，本板触摸复位挂在 PCA9557 bit0 上（不是 GPIO），**别直接填 GPIO_NUM**，中断脚目前是 NC，需确认原理图是否有引出 |
| 5. 构造调用 | `esp_lcd_touch_new_i2c_ft5x06()` → `esp_lcd_touch_new_i2c_cst816s()` / `esp_lcd_touch_new_i2c_gt911()` |
| 6. 日志与提示 | 同步改 `InitializeTouch()` 里"not detected / hint"文案里的地址与型号名，避免后续排障被旧文案误导 |
| 7. 复位时序 | GT911 上电后需做一次复位 + 地址选择时序（INT 脚时序决定 0x5D/0x14）；本板触摸复位经 PCA9557 bit0，要先确认 bit0 能否被安全翻转（**注意**：翻转 bit0 会连带复位 LCD） |
| 8. 回归 | 改完跑 `build_lckfb_s3.bat clean` → `yh_flash.bat COMx`，确认扫描里目标地址出现、`FT5x06` 相关报错消失、四角点按无偏移 |

---

## 7. 常见误判提醒

| # | 误判 | 正解 |
| --- | --- | --- |
| 1 | `camera=ready` 就说明摄像头能用 | **旧日志不可信**（init 失败仍保留非空指针）。已改为 `camera=DISABLED(probe failed)`，只信这个字段 |
| 2 | `Backlight: Set brightness to 75` 是 NVS 恢复成功 | 75 是**默认值**；`RestoreBrightness()` 才走 NVS |
| 3 | 停在 `starting` = 卡死 | 日志被截断而已，约 **2.2s** 后进入配网；请把日志看完再下结论 |
| 4 | 摄像头 `0x106` = 驱动没编进去 | 门控是 `CONFIG_<型号>_SUPPORT`（全 y）；0x106 的真实含义是 **SCCB 全地址 NACK** |
| 5 | 触摸 `0x108` = 速率/时序问题 | 0x108 是**地址 NACK**（超时才 0x107）。速率问题会走"400kHz 失败 → 100kHz 重试"分支并打 `FT5x06 initialized at 100kHz` |
| 6 | `cam_hal: cam init ok` = 摄像头好了 | 只是 cam_hal 层，传感器探测在其后，仍可能 0x106 |
| 7 | `I2S rx switched master→slave` 是配置错 | 全双工预期行为，正常 |
| 8 | `Resampling 16000→24000` 是采样率配错 | 开机提示音解码，正常 |
| 9 | 一堆 `panel_io_i2c_tx_buffer ... i2c transaction failed` 说明总线坏了 | 是"设备没上电仍强行 init"的刷屏；已加前置 probe，新版不会再现 |
| 10 | OTA 之后也要重刷 assets | **OTA 只刷 app**；assets 只在 0x800000 全量烧录时写入 |
| 11 | 6 个触摸地址全 NACK = 触摸坏了 | 本屏 FPC **没有触摸信号线**（§2.4），全 NACK 是**预期**；功能不受影响（BOOT 键 + 语音可用） |
| 12 | 背光"高电平导通"（`OUTPUT_INVERT=false`） | **已回退为 `true`（低电平导通）**。Q2 栅极经 R21(10k) **上拉到 3V3** = P 沟道，拉低才导通；且上游 pristine BSP 与 `camera板子信息.md:60` 都是 true。改 false 后实机仍黑屏，已回退（§9.1） |
| 13 | bit0 释放态是 1（高有效复位） | **已订正为稳态 0**。立创官方 wiki 定义 IO0 = **LCD_CS 低电平选通**；且 yuhe/cam、yuhe/cam-ml307、rymcu/bigsmart、上游 pristine **全部 `SetOutputState(0,0)` 并全程保持 0**。停在 1 等于"永久取消片选 / 永久按住复位"→ 必黑（§9.1） |
| 14 | 扫 PCF8557 bit0~bit7 就是穷举了 | **错**。构造函数 `WriteReg(0x03, 0xF8)` 让 **bit3~bit7 是高阻输入**，对高阻脚写输出寄存器**完全无效** → 前几轮实际只驱动了 bit0/1/2。要扫某位必须**先 `SetDirection(0x00)`**（§9.2） |

---

## 8.5 第 9 轮：I2C 全域扫描 + SPI 模式订正

用户给出屏幕侧 I2C 为 **SDA=GPIO1 / SCL=GPIO2**（与本板总线 `AUDIO_CODEC_I2C_SDA_PIN/SCL_PIN` 一致），
并要求"扫描 I2C"。本轮同时落地两件事。

### 8.5.1 强证据修复：`DISPLAY_SPI_MODE` 2 → **0**

| 板 | PCA9557 初始化 | ST7789 | mosi/sclk/dc/BL | 分辨率 | swap/mirror | **spi_mode** |
| --- | --- | --- | --- | --- | --- | --- |
| `yuhe/cam` | 0x01=0x03 / 0x03=0xF8 | 是 | 40/41/39/42 | 320×240 | 一致 | **0** |
| `yuhe/cam-ml307` | 同上 | 是 | 同上 | 320×240 | 一致 | **0** |
| `rymcu/bigsmart` | 同上 | 是 | 同上 | 320×240 | 一致 | 2 |
| `lckfb/szpi-esp32s3`（本板，旧） | 同上 | 是 | 同上 | 320×240 | 一致 | **2** |

即：**与 lckfb 完全同族、且唯一差别就是 spi_mode 的两块板，用的都是 mode 0**。

技术面：ST7789 规格在 SCL **上升沿**采样 → **mode 0（CPOL=0/CPHA=0）**。
mode 2（CPOL=1）时钟空闲为高、采样沿相反 → 每字节整体错位一位 →
**所有命令成乱码 → 屏收不到 `0x11 SLPOUT` → 永远停在睡眠 → 背光再亮也全黑**。
这与"刷机前能显示、背光怎么调都没反应"的现象吻合。

`DISPLAY_SPI_HZ` 仍为 80MHz（yuhe/cam 在 mode 0 下同样跑 80MHz）；若改 0 后花屏，降到 40MHz。

### 8.5.2 阶段 4：`ScanI2cAcrossPowerDomains()`

`config.h` 的 `LCD_PROBE_PHASE` 设为 **4**，`LcdProbe()` 里另加一条**始终执行**的 `ProbeBacklightPinSanity()`。

**A. 背光脚连通性自检（纯数字判读，不用盯屏幕）**

把 `DISPLAY_BACKLIGHT_PIN` 从 LEDC 摘下改成输入，只开内部下拉读一次、只开内部上拉读一次：

| 下拉读数 | 上拉读数 | 判定 | 结论 |
| --- | --- | --- | --- |
| 0 | 1 | **悬空** | GPIO42 很可能**没连到背光电路**，原理图 BLK/LEDA 另有其脚 |
| 1 | 1 | **外部上拉** | 脚是通的（R21 10k→3V3），默认高 = 背光默认灭，与 `OUTPUT_INVERT=true` 自洽 |
| 0 | 0 | **外部下拉/短路** | 脚通但恒低；invert=true 时恒低 = 背光常亮 → 若仍全黑则问题在 SPI/CS 侧 |

**B. I2C 全域扫描 × PCF8557 全脚驱动**

先 `SetOutputPort(0x00)` → `SetDirection(0x00)`（**关键**：把 bit3~bit7 从高阻改成输出），
然后依次施加 `全低 / 全高 / 每位单独高 / 每位单独低` 共 **18 组**输出组合，
每组把 0x08~0x7F 扫一遍，并对每个地址打印中文设备名。

日志判读：

```
[i2c-scan] 方向寄存器 -> 0x00（bit0~bit7 全输出），实测 dir=0x??
[i2c-scan] out=0x?? (描述) -> N 个设备
[i2c-scan]   >>> 相对基线新增 N 个：0x.. （重点看这些！）
[i2c-scan]   <<< 相对基线消失 N 个：0x.. （该位疑似其电源/掉电控制）
[i2c-scan] 全部组合下出现过的地址合集：0x.. 0x..
```

- 基线 = 第一组"全低"（bit2=0 → 摄像头已使能，此时 **0x21 应该出现**）。
  若基线里就有 0x21，说明 `SetDirection()` 生效、方向寄存器写对了 —— 这是一个自带的自校验。
- 已知地址速查：`0x18`=ES8311 音频 DAC、`0x19`=PCF8557 本身、`0x41`=ES7210/ES8720 音频 ADC、
  `0x21`=GC0308、`0x30`=OV2640、`0x3C`=OV5640、`0x38`=FT5x06、`0x5D/0x14`=GT911、`0x15`=CST816S。
- 若某个组合下**冒出新地址**，那一位就是某路电源域的使能脚。

结束时会复原 `out=0x02` / `dir=0xF8`，不留下强驱状态。

### 8.5.3 本轮同时修掉的三个代码缺陷

| # | 缺陷 | 修法 |
| --- | --- | --- |
| 1 | `snprintf` 返回值是"本该写入的长度"，直接 `n += w` 会让 `n` 越过缓冲区，`sizeof(buf)-n` 下溢成巨大值 → **越界写** | 用 `Append()` lambda 对增量做钳位 |
| 2 | `snprintf(buf, cap, "  ", 0u)` 多余实参触发 `-Wformat-extra-args`，ESP-IDF 默认 `-Werror` → **编译失败** | 拆出无格式串的 `AppendLit()` |
| 3 | `ledc_stop()` 后仅靠 `ledc_update_duty()` 未必能把计数器重新跑起来 | 复原走完整 `ledc_channel_config()` |

---

## 8.6 第 10 轮：屏幕型号确认（ST7789 / 240×320）→ 分辨率配置复核结论：**无需改**

用户确认：**ST7789，物理 240×320**。核对后确认当前配置**本来就对**，不需要动。

### 8.6.1 为什么 `DISPLAY_WIDTH=320 / HEIGHT=240` 不是写反

ST7789 原生 GRAM 是 **240 列 × 320 行**。本板**横装**，所以：

| 项 | 值 | 说明 |
| --- | --- | --- |
| `DISPLAY_WIDTH` | 320 | LVGL 逻辑宽（横屏） |
| `DISPLAY_HEIGHT` | 240 | LVGL 逻辑高（横屏） |
| `DISPLAY_SWAP_XY` | true | 驱动在 MADCTL 置 **MV(0x20)**，列/行寻址方向互换 |
| `DISPLAY_MIRROR_X` | true | MADCTL 置 **MX(0x40)** |
| `DISPLAY_MIRROR_Y` | false | MY 不置 |
| **最终 MADCTL** | **0x60** | ST7789 240×320 横装的**标准横屏值** |

`SWAP_XY` 后 `draw_bitmap(0,0,320,240)` 发 CASET 0..319 / RASET 0..239，MV=1 使控制器把它正确映射到 240×320 的 GRAM 上。

**⚠ 不要因为"屏是 240×320"就把宏改成 240/320** —— 必须**同时**把 `SWAP_XY` 改成 `false`，否则画面转 90°。仓库内两种写法都合法，取决于横装/竖装：

- 横装（本板、`rymcu/bigsmart`、alientek box/box3、waveshare 3.5）：`320×240 + swap=true`
- 竖装（`bread-compact`、`wdmomo/esp32-cgc`、alientek box2、`waveshare/esp32-s3-cam`）：`240×320 + swap=false`

### 8.6.2 偏移量保持 0

ST7789 GRAM 恰好 240×320，不存在"屏比控制器小"的居中偏移 → `DISPLAY_OFFSET_X/Y = 0`。
（只有 240×240 或 135×240 这类小屏才需要 `esp_lcd_panel_set_gap()` 偏移。）

### 8.6.3 IDF v6.1 的 `panel_st7789_init()` 行为核对

`components/esp_lcd/src/esp_lcd_panel_st7789.c:182-201` 只发 4 条命令：

```
0x11 SLPOUT  → 等 100ms
0x36 MADCTL  (madctl_val)
0x3A COLMOD  (0x55 = RGB565)
0xB0 RAMCTRL (0x00, 0xF0 = big endian)
```

**不含 `0x29 DISPON`** → 本板代码在 `swap/mirror` 之后显式调用了 `esp_lcd_panel_disp_on_off(panel, true)`（发 0x29），顺序正确。
另外 `data_endian` 默认 0 = big endian（RGB565 标准），本板未改，正确。

### 8.6.4 新增日志

```
[lcd] ST7789 物理240x320 -> 逻辑320x240 (swap=1 mx=1 my=0) MADCTL=0x60, 已发 DISPON
```

**排障提示：方向/分辨率配错只会花屏或倒转，不会导致"一点不亮"。** 全黑不要往这里找原因，
继续看 §8.5 的 `[bl-pin]` 与 `[i2c-scan]`。

---

## 8. 相关文档

| 文档 | 内容 |
| --- | --- |
| `docs/lckfb-szpi-摄像头板适配说明.md` | 切板决策、风险清单（bit0/bit2 状态）、§4.4 实机首跑故障与处置 |
| `main/boards/lckfb/szpi-esp32s3/README.md` | 板级说明、Flash 模式、与档案的偏差说明（含屏幕原理图校准） |
| `main/boards/lckfb/szpi-esp32s3/config.h` | 唯一硬件事实来源（引脚宏，含 `DISPLAY_BACKLIGHT_OUTPUT_INVERT`） |
| `HARDWARE_GUIDE.md` | 硬件规格与 GPIO 分配（含 FPC 脚号、背光/复位电路） |
| `camera板子信息.md`（上级目录） | 硬件规格权威 |
| TFT 接口原理图（用户提供） | **屏幕侧最终权威**：FPC `AFC01-S14FCC-00`、背光 Q2、复位 R76；覆盖本文 §2 的所有结论 |
