# ESP32 硬件开发指南

## 硬件规格

| 组件 | 型号 | 连接 |
|------|------|------|
| MCU | ESP32-S3-N16R8 | Flash 16MB, PSRAM 8MB |
| LCD | ST7789 240×240 | SPI: GPIO 21/47/45/40/41/42 |
| 功放 | MAX98357A | I2S: GPIO 7/15/16 |
| 麦克风 | INMP441（已接线） | I2S: GPIO 4/5/6（VDD=3.3V, L/R=GND 左声道） |
| LED | WS2812 | GPIO 48 |

## 环境配置

### ESP-IDF 工具链
- 路径: `D:\INSTALL\esp\v6.1\esp-idf`
- Python环境: `D:\INSTALL\esp\tools\python\v6.1\venv`
- 临时目录: `D:\INSTALL\esp\tmp`

### 项目路径
- 源码: `G:\demo\21_xiaozhi\code\xiaozhi-esp32`
- 构建: `G:\demo\21_xiaozhi\code\xiaozhi-esp32\build`

## 开发命令

### 1. 编译固件
```batch
build_my_s3_tft.bat
```

### 2. 烧录固件
```batch
yh_flash.bat COM3
```
或自动检测端口：
```batch
yh_flash.bat
```

### 3. 串口监视
```batch
monitor.bat COM3
```
或自动检测端口：
```batch
monitor.bat
```

### 4. 完整工作流
```batch
workflow.bat all
```

## 目录结构

```
xiaozhi-esp32/
├── main/
│   ├── main.cc              # 主入口
│   ├── application.cc/h     # 应用逻辑
│   ├── boards/
│   │   └── my-s3-tft/
│   │       ├── config.h     # 硬件配置
│   │       └── my_s3_tft_board.cc  # 板级实现
│   └── yh/
│       ├── yh_protocol.cc/h # YH设备协议
│       └── yh_ws2812_led.cc/h  # WS2812 LED控制
├── build_my_s3_tft.bat      # 编译脚本
├── yh_flash.bat             # 烧录脚本
├── monitor.bat              # 串口监视
├── workflow.bat             # 完整工作流
└── sdkconfig                # 配置文件
```

## GPIO 分配

| GPIO | 功能 | 设备 |
|------|------|------|
| 4 | I2S_WS | INMP441（已接线） |
| 5 | I2S_SCK | INMP441（已接线） |
| 6 | I2S_SD | INMP441（已接线） |
| 7 | I2S_DOUT | MAX98357A |
| 15 | I2S_BCLK | MAX98357A |
| 16 | I2S_LRC | MAX98357A |
| 21 | SPI_SCL | ST7789 |
| 40 | SPI_DC | ST7789 |
| 41 | SPI_CS | ST7789 |
| 42 | BL | 背光 |
| 45 | RST | ST7789 |
| 47 | SPI_SDA | ST7789 |
| 48 | DATA | WS2812 |
| 0 | BOOT | 启动按钮 |

## YH 协议

YH (屿禾) 设备协议是独立的设备管理旁路通道，与小智主业务通道（WebSocket/MQTT）互不影响：
- 服务端: TCP `sandyun.top:12399`（22222 是服务器 SSH 端口，非 YH 协议端口）
- 协议: newline-delimited JSON（每行一条 JSON 消息）
- 消息类型: HELLO / ADVERTISEMENT / HEARTBEAT / COMMAND / ACK
- 功能: 设备状态同步、远程指令（如 WS2812 LED 控制）

## 调试技巧

### 查看编译日志
```batch
idf.py build -v
```

### 清理构建
```batch
idf.py fullclean
```

### 查看分区表
```batch
idf.py partition-table
```

### 擦除Flash
```batch
idf.py -p COM3 erase-flash
```

## 常见问题

### 1. 编译失败 - Permission denied
确保 TEMP 环境变量指向无空格路径：
```batch
set TEMP=D:\INSTALL\esp\tmp
```

### 2. 烧录失败 - Connection refused
- 检查COM端口是否正确
- 确保ESP32处于下载模式 (BOOT按钮 + RESET)
- 尝试降低波特率: `-b 115200`

### 3. 串口无输出
- 检查波特率 (默认 115200)
- 确认COM端口
- 检查USB线是否支持数据传输

## 版本信息

- ESP-IDF: v6.1
- 框架: C++
- 目标芯片: ESP32-S3
- 构建系统: CMake + idf.py
