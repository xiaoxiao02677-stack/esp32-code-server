# 板卡信息总结 — ESP32-S3 + 0.42" OLED（super_small_screen）

> 本文档由 2026-10-10 的 HelloWorld 开发会话整理，供后续任何 agent/开发者在此板子上编译、烧录、开发使用。
> 所有"实测"条目均已真机验证过；"推断"条目来自网络调研，未经本机验证。

## 1. 硬件概况（实测确认）

| 项目 | 值 | 备注 |
|---|---|---|
| 主控 | ESP32-S3 | 具体子型号未知（非 N16R8） |
| Flash | **4MB**（实测 `Detected size(4096k)`） | ⚠️ 配 16MB 会启动 assert 崩溃，必须 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y` |
| PSRAM | 未知（未启用，HelloWorld 不需要） | |
| 板载屏 | 0.42" OLED，SSD1306 兼容控制器 | 72x40 有效分辨率 |
| 屏幕接口 | I2C，地址 **0x3C**（7bit） | 400kHz 实测可用 |
| 屏幕几何 | 控制器 128 列 RAM，可见 72 列，**列偏移 28**；40 行 = 5 页 | 偏移 28 与 U8g2/SSD1306Ascii 官方一致 |
| 串口/烧录口 | **COM12**（本机） | ESP32-S3，自动复位烧录正常，无需手动 BOOT |
| 供电 | USB（5V），实测正常 | |

## 2. I2C 引脚（重要）

**这块板的 SDA/SCL 具体 GPIO 未经人工确认** —— 固件采用**上电自动探测**方案：
`main/main.c` 里的 `pin_pairs[]` 表（32 组常见组合）逐组 probe 0x3C，找到即用。

- 真实引脚 =`SDA=41 SCL=40` 
- 如需固化：把查到的值填进 `components/ssd1306/include/i2cdev.h` 的 `I2C_MASTER_SDA_IO / I2C_MASTER_SCL_IO`，并删掉 main.c 的扫描逻辑
- ⚠️ 引脚和 SDA/SCL 的**方向**也要注意：第一次手写 SDA=40/SCL=41 失败（NACK），自动探测纠正后成功

**同类板卡引脚调研（2026-10-10 agent 网络调研结论，供参考）：**

| 板卡/来源 | SDA | SCL | 备注 |
|---|---|---|---|
| 01Space ESP32-S3-0.42OLED（官方例程） | **41** | **40** | GitHub: 01Space/ESP32-S3-0.42OLED，与 upiir 项目同款，SSD1306 72x40 |
| 淘宝无 LED 版本（Arduino 论坛实证） | 48 | 47 | vauxmaker 博客记录的 AliExpress 板 |
| 台湾 IoT 扩展底板（外接 OLED，非板载） | 41 | 42 | 是扩展板外接 OLED 接口，不是板载屏 |
| 01Space ESP32-C3 0.42 OLED（不同芯片！） | 5 | 6 | C3 版，Zephyr 官方有 board 定义，别混淆 |

> 本板 Flash 实测 4MB。01Space 官方板有 S3R8（8MB PSRAM）版本；淘宝无 LED 版为 4MB。本板更接近后者，但未经证实。

## 3. 工程结构（G:\demo\21_xiaozhi\code\super_small_screen）

```
super_small_screen/
├── CMakeLists.txt              # 根 CMake，EXTRA_COMPONENT_DIRS 指向 components/
├── sdkconfig.defaults          # 4MB flash / DIO / 80M / Size 优化 / INFO 日志 / 自定义分区表
├── partitions_4mb.csv          # 自定义分区表：nvs 24K + phy 4K + factory 2MB
├── build.bat                   # 全量编译（set-target esp32s3 + build，会 fullclean）
├── build_only.bat              # 增量编译（不动 sdkconfig，日常改代码用这个）
├── main/
│   ├── main.c                  # HelloWorld + I2C 引脚自动探测
│   ├── CMakeLists.txt
│   └── idf_component.yml       # 托管组件清单（espressif/esp-websocket）
└── components/ssd1306/         # 自研组件，零第三方依赖
    ├── include/
    │   ├── ssd1306.h           # OLED 宽高/地址/页数宏 + API
    │   ├── i2cdev.h            # I2C 引脚宏 + 总线 API（含 probe）
    │   └── font.h              # 5x7 字库声明
    ├── ssd1306.c               # SSD1306 初始化/清屏/画字/刷新（帧缓冲 72x5）
    ├── i2cdev.c                # 新版 i2c_master API 封装（ESP-IDF v6.x）
    ├── font.c                  # 5x7 ASCII 字库（32..126）
    └── CMakeLists.txt          # REQUIRES esp_driver_i2c（⚠️ 不是 driver）
```

## 4. 编译（任何 agent 照做即可）

**环境（本机已装好，勿改路径）：**
- ESP-IDF **v6.1**：`D:\INSTALL\esp\v6.1\esp-idf`
- 工具链根：`D:\INSTALL\esp`（IDF_TOOLS_PATH）
- Python venv：`D:\INSTALL\esp\tools\python\v6.1\venv`
- TEMP/TMP 必须重定向到 `D:\INSTALL\esp\tmp`（避开杀软拦截 gcc 临时文件）

**方法一（推荐）：跑现成脚本**
```bat
G:\demo\21_xiaozhi\code\super_small_screen\build.bat       rem 全量（改了 sdkconfig.defaults 后用）
G:\demo\21_xiaozhi\code\super_small_screen\build_only.bat  rem 增量（日常改代码用）
```

**方法二：手动命令（cmd）**
```bat
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set TEMP=D:\INSTALL\esp\tmp
set TMP=D:\INSTALL\esp\tmp
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
cd /d G:\demo\21_xiaozhi\code\super_small_screen
python %IDF_PATH%\tools\idf.py build
```

**编译坑（已踩过）：**
1. sdkconfig 写 16MB → 启动 assert（`Detected size(4096k) smaller than ... 16384k`）。必须 4MB。
2. I2C 组件名：ESP-IDF v6.x 用 `esp_driver_i2c`，老写法 `driver` 会在链接时找不到 `i2c_master_transmit`。
3. `i2c_master_transmit` 的 len 参数是 `size_t`（头文件要 `<stddef.h>`）。
4. 路径含中文/空格会触发链接器 bug —— 本工程路径 `G:\demo\21_xiaozhi\code\super_small_screen` 全 ASCII，安全，勿移动。
5. `idf.py set-target` 前若 build 目录处于半清理状态会拒绝 fullclean —— 手动 `rmdir /s /q build` 再跑。
6. **托管组件联网下载**：`main/idf_component.yml` 声明了 `espressif/esp-websocket`，**首次构建需联网**，IDF 组件管理器会自动拉取到 `managed_components/`（缓存后离线可用；CI/无网环境用 `idf.py component download` 预取）。
7. **分区表已改自定义**（`partitions_4mb.csv`：nvs 24K + phy 4K + factory 2MB）。改了 `sdkconfig.defaults` 后必须用 `build.bat` 全量编译，不要用 `build_only.bat` 增量。

## 5. 烧录（COM12，用户自己执行）

**方式 A：IDF 环境**
```bat
python %IDF_PATH%\tools\idf.py -p COM12 flash
```

**方式 B：不进 IDF 环境，直接 esptool（cmd 可直接跑）**
```bat
cd /d G:\demo\21_xiaozhi\code\super_small_screen
D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe -m esptool --chip esp32s3 -p COM12 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 4MB --flash-freq 80m 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0x10000 build\super_small_screen.bin
```

**产物（全量编译后）：**
- `build\bootloader\bootloader.bin` @ 0x0
- `build\partition_table\partition-table.bin` @ 0x8000（自定义 `partitions_4mb.csv`，factory 分区 2MB）
- `build\super_small_screen.bin` @ 0x10000

**烧录观察：**
- 自动复位正常（`--before default-reset`），无需手动进下载模式
- 万一失败：按住 BOOT 再按 RST 进下载模式重烧

## 6. 串口监视

```bat
D:\INSTALL\esp\tools\python\v6.1\venv\Scripts\python.exe -m serial.tools.miniterm COM12 115200
```
（或 IDF 环境下 `idf.py -p COM12 monitor`，退出 Ctrl+]）

**关键日志（当前固件）：**
```
I main: boot: ESP32-S3 + 0.42in SSD1306 hello world
I main: probe SDA=40 SCL=41 ... ESP_ERR_TIMEOUT     <- 逐组扫描（每组约几十 ms）
I main: OLED found at 0x3C on SDA=xx SCL=xx          <- ★ 真实引脚在这一行
I ssd1306: SSD1306 72x40 initialized
I main: hello world rendered on SDA=xx SCL=xx        <- 屏幕此时已显示 Hello / World!
```
错误对照：`ESP_ERR_INVALID_RESPONSE` = NACK（引脚不对/地址不对）；`ESP_ERR_TIMEOUT` = 总线无应答（引脚不对或缺上拉）。

## 7. SSD1306 驱动要点（写新功能时参考）

- 初始化序列（实测可用）：`0xAE → 0xD3/0x00 → 0x20/0x00（水平寻址） → 0x40 → 0xA1 → 0xC8 → 0xA8/0x27（40行） → 0xD5/0x80 → 0xD9/0x21 → 0xDA/0x12 → 0x81/0xCF（对比度） → 0x8D/0x14（内部电荷泵） → 0xA4 → 0xA6 → 清屏 → 0xAF`
- 帧缓冲 `fb[5][72]`（5 页 x 72 列），刷新时设列窗口 28..99（`0x21/28/99`）+ 页窗口 0..4（`0x22/0/4`），然后一笔 I2C 写 0x40 前缀 + 360 字节
- 文字渲染：`ssd1306_draw_string(x, page, str)`，5x7 字体、6 像素步进、每行 12 字符、共 5 行
- 列偏移 28 的依据：U8g2 `u8x8_d_ssd1306_72x40.c`（EastRising 0.42"）与 SSD1306Ascii issue#94 一致
- 屏幕是 128x64 控制器裁成 72x40 可见区：不要用 128x64 的整屏寻址写法

## 8. 已验证状态

| 日期 | 事项 | 结果 |
|---|---|---|
| 2026-10-10 | HelloWorld（自动探测版）烧录 COM12 | ✅ 屏幕显示 Hello / World!，用户确认 |
| 2026-10-10 | Flash 4MB 修正 | ✅ 修复 16MB assert 崩溃 |
| 2026-10-10 | I2C 引脚自动探测 32 组 | ✅ 扫描找到 0x3C（具体引脚值见串口日志） |

