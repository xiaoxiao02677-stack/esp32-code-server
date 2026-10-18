# 项目总结 · 备份分支 261012-backup

> 本分支为 2026-10-12 建立的**完整项目备份**（含全量源码、固件、服务端、AOCI 治理产物）。
> 用途：归档当前进度、记录尚未完善的问题、列示后续待上线功能。
> 归档时间：2026-10-12；分支：`261012-backup`。

---

## 一、当前项目情况

### 1. 总体架构
- 仓库内容：yuhe-esp32 智能音箱固件 + 配套服务端（`manager-api` / `yuhe-server`）+ 管理后台。
- 固件端已拆分为两个 **AOCI 受管子项目**：
  - **大屏** `code/big_secreen/yuhe-esp32`（板级源 `main/boards/bigscreen-s3/`）
  - **小屏** `code/small_secreen/yuhe-esp32`（my-s3-tft 圆屏 + audio 引擎改造）
  - `code/super_small_screen` 为独立目录，**非 AOCI 项目**。
- 服务端镜像 `code-server-mirror/`：Java `manager-api` + Python `yuhe-server`。
- 管理后台：`console-v2`（含 `dist` 构建产物）、`cc-console`。

### 2. 固件进展
- 小屏 my-s3-tft：自定义唤醒词链路（`custom_wake_word`）、AFE 音频检测、audio_service / audio_engine、WebSocket 协议、OTA。
- 大屏 bigscreen-s3：首方板级源已建 FRAS 条目并升 `index`（`config.h`/`config.json`/`*.md`/`bigscreen_display.cc` 等）。
- AOCI 索引：两仓库均完成 Volumes v1 基线（大屏 index≈1081 / 小屏 index≈1074）。`governance_aligned: false` 为**结构性良性状态**（scope 策略指纹不符，非内容漂移，code_drift 恒为空）。

### 3. 服务端进展
- 唤醒词推送改造：`WakeWordService` 注册于 `connection.py` 的 hello/device_register，推送格式固定为 `{"type":"device_config","payload":{"wake_word":[...]}}`；空数组/空串 = 清空回默认词。
- 记忆引擎（`mem_holographic`）、TTS/ASR、记忆时间线、推送调度等模块已落地。
- Java 构建需注意：测试代码滞后于构造器变更，部署用 `-Dmaven.test.skip=true`；部署前核对 jar 内 Controller 数量。

### 4. 已完成的治理 / 交付
- 双仓库递归 reconcile（小屏：38 文件内容指纹刷新 / 8 新文件入 observe / 1 已删文件移除；大屏已最新）。
- 全量上传 gitee：`main` 与 `master` 已同步（31,520 文件），本 `261012-backup` 分支为带总结的完整备份。

---

## 二、尚未完善的问题

1. **私钥安全**：gitee 旧快照曾上传两把证书私钥（`aoci-code/.../certs/*.key`），已从当前树清除，但历史上传记录可能残留，相关凭据**必须轮换 / 撤销**。
2. **AOCI 基线归属**：`baseline.json` 被 `.gitignore` 意图忽略却已被 git 追踪，每次 reconcile 都会产生 diff，治理产物归属需理顺。
3. **构建环境**：防病毒反复杀构建进程，需 ninja 前台直跑 + 增量续跑；`merged-binary.bin` 偶发滞后，全量烧录前须核对三产物（yuhe.bin / generated_assets.bin / merged-binary.bin）时间戳一致。
4. **烧录规范**：assets 分区变更必须 USB **全量烧录**（OTA 只刷 app 分区，不改 assets），否则设备行为与 bin 不符。
5. **串口独占**：小屏 COM12 单设备单 idf_monitor 会话，两个会话争用互报 `PermissionError(13)`；烧录前须确认无残留 monitor 进程。
6. **Java 构建**：测试代码滞后于构造器，部署需 `-Dmaven.test.skip=true`；部署前核对 jar 内 Controller 数量，避免旧 jar 端点 404。
7. **TTS 音色**：私有复刻音色（`S_` 前缀）授权随免费额度耗尽自动失效（403 code=45000030），**禁止入 DB**；推荐官方音色（TTS_DoubaoV3_V01 / zh_female_xiaohe_uranus_bigtts）。
8. **设备配置生效**：device_config 改库后需设备重连或推送才生效，光改库不生效。
9. **Windows 保留名**：仓库根曾出现保留名文件 `nul` 导致 reconcile 崩溃，已加 RESERVED 跳过逻辑并隔离至 `.trash/`。

---

## 三、以后需要上线的功能（规划）

1. **大屏 bigscreen-s3**：完整功能联调、量产烧录与验收。
2. **小屏音频引擎**：多引擎 / 新 SR 模型端到端验收与稳定性打磨。
3. **服务端**：记忆引擎完善、WeChat OpenClaw 集成、PushScheduler / TimelineChart 等后台管理功能正式上线。
4. **唤醒词 OTA 推送**：生产环境大规模设备验证与灰度发布。
5. **多设备 / 多租户**管理能力建设。
6. **AOCI 治理自动化**：持续 reconcile + 基线健康监控，理顺 `baseline.json` 归属。
7. **密钥与证书管理规范化**：排除私钥、定期轮换、CI 扫描防泄漏。
8. **统一 CI/CD 与一键部署**：大屏 + 小屏 + 服务端流水线。

---

*归档于 2026-10-12，分支 `261012-backup`。本分支 = 当前完整项目 + 本总结文档。*
