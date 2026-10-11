# 遗留低优先级修复 — 状态板（收口版）

**协调员**: general-purpose-4
**收口时间**: 2026-10-10 21:48 UTC+8（终版）
**轮次**: 20 agent 分 4 波 · 任务系统 22/22 全部 completed
**取证方式**: 队友报告 + 文件证据（git diff / 构建产物 / 交付文档 / 协调备忘录交叉验证）

## 最终状态板（agent | 任务 | 状态 | 产出 | 阻塞）

| # | Agent | 任务 | 状态 | 产出 | 阻塞 |
|---|-------|------|------|------|------|
| ① | agent-1 | 固件 NVS 唤醒词清空死锁 | ✅ 完成 | 8 文件：custom_wake_word(.h/.cc) ClearWakeWordCommands + default_commands_ 快照；audio_engine/afe_audio_engine/audio_service 三层透传 + pending_wake_word_clear_ 竞态防护；board.cc 空值触发清空；settings.cc EraseKey/EraseAll dirty_ 不落盘 bug 顺带修复；agent-12 终审 7 项全 PASS | 无 |
| ② | agent-2 | Python 推送改 device_config 格式 | ✅ 完成 | connection.py:971-981 device_config 下发 + register_connection/register_agent_device 零调用根修；推送改 `{"type":"device_config"}`；sent:0 根除，在线设备秒级热更新；另完成 8 关键文件远程→本地 md5 反向同步收口 | 无 |
| ③ | agent-5(三波)/agent-2 | Java 补齐 WakeWordController 等 + 重建部署 | ✅ 完成 | 22 文件同步（12 新增 + 9 覆盖 + 1 XML，33 Controllers）；GET/POST /agent/wake-word/{agentId} 全链 200；jackson-databind 降级修复；6 个错误码（10214-10219）；290 部署线全绿；回滚 .bak-wcdeploy | 无 |
| ④ | agent-3 实现 / agent-11 复核 | 固件拼音表次序 + 误导日志 | ✅ 完成 | 多字词条（小禾/哈喽/hello）前移表顶防逐字拆词；board.cc 按 SupportsDynamicWakeWords() 区分日志；custom_wake_word.cc 3 处 ESP_LOG 规范化 | 无 |
| ⑤ | agent-7/8/10/15/17 | TTS fallback / 403 快速失败 / 字幕保底 | ✅ 完成 | base.py 失败路径补发 FIRST 字幕；_is_fatal_tts_error 识别 8 种永久错误；EdgeTTS fallback（zh-CN-XiaoxiaoNeural）主备降级，venv 实测 ALL_FALLBACK_TESTS_PASSED；21:37 重启生效（agent-17 审计补的遗漏）；DB 默认音色统一官方 zh_female_xiaohe_uranus_bigtts | 无 |
| ⑥ | agent-8 | 前端 cc-console 修复 | ✅ 完成 | 双击竞态入口置位+启动令牌、watch 清残留、AbortController 120s、simBusy finally 重置、MediaRecorder try/catch；npm build 通过（dist 21:34） | 无 |
| ⑦ | agent-3/14/18/19/20 | 构建部署验证 | ✅ 完成 | 固件三件套 21:32-21:33（xiaozhi.bin 2,833,504B / assets 3.6MB / merged 12MB，二进制符号验证全 PASS）；E2E 推送复测全绿：Java POST 200 → Python → DB → bigscreen+小屏 2 设备实时收 device_config → TTS 字幕"你好小禾"闭环 | 无 |

## 交付文档（3 份）

1. `reports/2026-10-10-fix-delivery.md` — 修复交付文档（四大部分：ASR/TTS/唤醒词/遗留修复 + 运维注意 + 技术债清单 7 项）
2. `reports/FLASH-GUIDE-20261010.md` — 烧录与验证手册（6 项验证清单 + 阈值调优 + FAQ 8 条）
3. `reports/fix_wave_status_board.md` — 本状态板

## 依赖链结清

- **链 A**（①+④ → 固件重建）：✅ 结清。三项固件修复（NVS清空/拼音表/日志）全部包含进 21:33 重建产物
- **链 B**（②+③ → 端到端推送）：✅ 结清。服务器部署 + 设备实时推送闭环复测通过

## 阻塞与风险处置记录

1. **COM12 串口争用**（曾报高危）：两个 idf_monitor 会话互抢 COM12 → 备忘录已裁决"只保留一个会话"；agent-1 确认其任务仅改代码不占串口；构建完成后争用自然消除。状态：已解决
2. **CheckAssetsVersion 崩溃回溯**（曾报中危）：出现在 20:54 旧版产物烧录验证阶段；21:33 重建产物为权威版本（含三项新修复），手册明确"勿用 20:54 旧 merged"。状态：随重建解决，如复现按 FLASH-GUIDE FAQ Q1/Q2 排查
3. **merged-binary 旧版风险**：20:54 版本不含三项新修复，21:33:48 已补齐。状态：已解决（手册已警示）

## 协调备忘（供下轮参考）

1. **时间戳矛盾**：协调备忘录出现 22:10-23:30 条目，晚于本机时钟 21:41（备忘录文件 mtime 21:40）。推断为撰写 agent 时钟偏差或计划性时间戳；本板以文件证据（bin 21:32-21:33 / dist 21:34）为权威锚点，已上报 team-lead
2. **agent↔teammate 映射已确认**（据任务列表）：general-purpose-N 即 agent-N（gp-1=NVS死锁、gp-2=Java同步部署、gp-6=冲突审计、gp-7=TTS保底、gp-8=cc-console、gp-11=拼音表、gp-15=fallback分析、gp-16=端点验证+交付文档、gp-17=部署一致性审计、gp-18=回归测试）
3. **收尾差异已消除**：此前 4 项 in_progress（#8 gp-6 冲突审计 / #13 gp-16 Java端点验证 / #14 gp-16 交付文档 / #18 gp-18 e2e回归）经定向催收确认后，任务系统现已 22/22 全部 completed，与备忘录记载一致
4. 遗留技术债 7 项已在 fix-delivery.md 第四节登记（大屏/超小屏固件未同步移植为最大项）

## 事件日志

- [21:10] 初始化状态板，广播汇报通道
- [21:30] 无直接报告 → 转文件取证，7 项全部找到证据
- [21:32] 上报 COM12 争用 + CheckAssetsVersion 回溯两项阻塞
- [21:33] 定向催收 4 位 teammate（gp-1/2/3/5），附带串口协调
- [21:38] 读取交付文档 + 烧录手册 + 备忘录（含五波成果与收尾记录）
- [21:41] 验证最终产物（bin 三件套/dist），状态板收口，发最终汇报
- [21:42] 发现任务列表 4 项 in_progress 与备忘录矛盾，定向催收 gp-6/16/18
- [21:48] 22/22 全部 completed，矛盾消除，状态板终版闭环
