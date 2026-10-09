# bigscreen-s3 编译与烧录指南

> 用户自行编译烧录。板卡：ESP32-S3（16MB Flash / 8MB Octal PSRAM）、ES8311 音频、ILI9341 2.8 寸 SPI 屏。
> 环境：ESP-IDF v6.1，串口 COM10（USB-Serial/JTAG）。

## 1. 编译

```bash
cd G:/demo/21_xiaozhi/code/大屏幕/xiaozhi-esp32

# 方式 A：项目自带构建脚本（推荐，自动读本板 config.json 的 sdkconfig_append）
python scripts/build.py bigscreen-s3
# 查看所有板：python scripts/build.py --list-boards

# 方式 B：idf.py 手动（先 set target 再选板型）
idf.py set-target esp32s3
idf.py menuconfig   # Board type → "Bigscreen S3 (ES8311 + ILI9341 2.8-inch, 大屏幕)"
idf.py build
```

关键 sdkconfig 已由 `main/boards/bigscreen-s3/config.json` 声明（16MB Flash、`partitions/v2/16m.csv`、8MB Octal PSRAM、YH 心跳 `sandyun.top:12399`、OTA `http://sandyun.top:8002/xiaozhi/ota/`），走方式 A 无需手工配置。

## 2. 烧录与监视

```bash
idf.py -p COM10 flash monitor
# 或分步
idf.py -p COM10 flash
idf.py -p COM10 monitor
```

退出监视器：`Ctrl+]`。

## 3. 首烧后流程

1. **配网**：首次启动进入配网模式（BOOT 键单击进入 Wi-Fi 配网，或看串口提示）
2. **OTA 激活**：连网后设备自动向 `http://sandyun.top:8002/xiaozhi/ota/` 检查更新，OTA 响应会下发 WebSocket 地址并写入 NVS
3. **语音链路**：WS 连上 `ws://sandyun.top:8001/xiaozhi/v1/` 后即可对话（ASR→LLM→TTS 全链路在服务端）
4. **YH 心跳**：串口可见 `YH ONLINE` + 25s 周期心跳日志（服务端 12399 已上线）

## 4. 引脚风险提示（必读）

引脚来自 99 文档字符串推断 + 冲突消解（详见 `PINOUT.md`）：

- 音频 I2S（46/45/7/2）可信度最高（固件外设探测值）
- 显示数据脚 **SCK=12 / MOSI=13 为消解推测值**——若白屏，第一优先改这两个宏
- 背光=47、PA=1、I2C=10/11 均为推测值，实测不符改 `config.h` 即可

## 5. 已知裁剪

- I2C 触摸屏未启用（99 文档：`touch ic error` 初始化失败，型号未定）
- SD 卡未启用（引脚与显示/音频冲突）
- 无电池监测（板载无电池）
