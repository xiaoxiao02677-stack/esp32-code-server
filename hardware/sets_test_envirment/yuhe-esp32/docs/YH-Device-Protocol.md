# YH Device Protocol v1 — 小智固件侧实现说明

> 模块：`main/yh/`（小智固件 ↔ 屿禾工坊服务器通信适配层）
> 状态：固件已编译通过（ESP-IDF v6.1，板型 my-s3-tft，2026-10-02 构建产物）

## 1. 定位

小智原有 AI / ASR / TTS / WebSocket / MQTT / OTA **全部不变**。YH TCP 是**旁路设备管理通道**：

```
小智主链路（不动）:  Mic → Opus → WebSocket/MQTT → 小智云 → TTS → 喇叭
YH 旁路（新增）:    ESP32 ──TCP client──> 屿禾服务器 mm.com:3333
                     HELLO/ADVERTISEMENT/HEARTBEAT ↑   ↓ COMMAND/ACK
                                              WS2812 (GPIO48)
```

## 2. 通信技术

| 项 | 值 |
|---|---|
| 传输 | TCP over Wi-Fi（ESP32=client，服务器=server） |
| 地址 | `CONFIG_YH_SERVER_HOST`（默认 `mm.com`）: `CONFIG_YH_SERVER_PORT`（默认 3333） |
| 序列化 | JSON（cJSON） |
| **分帧** | **newline-delimited JSON**：`JSON + "\n"`；支持半包/粘包/一次 recv 多条/空行(CRLF 兼容)/超长(>4096B)拒绝断连 |
| 复用 | `Board::GetNetwork()->CreateTcp()`（EspTcp，自带接收任务，阻塞 DNS+connect 在 esp_timer 回调执行，不碰主循环/音频任务） |

## 3. 消息（全部含 `protocol_version: 1`）

| 类型 | 方向 | 触发 | 关键字段 |
|---|---|---|---|
| HELLO | 设备→服务器 | TCP 连接成功立即 | device_id（WiFi MAC，稳定）、firmware（esp_app 版本，如 2.5.1）、session_id（每连接新生成，esp_fill_random UUID） |
| ADVERTISEMENT | 设备→服务器 | HELLO 后 | operations: `["SET_LED"]`（白名单，只声明已实现能力） |
| HEARTBEAT | 设备→服务器 | 每 30s（esp_timer periodic） | device_id + session_id，无任何 AI/音频/用户负载 |
| COMMAND | 服务器→设备 | 服务器下发 | command_id / device_id / operation / parameters |
| ACK | 设备→服务器 | 每条 COMMAND 应答 | status: ACKED/NACKED，error_code，回显 command_id/device_id/protocol_version |

## 4. COMMAND 校验顺序（安全门）

1. `protocol_version != 1` → NACK `INVALID_VERSION`
2. 缺 `device_id`/`command_id`/`operation`（字符串）→ NACK `INVALID_PARAMETERS`
3. `device_id` ≠ 本机 MAC → NACK `WRONG_DEVICE`（**不执行任何动作**）
4. `operation` 不在白名单（仅 `SET_LED`）→ NACK `UNKNOWN_COMMAND`
5. `command_id` 命中 64 槽环形缓存 → NACK `DUPLICATE_COMMAND`（**不重复操作硬件**）
6. SET_LED 参数 schema：`parameters` 必须是**恰好只含一个键 `on`** 的对象，且 `on` 为 JSON boolean（拒绝 `"true"`/1/0/null/[]/{}/多余键）→ 否则 NACK `INVALID_PARAMETERS`
7. 全过 → 执行 LED → ACK `ACKED`

错误码与服务器 DeviceAck 对齐：`NONE / INVALID_MESSAGE / INVALID_VERSION / WRONG_DEVICE / UNKNOWN_COMMAND / INVALID_PARAMETERS / DUPLICATE_COMMAND`。

## 5. SET_LED → WS2812 映射

```
COMMAND SET_LED → YhProtocol::ExecuteSetLed(bool)
                      ↓
        Board::GetWs2812Led()  （Board 新增虚接口，默认 nullptr）
                      ↓
        YhWs2812Led::SetYhLed(bool)  （main/yh/yh_ws2812_led.cc）
                      ↓
        led_strip RMT → WS2812 GPIO48（DevKitC-1 板载）
```

- 协议代码**零 GPIO 操作**；LED 桥与协议解耦
- `YhWs2812Led` 与小智状态灯 `SingleLed`（Board::GetLed）**完全独立**，各自持有 led_strip 实例，互不干扰
- my-s3-tft：`YH_WS2812_GPIO = GPIO_NUM_48`（`config.h` 可改）
- 引脚可在 `main/boards/my-s3-tft/config.h` 的 `YH_WS2812_GPIO` 调整

## 6. 生命周期与重连

- **启动**：`NetworkEvent::Connected` → `YhProtocol::Start()`（application.cc，`#ifdef CONFIG_YH_PROTOCOL_ENABLED`）
- **断网**：`NetworkEvent::Disconnected` → `Stop()`（停定时器、断连）；网络恢复由 Connected 重新启动
- **OTA 升级**：`UpgradeFirmware()` 入口主动 `Stop()`，避免 reboot 残留半开连接
- **断线重连**：指数退避 1s→60s（esp_timer）；重连后**新 session_id**、重新 HELLO/ADVERTISEMENT；**绝不重放**上次 COMMAND
- **异常**：malformed JSON / 超长帧（>4KB）→ 断连重连，不 crash、不阻塞音频/主循环

## 7. 幂等

- 64 槽环形 RAM 缓存 command_id（FIFO 覆盖）
- 不持久化 NVS；重启后缓存为空（服务器侧 CommandLifecycle 负责跨重启去重）

## 8. 配置

Kconfig（menuconfig → Yuhe Assistant → YH Device Protocol）：

```
CONFIG_YH_PROTOCOL_ENABLED=y
CONFIG_YH_SERVER_HOST="mm.com"
CONFIG_YH_SERVER_PORT=3333
```

my-s3-tft 默认开启（`main/boards/my-s3-tft/config.json` sdkconfig_append）。其他板默认关闭，零影响。

## 9. 文件清单

| 文件 | 角色 |
|---|---|
| `main/yh/yh_protocol.h/.cc` | 协议核心：状态机/分帧/校验/幂等/ACK/重连 |
| `main/yh/yh_ws2812_led.h/.cc` | WS2812 LED 适配器（独立于状态指示灯） |
| `main/boards/common/board.h` | 新增 `GetWs2812Led()` 虚接口（默认 nullptr） |
| `main/boards/my-s3-tft/my_s3_tft_board.cc` | 覆写 `GetWs2812Led()` → GPIO48 |
| `main/boards/my-s3-tft/config.h` | `YH_WS2812_GPIO` 定义 |
| `main/Kconfig.projbuild` | YH menu 配置项 |
| `main/CMakeLists.txt` | 条件收录 `yh/*.cc` + include 路径 |
| `main/application.cc` | 生命周期挂载（Connected/Disconnected/UpgradeFirmware） |
| `tools/yh_e2e_test.py` | 对拍测试服务器（模拟 p19r_console 侧） |

## 10. 日志（串口）

```
I (xxxx) YH: TCP connecting to mm.com:3333 ...
I (xxxx) YH: TCP connected, session_id=xxxx
I (xxxx) YH: HELLO sent
I (xxxx) YH: ADVERTISEMENT sent
I (xxxx) YH: HEARTBEAT
I (xxxx) YH: COMMAND SET_LED, command_id=cmd_001
I (xxxx) YH_LED: YhWs2812Led ready on GPIO 48
I (xxxx) YH: LED ON
I (xxxx) YH: ACK ACKED (NONE)
E (xxxx) YH: [ERR] DUPLICATE_COMMAND: cmd_001
```

不打印 WiFi 密码 / token / 用户对话 / 音频内容。
