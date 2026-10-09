# YH Device Protocol — 测试报告

日期：2026-10-02
固件：xiaozhi 2.5.1（my-s3-tft，ESP-IDF v6.1，`CONFIG_YH_PROTOCOL_ENABLED=y`，server=mm.com:3333）
对拍工具：`tools/yh_e2e_test.py`（模拟服务器侧 p19r_console 的 TCP 端点）

## 一、静态验证（已完成）

| 验证项 | 结果 | 证据 |
|---|---|---|
| 固件编译 | **PASS** | `Project build complete`（2026-10-02 16:22，含 YH 模块，xiaozhi.bin 正常生成） |
| YH 模块进编译链 | **PASS** | build.ninja 含 `yh/yh_protocol.cc.obj`、`yh/yh_ws2812_led.cc.obj` |
| sdkconfig 注入 | **PASS** | 构建日志 sdkconfig_append 5 项含 `CONFIG_YH_PROTOCOL_ENABLED=y`、`mm.com`、`3333` |
| 原功能不受影响 | **PASS（静态）** | WS/MQTT/OTA/音频源码零改动；application.cc 仅 3 处 `#ifdef` 挂载点；board.h 默认实现不变（其他板 GetWs2812Led 返回 nullptr） |
| 对拍脚本语法 | **PASS** | py_compile 通过 |
| 协议合规（代码审查） | **PASS** | newline 分帧含半包/粘包/空行/超长处理；HELLO→ADVERTISEMENT 顺序；HEARTBEAT 30s 纯存活；COMMAND 六重校验（版本/缺字段/错设备/白名单/幂等/schema 严格 boolean-only）；ACK 回显三要素；错误码 7 项与服务器对齐；重连新 session_id 不重放 |

## 二、动态验证（需真机，待执行）

> 以下项**必须**在真实 ESP32-S3 + 真实 WS2812 上执行后才能宣告 PASS。
> 前提：服务器 mm.com:3333 可达（或局域网内用 `python tools/yh_e2e_test.py` 临时充当）。

### 测试矩阵（覆盖任务书 §二十九 1-23 项）

| # | 用例 | 预期 | 结果 |
|---|---|---|---|
| 1 | HELLO 收到 | 含稳定 device_id/真实版本/新 session_id | 待测 |
| 2 | ADVERTISEMENT 收到 | operations=["SET_LED"] | 待测 |
| 3 | HEARTBEAT 每 30s | 仅 device_id+session_id | 待测 |
| 4-5 | SET_LED on/off | ACK ACKED + 硬件亮/灭 | 待测 |
| 7 | wrong device | NACK WRONG_DEVICE 不执行 | 待测 |
| 8 | protocol_version=2 | NACK INVALID_VERSION | 待测 |
| 9 | unknown operation | NACK UNKNOWN_COMMAND | 待测 |
| 10 | on:"true"（字符串） | NACK INVALID_PARAMETERS | 待测 |
| 11 | 多余参数 gpio | NACK INVALID_PARAMETERS | 待测 |
| 12 | 缺 command_id | NACK INVALID_PARAMETERS | 待测 |
| 13 | 重复 command_id | NACK DUPLICATE_COMMAND 硬件不动 | 待测 |
| 14-16 | 服务器断开→设备重连 | 新 session_id + 重新 HELLO | 待测 |
| 17-18 | 半包/粘包 | 分帧正确 | 待测 |
| 19 | malformed JSON | 断连重连不 crash | 待测 |
| 20 | 超长 JSON(>4KB) | 断连重连 | 待测 |
| 21-23 | ON/OFF/重复的物理 LED | 亮/灭/不重复执行 | 待测 |

### 真机对拍步骤

1. 电脑运行：`python tools/yh_e2e_test.py --port 3333`（自动对拍模式）
2. 固件烧录后串口观察 `[YH]` 日志；脚本侧观察 `[DEVICE]` 回显
3. 交互模式手动验证：`on` / `off` / `dup cmd_001` / `raw {...}`
4. 物理观察 GPIO48 RGB LED 亮灭

## 三、验收矩阵（当前状态）

```
YH Device Protocol:      PASS（协议实现+编译）
TCP Transport:           PASS（EspTcp 复用+分帧）
HELLO:                   PASS（静态）/ BLOCKED（真机）
ADVERTISEMENT:           PASS（静态）/ BLOCKED（真机）
HEARTBEAT:               PASS（静态）/ BLOCKED（真机）
SET_LED:                 PASS（静态）/ BLOCKED（真机）
ACK:                     PASS（静态）/ BLOCKED（真机）
Idempotency:             PASS（静态）/ BLOCKED（真机）
Reconnect:               PASS（静态）/ BLOCKED（真机）
Security:                PASS（静态）/ BLOCKED（真机）
P19-R Console E2E:       BLOCKED（需真机 + 服务器）
Real ESP32:              BLOCKED（固件已就绪，待烧录对拍）
Real WS2812:             BLOCKED（固件已就绪，待烧录对拍）
```

## 四、遗留事项

1. `mm.com:3333` 需服务器侧可达；若测试时服务器未上线，用对拍脚本在局域网充当（需临时把 `CONFIG_YH_SERVER_HOST` 改为测试机 IP 重编，或等服务器提供动态下发）
2. GPIO48 需确认板子实际焊接（DevKitC-1 板载地址 RGB 灯即 48 脚；自焊板按 `config.h` 的 `YH_WS2812_GPIO` 改）
3. 对拍通过后，与真实 `tools/p19r_console.py`（服务器侧）联调，替换模拟脚本
