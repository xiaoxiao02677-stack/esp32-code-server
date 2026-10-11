# my-s3-tft 固件编译烧录指南

## 硬件信息
- MCU: ESP32-S3-N16R8（16MB Flash, 8MB PSRAM）
- Display: ST7789 240x240 SPI LCD
- Audio: MAX98357A I2S功放 + INMP441麦克风
- 框架: ESP-IDF 6.1

## 一、编译步骤

### 1. 设置环境变量
```batch
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
```

### 2. 进入项目目录
```bash
cd G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32
```

### 3. 配置目标板子
```bash
idf.py set-target esp32s3
idf.py reconfigure
```

### 4. 选择 my-s3-tft 板型
```bash
idf.py menuconfig
```
导航到：`Component config` → `Xiaozhi ESP32 Board Type` → 选择 `my-s3-tft`

或者直接命令行：
```bash
idf.py -DCONFIG_BOARD_TYPE_MY_S3_TFT=y build
```

### 5. 全量编译
```bash
idf.py build
```

## 二、烧录步骤

### 方法1：使用自动脚本（推荐）
```batch
yh_flash.bat COM12
```
（假设串口为COM12，脚本会自动探测）

### 方法2：手动全量烧录
```bash
python -m esptool --chip esp32s3 -p COM12 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build/bootloader/bootloader.bin 0x8000 build/partition_table/partition-table.bin 0xd000 build/ota_data_initial.bin 0x20000 build/xiaozhi.bin 0x800000 build/generated_assets.bin
```

## 三、串口监视

### 查看启动日志
```bash
idf.py -p COM12 monitor
```

### 关键日志检查点
```
# WiFi连接成功
[I] wifi_board.cc:xxx] WiFi connected to xxx

# WebSocket连接成功
[I] websocket_protocol.cc:xxx] Connected to websocket server

# 收到设备配置
[I] application.cc:xxx] Received device_config: {...}

# 配置同步完成
[I] application.cc:xxx] 云端配置同步完成（唤醒词已生效/已缓存待引擎就绪）
```

## 四、验证清单

### 1. 屏幕状态
- 开机后显示"配置同步中..."（正常）
- 收到device_config后切换到"唤醒词就绪"
- 2秒后回落待机文案

### 2. WiFi配网（如需重新配网）
- 短按BOOT键（Starting状态下）进入配网模式
- AP SSID格式："屿禾工坊-XX"（XX是MAC后缀）
- 手机连接AP后，浏览器打开 http://192.168.4.1

### 3. 唤醒词测试
- 说"你好小禾"应触发唤醒
- 屏幕显示表情变化

### 4. 常见问题排查
| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| 一直显示"配置同步中" | 设备未注册/未绑定 | 在Java后台添加设备MAC地址 |
| 无法连接WiFi AP | 配网模式未启动 | 长按BOOT键30秒内 |
| 屏幕无显示 | LCD初始化失败 | 检查SPI引脚连接 |
| 无声 | 音量设置/功放问题 | 长按BOOT调节音量 |

## 五、服务器端检查

如果设备一直显示"配置同步中"，检查服务器：

```bash
# SSH登录服务器
ssh -p 22222 root@sandyun.top
# 密码: Ymm6088.

# 查看数据库设备列表
MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -e "SELECT * FROM ai_device LIMIT 10;"

# 查看最近连接日志
tail -100 /root/xiaozhi-server/main/xiaozhi-server/data/app.log | grep -E "device|hello|connect"
```
