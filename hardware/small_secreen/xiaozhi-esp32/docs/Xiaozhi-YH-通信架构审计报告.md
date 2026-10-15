# Xiaozhi-YH 通信架构审计报告

> 审计对象：`G:\demo\19 esp32\xiaozhi-esp32`（PROJECT_VER 2.5.1，ESP-IDF v6.1，目标板 `my-s3-tft`）
> 审计目的：为新增 **YH Device Protocol v1**（TCP 客户端 → 屿禾服务器 :3333，newline-delimited JSON）适配层提供事实依据。
> 审计方式：只读源码分析，未修改任何文件。

---

## A. 小智现在怎么联网？

| 环节 | 位置 | 机制 |
|---|---|---|
| 启动 | `main.cc:14-29` | `nvs_flash_init()` → `Application::Initialize()` → `Run()`（事件组主循环） |
| 网络启动 | `application.cc:170` → `wifi_board.cc:52-100` | `StartNetwork()` 异步初始化 `WifiManager`（esp-wifi-connect 组件） |
| STA 连接 | `wifi_station.cc:115-169` | 扫描 → RSSI 排序匹配已存 SSID → 连接 |
| **断线重连** | `wifi_station.cc:418-445` | 快速重连 ×5 → 换下一个 AP → 定时重扫（指数退避 10s→300s） |
| 配网回退 | `wifi_board.cc:164-170` | 60s 连不上 → AP 配网模式（SSID 前缀「屿禾工坊」，`wifi_board.cc:59`） |
| 回调线程 | `wifi_manager.h:6` | **WiFi event task** 调用回调——YH 层跨线程须用 `Application::Schedule()`（AGENTS.md:33） |

## B. 小智现在怎么连接服务器？

`application.cc:531-545` `InitializeProtocol()`：开机 activation 任务里 OTA 服务器（`api.tenclass.net`）下发配置 → **有 mqtt 配置建 MqttProtocol，否则 WebsocketProtocol**（默认 MQTT）。两者均为懒连接：`Start()` 直接返回，音频通道打开时才真正拨号。

## C. 当前服务器通信技术

| 通道 | 文件 | 用途 |
|---|---|---|
| WebSocket | `protocols/websocket_protocol.cc` | 语音对话（Opus 音频流 + JSON 控制） |
| MQTT + UDP | `protocols/mqtt_protocol.cc` | 对话控制（MQTT）+ 音频（UDP） |
| HTTPS | `ota.cc` | 版本检查 / 固件下载 / 服务器配置下发 |

均为「小智云」通道。**YH TCP 属旁路管理通道，不并入此体系**。

## D. 哪个 task 负责网络？

- 主循环 `main`（`application.cc:176-261`，事件组驱动，优先级 10）
- `activation`（`application.cc:301-308`，OTA+协议创建）
- `EspTcp` 每实例自带 `tcp_receive` 任务（`esp_tcp.cc:129-148`，1500B/次 recv）
- WiFi event task / esp_timer task
- **YH 连接管理**：仿 `mqtt_protocol.cc:20-37` 的 esp_timer 重连模式 + `EspTcp` 自带接收任务，**不新建常驻任务**（先证明现有模型适合——EspTcp 接收回调 + esp_timer 定时器已覆盖需求）

## E. 哪个模块最适合增加 YH Protocol？

**`main/yh/`（新目录，与 `protocols/` 平行）**：
1. `protocols/` 的 `Protocol` 基类绑定音频通道语义（`SendAudio`/`OpenAudioChannel`），YH 是设备管理通道，塞入污染契约（AGENTS.md:35 改 Protocol 须同时验证 WS+MQTT）
2. TCP 原语现成：`Board::GetNetwork()->CreateTcp()` → `EspTcp`（DNS+connect+接收任务+断开回调全套，`esp_tcp.cc:26-70`）
3. 生命周期：网络就绪（`kDeviceStateIdle`）后起连；OTA 升级期（`kDeviceStateUpgrading`）主动断开

## F. 当前有没有 TCP server/client？

**有 client 封装，可直接复用**：`78__esp-ml307` 组件的 `Tcp` 接口（`include/tcp.h`）+ WiFi 实现 `EspTcp`（`src/esp/esp_tcp.cc`）。`HttpClient` 内部同样用它（`http_client.cc:201-203`），证明通用性。注意 `Connect()` 是阻塞 DNS+connect，须在定时器回调（esp_timer task）中调用，不得在主循环/audio 任务调用。

## G. 当前有没有 WebSocket？

有（语音通道，见 C）。YH 第一阶段禁止 WS Device Protocol，不复用、不改动。

## H. 当前 LED/WS2812 是怎么驱动的？

- `main/led/single_led.cc`：WS2812 单灯（led_strip RMT 后端，GRB，10MHz）；但 `SetColor/TurnOn/TurnOff` 均为 **private**，外部唯一入口 `OnStateChanged()`（按设备状态自动配色，含线程安全 mutex）
- `Board::GetLed()` 默认返回 `NoLed`（`board.cc:56-59`）
- **my-s3-tft 现状**：`config.h:46` `BUILTIN_LED_GPIO=GPIO_NUM_NC`，未接 LED → YH 需新增独立 WS2812 句柄（不能借用状态指示灯路径，否则 YH SET_LED 会与小智状态灯互相打架）
- DevKitC-1 板载 WS2812 惯例 **GPIO48**（多板 `BUILTIN_LED_GPIO=GPIO_NUM_48` 佐证）

## I. device_id 从哪里来？

`system_info.cc:35-47` `SystemInfo::GetMacAddress()` = WiFi STA MAC 小写冒号格式（`aa:bb:cc:dd:ee:ff`），即小智对服务器的既有身份。另有 NVS 持久化 UUID（`board.cc:15-43`，`board/uuid`）。
**YH device_id 方案**：直接用 MAC（稳定、与服务器 P19-R 侧设备管理兼容）。

## J. 哪些代码绝对不能改？

| 禁区 | 依据 |
|---|---|
| `managed_components/` 全部 | AGENTS.md:38（EspTcp 只 include 使用） |
| `Protocol` 基类与 WS/MQTT 协议实现 | AGENTS.md:35；YH 是旁路 |
| `Board::GetLed()` 默认实现及他板引脚 | AGENTS.md:29（板身份影响 OTA） |
| `Application::Run()` 结构 / audio 任务参数 | AGENTS.md:34（禁阻塞） |
| 既有 NVS 命名空间（wifi/board/mqtt/websocket/...） | AGENTS.md:36（持久 API） |
| `device_state_machine.cc` / `main.cc` 启动序 | AGENTS.md:32 |
| `build/` `sdkconfig*` 等生成物 | AGENTS.md:38 |

---

## 附：YH 适配层设计决定（由审计导出）

1. **目录**：`main/yh/`（`yh_protocol.h/.cc` 单类 + `main/CMakeLists.txt` SOURCES 追加 + INCLUDE_DIRS `yh`）
2. **传输**：`Board::GetNetwork()->CreateTcp()`（EspTcp）；连接/重连在 esp_timer 回调内完成（不阻塞主循环）
3. **分帧**：`OnStream` 回调累积到缓冲区，按 `\n` 切分；单消息上限 4KB 超限断连（防内存攻击）
4. **device_id**：`SystemInfo::GetMacAddress()`；**firmware**：`esp_app_get_description()->version`（真实小智版本 2.5.1）
5. **session_id**：每连接用 `Board::GenerateUuid()` 同款算法新生成（不复用 NVS uuid）
6. **LED 桥**：`Board` 新增虚方法 `GetWs2812Led()`（默认 nullptr）——my-s3-tft 返回 GPIO48 独立 `SingleLed` 式句柄；YH 层只调 `yh_set_led(bool)`，协议代码零 GPIO 操作
7. **幂等**：64 槽环形缓存 `command_id`（RAM，不进 NVS）
8. **挂载点**：`Application::InitializeProtocol()` 尾部条件启动（`CONFIG_YH_PROTOCOL_ENABLED`），网络就绪后由网络事件驱动首连
9. **配置**：`Kconfig.projbuild` 新增 `YH_PROTOCOL_ENABLED`（默认 n）/ `YH_SERVER_HOST`（默认 mm.com）/ `YH_SERVER_PORT`（默认 3333）；my-s3-tft 的 `config.json` sdkconfig_append 开启
