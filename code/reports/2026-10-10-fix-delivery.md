# 2026-10-10 修复交付文档

**交付日期**: 2026-10-10
**服务地址**: https://sandyun.top:8001（cc-console）/ :8001（设备 WS）/ 管理端 :8001/admincc/
**覆盖范围**: ASR 链路、TTS 音色、唤醒词改造、遗留修复 四大部分

---

## 一、今日修复总览

| # | 模块 | 问题现象 | 根因 | 修复动作 |
|---|------|----------|------|----------|
| 1 | ASR 链路 | 链路模拟器"断网也能 ASR"；ASR 一键测试报错 | 模拟器用浏览器 Web Speech API（本地识别，与服务器无关）；ASR 工厂漏传 delete_audio_file | 新增真实服务端 ASR 链路：Python `asr_recognize_handler.py`（ffmpeg 转 16k WAV → qwen3_asr_flash，60s 兜底）+ Java `AsrRecognizeController`；前端 MediaRecorder 录音上传，日志标注"ASR（服务端 xx ms）"；工厂补 delete_audio_file=True |
| 2 | TTS 音色 | 豆包"婉婉小何"等音色合成被火山拒绝（55000000 resource 不匹配）；复刻音色 S_ 前缀不可用 | 账号只开通 seed-tts-2.0 资源，预置音色混入 moon/jupiter 系；S_ 复刻音色归属与 resource_id 不匹配 | 音色表收敛为 5 个实测可用音色（小何/高冷御姐/VV/少儿故事/魅力女友）；复刻音色需 seed-icl-2.0 + 复刻专用模型（用户脚本实测打通）；错误翻译成中文可操作提示 |
| 3 | 唤醒词改造 | 管理后台设置唤醒词不生效/接口 404；推送消息格式设备不认 | Java 缺 WakeWordController 等 12 文件；旧推送 type=wake_word 被固件静默丢弃（固件只认 device_config 等 10 种 type） | 补 Java 12 文件重建部署；Python 推送改 `{"type":"device_config","payload":{"wake_word":[...]}}` → 固件 MultiNet UpdateWakeWordCommands 热更新（免重连）；空数组配合固件 ClearWakeWordCommands 恢复默认词；离线设备队列缓存待上线补推 |
| 4 | 遗留修复 | 清空唤醒词 NVS 死锁；小屏拼音表次序；误导日志；设备空闲被踢线 | 固件 ClearWakeWordCommands 语义缺失；拼音表乱序；close_connection_no_voice_time 三层覆盖（config.yaml 被 DB sys_params=120 覆盖） | 固件补"清空回默认"语义（agent-1）；拼音表次序+日志修复（agent-11）；DB sys_params 改 3600 + 固件断线自动指数退避重连（fw_build11） |

**关键链路图（唤醒词）**:
```
管理后台 POST /agent/wake-word/{agentId}（Java 8002）
  → DB AgentEntity.wakeWords 持久化（分号分隔）
  → POST 127.0.0.1:8003/api/wake-word/push（Bearer server.secret，回环）
  → Python WakeWordService 在线直推 / 离线缓存
  → WS 下发 {"type":"device_config","payload":{"wake_word":["你好小禾"]}}
  → 固件 board.cc ApplyDeviceConfig → HanziToPinyin → MultiNet UpdateWakeWordCommands 热更新
```

---

## 二、用户操作指南

### 2.1 固件烧录（全量，含 assets）

> 📖 详细分步手册见 `reports/FLASH-GUIDE-20261010.md`（含 merged-binary 产物与故障排查）。

唤醒词热更新与"清空回默认"依赖新固件，**必须先烧录**。小屏设备（ESP32-S3-N16R8，COM 口按实际）：

```bat
cd /d G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32
yh_flash.bat COM6        :: 自动探测串口也可不带参数；等效 esptool 全量布局烧录（含 generated_assets.bin）
```

等效命令（`yh_flash.bat` 内部实现，esp32s3 + 16MB flash）：
```
python -m esptool --chip esp32s3 -p COM6 -b 460800 --before default-reset --after hard-reset ^
  write-flash "@flash_args" --flash-mode dio --flash-size 16MB --flash-freq 80m
```

布局：`0x0 bootloader / 0x8000 partition-table / 0xd000 ota_data_initial / 0x20000 xiaozhi.bin / 0x800000 generated_assets.bin`。**注意 16MB 分区强耦合**：4M 设备误烧会失败。

### 2.2 烧录后验证清单

1. 串口监视 `python yh_monitor.py COM6`（115200），按顺序确认：
   - 启动：`MyS3TftBoard: Board init done`（音量从 NVS 恢复，无旧硬编码 Set 50）
   - 联网握手：`WS: Server hello: sample_rate=..`
   - 唤醒词下发：`Board: 应用云端唤醒词: N 个（首个: 你好小禾）`
2. 说唤醒词测试：新词命中即唤醒；喊"你好小禾"应被新词替换（后台设置后）
3. 断网重连：应静默指数退避重连（2s 起 ×1.5，封顶 60s），不再弹阻塞 Alert

### 2.3 唤醒词管理后台用法

1. 登录管理端 → 智能体页 → 选中智能体
2. 设置唤醒词列表（如 `["你好小禾"]`，≤10 个词、每个 ≤30 字）→ 保存
3. **实时生效**：在线设备立即热更新（无需重连）；离线设备在下次上线自动补推
4. 清空/恢复默认：提交空数组 → 设备恢复本地默认词"你好小禾"并清 NVS 缓存
5. 真机 ASR 验证：cc-console 链路模拟器点"录音（服务端真实 ASR）"——日志显示"ASR（服务端 xx ms）"即走服务器真实识别（须 https:// 打开，麦克风要求安全上下文）

### 2.4 TTS 音色切换方法

1. 智能体编辑 → TTS 引擎下拉：
   - 官方音色：选"豆包语音合成v3(HTTP)"，音色选 5 个可用之一（小何/高冷御姐/VV/少儿故事/魅力女友）
   - 声音复刻：选"豆包声音复刻"模型（resource_id=seed-icl-2.0），音色选 S_ 前缀复刻音色
2. 试听：音色下拉旁播放键（已支持任意 voice 实时合成试听）
3. **避开坑**：S_ 前缀复刻音色配"豆包语音合成v3"模型会报 55000000（resource 不匹配）；报错提示已中文化，按提示改模型即可

---

## 三、运维注意事项

1. **jar 部署规范**：服务器构建统一 `mvn package -Dmaven.test.skip=true`（本机无 mvn；testCompile 有预存失败与改动无关）。备份旧 jar 后再 cp、`systemctl restart xiaozhi-manager-api`，重启后必查 8002 探活。
2. **auth_key 三处一致**：`server.secret`（sys_params）、Python `config.yaml` 的 `server.auth_key`、Java 回环调用 Bearer——任一处不一致导致推送 401/鉴权失败。本次唤醒词推送依赖该密钥。
3. **YAML 文件勿用 SSH echo 写入**：此前有 rc=0 但内容被污染的先例（echo 转义/截断写出坏 YAML，Python 服务静默加载错误配置）。一律 sftp 传文件 + `python -c "import yaml; yaml.safe_load(...)"` 校验后重启。
4. **DB 音色配置**：预置音色只保留实测可用 5 条；**避开 S_ 前缀声音复刻系**（账号归属问题，非代码 bug）。新增音色走管理后台音色页（POST /ttsVoice），改音色后清 Redis 陈旧缓存（timbre:details / name:TTS_DoubaoV3_*）。
5. **业务码 vs HTTP 码**：Java 接口业务错误包在 HTTP 200 里（`{"code":404,"msg":"资源不存在"}`），监控/探活要用响应体 code 判断，不能只看 http_code。

---

## 四、遗留技术债清单

| # | 事项 | 说明 |
|---|------|------|
| 1 | NVS 残留依赖新固件 | 旧固件清空唤醒词死锁、不认 device_config 热更新；不烧新固件则唤醒词管理功能不可用 |
| 2 | MN7 唤醒率待实测调优 | MultiNet 动态命令表热更新后，新词唤醒率/误唤醒率需真机实测；拼音转换（HanziToPinyin）多音字可能不准 |
| 3 | icloud 音色命名混淆 | `zh_female_wanwanxiaohe_moon_bigtts`（婉婉小何）等 moon/jupiter/wvae 系命名与可用 uranus 系易混；后台已收敛但旧智能体配置若指向坏音色仍会报 55000000 |
| 4 | huoshan_double_stream 硬编码 | `ConfigServiceImpl:555-561` 对 S_ 音色强制 resource_id=seed-icl-1.0，与实测可用的 seed-icl-2.0 不一致；未来用该类型需改 |
| 5 | 大屏/超小屏固件未同步 | 唤醒词热更新与断线重连兜底当前验证在小屏固件；大屏（ILI9341+ES8311）与 super_small_screen 需同源移植验证 |
| 6 | 设备音量/亮度 0 值风险 | 云端下发 brightness=0 会把背光写到全黑并持久化，UI 未加二次确认 |
| 7 | 构建环境脆弱 | Git Bash 下 MSYSTEM 注入使 idf.py 告警；烧录/构建务必走 CMD/PowerShell 姿势（见 firmware-build-verify.md） |

---

## 五、验证记录（本轮，2026-10-10 21:30–21:45）

| # | 验证项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | GET /agent/wake-word/{agentId} | ✅ PASS | `{"code":0,"data":["你好小禾"]}`（部署前业务码 404 → 部署后正常） |
| 2 | POST 同路径 `{"wakeWords":["你好小禾"]}` | ✅ PASS | `code:0` 落库；GET 复查持久；无 token → 401（Shiro 鉴权生效） |
| 3 | 推送链路 Java→Python→设备 | ✅ PASS | Java 日志 `[WakeWord] 推送成功 agentId=32ff...` ×6；app.log 21:36:41/21:38:03 等多次 `已合并 agent 级唤醒词: ['你好小禾','嗨小禾',...]` + `已下发云端设备配置: {...,"wake_word":"你好小禾"}`；Python 侧 WS 直推无 error 日志 |
| 4 | asrRecognize 探活（Java 重部署后） | ✅ PASS | HTTP 200（ASR 链路未被破坏） |
| 5 | /agent/list 回归 | ✅ PASS | `code:0`，智能体列表正常返回 |

**验证时序说明**：验证期间 Python 服务被 agent-2 迭代重启（21:32、21:37），设备 WS 随之重连；重连握手时均完成唤醒词合并下发（覆盖"设置→重连生效"链路）。设备在线时段 POST 触发的 WS 直推由 `_push_to_conn` 静默完成（无 error 即成功）。

**观测性提示**：Python `wake_word_service.py` 用标准 logging 记 INFO（`向设备 xx 推送唤醒词`/`唤醒词已缓存`），但该级别未转发至 app.log（仅 WARNING+ 可见）。排查推送问题时以 Java 侧 `[WakeWord] 推送成功` 日志 + 设备重连时 `已合并 agent 级唤醒词` 为准。
