# 板型更正：本板是 `yuhe/cam`，不是 `lckfb/szpi-esp32s3`

> 依据：`hardware/small_screen_camera/camera硬件信息.md`（2026-10-16 07:54 提供，用户确认为正确信息）
> 文档第 3 行明确写：**板级标识 `yuhe/cam` ｜ 主控 ESP32-S3**（屿禾 Yuhe AI Camera，Wi-Fi 版）

## 1. 结论：源码不用改引脚，改的是"选了哪块板"

此前一直在 `lckfb/szpi-esp32s3` 上改引脚，**方向是错的**。仓库里本来就有一块与该文档
**逐项吻合**的官方板实现 `main/boards/yuhe/cam`，**一个引脚都不用动**。

| 项 | 文档要求 | `lckfb/szpi-esp32s3`（原选，错） | `yuhe/cam`（现选，对） |
|---|---|---|---|
| 板级标识 | `yuhe/cam` | `lckfb/szpi-esp32s3` | **`yuhe/cam`** ✅ |
| 屏 SPI mode | — | **2** | **0** ✅（此前全黑的高可疑点） |
| 摄像头 XCLK | GPIO17 / 24 MHz | GPIO5 / 20 MHz ❌ | GPIO17 / 24 MHz ✅ |
| D0~D7 | 7,4,5,6,8,9,11,15 | 与文档不符 ❌ | 完全一致 ✅ |
| PCLK / VSYNC / HREF | 16 / 21 / 18 | 7 / 3 / 46 ❌ | 16 / 21 / 18 ✅ |
| I2S MCLK/BCLK/WS/DIN/DOUT | 38/14/13/12/45 | 一致 | 一致 ✅ |
| 按键 BOOT/VOL+/VOL− | 0 / 3 / 46 | 一致 | 一致 ✅ |
| LED | 单色 `SingleLed` GPIO48 | 一致 | 一致 ✅ |
| 屏 CS / RST | 均不接（NC） | 一致 | 一致 ✅ |
| 屏 RST 软控 | PCA9557 **P0**（置 0） | 一致 | `SetOutputState(0, 0)` ✅ |
| PA 使能 | PCA9557 **P1**（置 1） | 一致 | `EnableOutput()` 内置 ✅ |
| 摄像头电源 | PCA9557 **P2**（置 0 开） | 一致 | `SetOutputState(2, 0)` ✅ |
| 背光 | GPIO42 PWM **反相** | 一致 | `OUTPUT_INVERT=true` ✅ |
| 分辨率/方向 | 320×240 swap+mirror_x（横屏默认） | 一致 | 320×240 + `lcd_display` NVS 可切竖屏 ✅ |
| 摄像头参数 | VGA / RGB565 / PSRAM / fb=1 / jpeg 9 | — | 全部一致 ✅ |
| SCCB | 复用 I2C1（`sda=-1`, `port=1`） | — | 一致 ✅ |
| 电量 | ADC1_CH9(GPIO10) + GPIO47 充电检测 | — | 曲线 2030/2134/2252/2370/2488/2606 ✅ |
| ES8311 / ES7210 地址 | 0x30 / 0x82（8-bit 形式） | — | `ES8311_CODEC_DEFAULT_ADDR`(=0x30) / `0x82` ✅ |

## 2. 已做的改动（3 处）

1. **`sdkconfig`**：`CONFIG_BOARD_TYPE_LICHUANG_DEV_S3=y` → `CONFIG_BOARD_TYPE_YUHE_CAM=y`
   （`main/CMakeLists.txt` 的 `elseif(CONFIG_BOARD_TYPE_YUHE_CAM)` 分支会自动把
   `BOARD_DIR` 指向 `yuhe/cam`，字体也一并切对）
2. **`main/boards/yuhe/cam/config.json`**：并入本工程的构建项
   （16MB flash + `partitions/v2/16m.csv` + DIO + YH 协议 + OTA + 自定义唤醒词「你好小禾」），
   使 `scripts/build.py` 发布路径与本地 `sdkconfig` 保持一致
3. **新增 `build_yuhe_cam.bat`**：一键编译脚本，内容为 `python scripts\build.py yuhe/cam`

> 说明：`sdkconfig` 里原本就有 16MB / DIO / OTA / YH / 唤醒词，切板型不会丢这些配置。

## 3. 编译与烧录

```
cd G:\demo\21_xiaozhi\hardware\small_screen_camera\yuhe-esp32
build_yuhe_cam.bat            rem 首次建议加 clean
yh_flash.bat COMx
```

## 4. 关于之前那轮 lckfb 排查

`docs/lckfb-实机首跑排障.md` 与 `main/boards/lckfb/szpi-esp32s3/README.md` 记录的是
**在错误板型上做的排查**，相关代码已于 04:29 全部回退（备份在
`hardware/small_screen_camera/_revert_backup_20261016_0429/`）。

其中唯一仍值得保留的一条观察（现在已由板型切换天然解决）：

- 同族对照时发现 `yuhe/cam` 用 **spi_mode=0** 而 `lckfb` 用 **2**。
  当时推断"mode 2 会让命令乱码导致全黑"——这条推断现在有了更直接的解释：
  **板本来就是 yuhe/cam，用 lckfb 的 BSP 时 spi_mode 是错的**。
- 摄像头 XCLK：文档给 GPIO17，而 lckfb 原始值是 GPIO5（该原理图里 GPIO5 标 NC）——
  这也是"用错板型"的直接证据之一。

## 5. 竖屏/横屏切换

`yuhe/cam` 的 `InitializeSt7789Display()` 从 NVS 命名空间 **`lcd_display`** 读
`lcd_mode`（默认 1 = 横屏 320×240；0 = 竖屏 240×320）。改完需重启生效。
