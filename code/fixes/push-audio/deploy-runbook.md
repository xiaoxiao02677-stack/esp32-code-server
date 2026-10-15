# 推送音频修复部署手册（topic_generator Ogg Opus 转码）

## 变更摘要

- **改什么**：`core/services/topic_generator.py` 的 `_synthesize_tts` 在 TTS 落盘后新增 `_ensure_device_playable_audio` 调用——ffmpeg 校验时长并转码为 **Ogg Opus 单声道 24k**，成功后删除 MP3 中间产物、audio_url 指向 `.ogg`。
- **为什么**：固件 NotifyPlayer 的 OggDemuxer 只支持 Ogg Opus 单声道（OpusHead+OpusTags+mono），MP3 一律报 "Notification Ogg stream ended before a complete audio stream"。今日 11 次推送全部因此失败。
- **影响面**：仅推送管线音频格式。对话语音回复走 WS opus 帧（sendAudioHandle），不经 topic_generator，不受影响。
- **降级行为**：服务器无 ffmpeg → 保留 MP3 现状 + WARNING 日志；转码失败 → 删除产物抛错 → push_scheduler 置 audio_url="" 仅推字幕（字幕链路始终可用）。

## 前置检查（已由主 agent 于 17:53 完成）

| 项 | 结果 |
|---|---|
| 生产 topic_generator.py md5 | `c4f5dba079f0f295b265ac4b35b14c33`（与补丁基准 orig-prod 一致）|
| 服务状态 | active（重启于 10-14 20:56）|
| ffmpeg 6.1.1 + libopus | ✅ 存在（批量 41 样本转码 100% 成功，均耗时 0.43s）|
| 负载 | load 0.01，内存可用 2GB |
| tmp 规模 | 41 mp3 / 21MB（无自动清理，见遗留风险）|
| 隔离实测 | 4 场景全过（真实样本转码 60770B 合法 ogg）|

## 部署步骤（逐条执行）

```bash
# 1) 备份原版（带 UTC 时间戳）
ssh -p 22222 root@sandyun.top 'cp /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py.bak-$(date -u +%Y%m%dT%H%M%SZ)'

# 2) 上传补丁版本
scp -P 22222 G:/demo/21_xiaozhi/code/fixes/push-audio/topic_generator.py.fixed root@sandyun.top:/root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py

# 3) 语法校验 + md5 确认
ssh -p 22222 root@sandyun.top '/root/xiaozhi-server/main/xiaozhi-server/.venv/bin/python -m py_compile /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py && echo COMPILE_OK'

# 4) 重启服务（WS 设备瞬断 10-30s，心跳设备自动重连）
ssh -p 22222 root@sandyun.top 'systemctl restart xiaozhi-server && sleep 3 && systemctl is-active xiaozhi-server'

# 5) 健康检查：日志无 ERROR、设备开始重连
ssh -p 22222 root@sandyun.top 'sleep 10; tail -30 /root/xiaozhi-server/main/xiaozhi-server/tmp/server.log | grep -aiE "error|exception" | head; echo "---"; grep -ac "hello" /root/xiaozhi-server/main/xiaozhi-server/tmp/server.log'
```

## 验证（部署后）

```bash
# A) 管理页发 1 条即时推送：https://sandyun.top:8001/#/admin/push-scheduler
#    topic_sources 任选（memory/weather/chat），设备选在线设备

# B) 确认产物为 .ogg
ssh -p 22222 root@sandyun.top 'ls -la --time-style=+%T /root/xiaozhi-server/main/xiaozhi-server/tmp/topic-*.ogg | tail -3'

# C) 模拟器判定（固件语义）
cd G:/demo/21_xiaozhi/code && python tests/push_chain_simulator.py check http://sandyun.top:8003/audio/<新文件名>.ogg
# 预期：PLAYABLE ✅ pages/packets/duration 合理

# D) 浏览器直接开 URL 能播（ogg 原生支持）

# E) 真机（用户）：设备空闲时推送 → 完整播放无中断 + 屏幕字幕正常
```

## 回滚

```bash
ssh -p 22222 root@sandyun.top 'BAK=$(ls -t /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py.bak-* | head -1) && cp "$BAK" /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py && /root/xiaozhi-server/main/xiaozhi-server/.venv/bin/python -m py_compile /root/xiaozhi-server/main/xiaozhi-server/core/services/topic_generator.py && systemctl restart xiaozhi-server && systemctl is-active xiaozhi-server'
```

## 观察期（24h）

```bash
# 转码成功/降级频率
ssh -p 22222 root@sandyun.top 'grep -a "推送音频" /root/xiaozhi-server/main/xiaozhi-server/tmp/server.log | tail -20'
```

## 遗留风险（本次不处理，已记录）

1. 火山 doubao_v3 上游 MP3 尾部 0xAA/0x55 垃圾字节（复现 6/6，建议向火山反馈）
2. tmp/ 无自动清理，无限增长（建议后续加 systemd timer 定时清 7 天前文件）
3. 推送无播放回执：sent ≠ played，管理页看不到设备真实播放结果
4. admin 页面删除任务按钮是假动作（仅 toast）
5. MCP 工具 self.notify.send 的 audio_url 参数文档声称支持 mp3，实际固件只支持 ogg opus（第二入口，同根因）
