# 推送音频播放失败·根因分析报告（RCA）

**日期**：2026-10-15 | **状态**：已修复并上线验证 | **作者**：主 agent 排查（多 agent 通道因基础设施 406/503 故障，全部由主 agent 亲自完成）

## 摘要

管理端 push-scheduler 推送的音频，设备端 100% 播放失败并报 `Notification Ogg stream ended before a complete audio stream`。根因是**格式不匹配**：固件 NotifyPlayer 只支持 Ogg Opus 单声道，而服务端 TTS 落盘并推送的是 MP3。次要问题：火山 doubao_v3 上游返回的 MP3 尾部自带垃圾字节（不影响 MP3 播放器，但掩盖了问题）。修复 = 服务端落盘后统一 ffmpeg 转码 Ogg Opus，已部署并端到端验证通过。

## 故障现象

- 设备日志：HTTP 200 连上 `sandyun.top:8003`，约 300ms 后报 Ogg 流不完整错误，播放失败
- 2026-10-15 16:01–16:12 共 11 次推送全部失败；10-14 20:51–21:01 的 29 次推送同样全部失败（问题自推送功能上线即存在）
- `AudioService Stats: dec=44 out=42` 与本次无关——那是开机后 30s 周期累计计数（开机提示音约 2.6s），用户听到的"部分播放"即此开机音

## 排查过程（取证链）

| 步骤 | 操作 | 结论 |
|---|---|---|
| 1 | 下载问题音频对比 md5 | 本地下载=服务器磁盘（`021c323e…`），排除传输层 |
| 2 | 十六进制取证 | 头部合法 ID3/Lavf58.76.1；尾部 150-450B 连续 0xAA/0x55 垃圾 |
| 3 | 模拟设备请求头（Accept: audio/ogg）下载 | 服务器忽略 Accept，原样返回 audio/mpeg，无动态转码 |
| 4 | tmp/ 全量扫描 41 个文件 | 41/41 带尾部垃圾，但 ffmpeg 解码 0 错误、时长完整 |
| 5 | 直调 doubao_v3 复现（真实配置） | 6/6 次合成全部带垃圾（含每次新建实例）→ 垃圾来自火山上游，非服务代码 bug |
| 6 | 固件源码审计（notify_player.cc / ogg_demuxer.cc） | NotifyPlayer 硬约束：仅 Ogg Opus 单声道（OpusHead+OpusTags+mono），MP3 零 OggS 页 → 必然失败 |
| 7 | ffmpeg 转码实验 | 服务器 ffmpeg 6.1.1+libopus，41/41 转码成功，时长偏差≤0.007s，均耗 0.43s |

## 根因

**根因 B（决定性）——格式不匹配**：
- 固件 `main/notify/notify_player.cc:216-282`：HTTP GET 带 `Accept: audio/ogg, application/ogg`，数据喂给 OggDemuxer——只支持 Ogg Opus 单声道（`ogg_demuxer.cc`：首包必须 OpusHead 且声道数=1，次包必须 OpusTags，帧时长限 SILK 10/20/40/60ms、CELT 2.5/5/10/20ms 档）
- 服务端 `topic_generator.py _synthesize_tts`：doubao_v3 TTS 落盘 MP3（24kHz），URL 直接指 .mp3
- **任何 MP3 URL 推给该固件都必然失败**，与文件是否损坏无关

**根因 A（次要）——火山上游 MP3 尾部垃圾**：
- doubao_v3（`openspeech.bytedance.com/api/v3/tts/unidirectional`）每个响应都在 LAME 结束标记后附加 0xAA/0x55 字节
- ffmpeg/浏览器播放器忽略之（垃圾在有效流结束后）→ 用 MP3 播放器人工试听听不出问题，掩盖了格式不匹配

## 为什么长期未发现（三个盲区）

1. **MP3 浏览器可播**：管理端人工试听用浏览器/播放器验证音频文件本身，全部正常
2. **sent ≠ played**：服务端 `sent=1` 只代表消息送达 WS/心跳通道；设备 ACK 的也是"收到命令"而非"播放完成"（yh_protocol.cc:416-437 先 ACK 再异步播放）
3. **测试链路未含真实固件语义**：无模拟器按固件解复用规则判定 URL

## 修复（已上线）

- 补丁：`fixes/push-audio/topic_generator.py.fixed`（+`_ensure_device_playable_audio` 方法：落盘后 ffmpeg 校验时长 + 转码 Ogg Opus mono 24k 32k，删 MP3 中间产物，URL 改 .ogg；ffmpeg 缺失时降级保留原样并 WARNING）
- 部署：2026-10-15 17:59 备份（`topic_generator.py.bak-20261015T095759Z`）→ 上传 → py_compile 通过 → 重启 → 服务 active 无错误
- 端到端验证：API 触发真实推送 `push_1792058396143` → 产物 `topic-1792058396395-14c19fd13348.ogg`（5959B）→ 心跳通道直推 sent=1 → 模拟器判定 **PLAYABLE ✅**（4 页/75 包/1.5s/24kHz）
- 模拟器：`tests/push_chain_simulator.py`（忠实复刻固件 OggDemuxer 语义，可 check/check-file/scan 任意 URL）

## 遗留风险与建议

1. 火山上游 MP3 尾部垃圾值得向火山反馈（不影响修复后的链路，但污染产物）
2. tmp/ 无自动清理（41 文件/21MB 且会持续增长）→ 建议加 systemd timer 清理 7 天前文件
3. 推送无播放回执机制（sent≠played）→ 建议固件上报 NOTIFY_RESULT、服务端拆分 delivered/played
4. admin 页面删除任务按钮是假动作（仅 toast）；cron 任务只能等重启清除
5. MCP 工具 `self.notify.send` 的 audio_url 参数文档声称支持 mp3，实际固件只支持 ogg opus（第二入口，同根因）
