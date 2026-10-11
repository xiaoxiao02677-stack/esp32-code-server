# 待机唤醒不生效 — 紧急修复状态板

**协调员**: general-purpose-5
**开启时间**: 2026-10-10（用户催：agent拉满赶快修复）
**故障现象**: 烧录 21:33 固件后，待机喊"你好小禾"无反应
**日志证据**: MultiNet 检测器激活 ✅、服务器下发 wake_word ✅、**缺 "Command: ni3 hao3..." 命令注册日志** ❌

## 嫌疑排序（初始）

1. **拼音带声调格式 MN7 不认**（最高嫌疑）— esp-sr 官方 README 示例不带调："da kai kong tiao" vs 我们的 "ni3 hao3 xiao3 he2"
2. index.json 命令解析失败 / NVS 状态异常
3. assets 挂载时序 / index.json 读取失败

## 波次 1：根因调查（4 agent + 协调员独立复核）

| Agent | 任务 | 状态 | 结论摘要 |
|-------|------|------|----------|
| A=agent-2（格式调研员） | MN7 命令格式规范查证 | ✅ 交付 | 三重证据：mn7_cn 模型 vocab 零带调 token；esp_mn_commands_add 内部拒绝带调拼音并打 "invalid command"；官方工具 lazy_pinyin 无调输出 |
| B=agent-4（固件排查员） | 固件侧命令注册与检测链 | ✅ 交付 | device_config 消费链全通（ApplyDeviceConfig→UpdateWakeWordCommands），固件链路无断点 |
| C=agent-7（服务端排查员） | 服务端格式与残留排查 | ✅ 交付 | 服务器零残留：拼音转换职责全在固件 board.cc，服务器只发汉字 |
| D=agent-3（资源排查员） | assets 挂载时序与 index.json | ✅ 交付 | 分区表无独立 model 分区，esp_srmodel_init 走 assets models_list，时序链无 bug；指出 multinet_model 段缺失静默为可观测性缺陷（建议补 LOGW，本轮未纳入）；用户 21:33 烧录可能只刷 app 未刷 assets（双因叠加） |
| **协调员（gp-5）** | **独立交叉复核** | ✅ 完成 | **见下** |

### 协调员独立复核结论（文件物证）

1. **官方格式规范 = 无调拼音**（四重证据）：
   - esp-sr v2.4.7 `tool/README.md` + `model/multinet_model/fst/commands_cn.txt`：全部示例无调（`da kai kong tiao`）
   - `tool/multinet_pinyin.py`（官方 G2P 工具）实测输出：`你好小禾` → `ni hao xiao he`（无调，lazy_pinyin 默认 Style.NORMAL）
   - esp-sr `Kconfig.projbuild` 上游默认 `CONFIG_CUSTOM_WAKE_WORD="xiao tu dou"`（无调）
   - `esp_mn_speech_commands.c`:116 中文走 `#else` 分支：字符串**原样**传入 MN7 的 `check_speech_command`，格式不符则拒绝（ESP_ERR_INVALID_STATE）并打 `invalid command, please check format` 错误日志

2. **烧录产物物证（决定性）**：`build/generated_assets.bin`（21:45，即 21:33 烧录批次）内 `index.json` 的 `multinet_model.commands[0].command = "ni3 hao3 xiao3 he2"`（带调）——与 sdkconfig `CONFIG_CUSTOM_WAKE_WORD="ni3 hao3 xiao3 he2"` 一致。assets 内**无**无调版本。

3. **固件侧放大缺陷**（为何没有任何错误日志暴露）：`custom_wake_word.cc` `Initialize()` L165-169 与 `UpdateCommands()` L228-232 调用 `esp_mn_commands_add()` **均不检查返回值** → MN7 拒绝带调拼音时命令**静默注册失败**，无 ESP_LOGE 记录（esp-sr 内部的 `invalid command` 错误日志属于 MN_COMMAND TAG，或被日志级别/启动刷屏淹没）。

4. **"Command:" 日志缺失的解释**："Command: ..." 日志仅在 `ParseWakenetModelConfig()`（index.json 路径）打印，且在 cJSON 三字段校验通过后打印。用户日志缺此行有两种可能：
   - a) `multinet_model` JSON 解析失败/字段缺失（agent-D 需确认 assets 挂载时序）
   - b) **更可能**：日志被启动刷屏/日志级别吞掉，或该轮启动走了 NVS 恢复路径（`Restored N server wake-word command(s)`，L159）
   - 但**无论 a/b，核心矛盾不变**：即便命令注册成功，带调拼音 MN7 检测也不认（模型无法匹配发音序列）

5. **根因裁决（高置信度）**：**拼音带声调格式 MN7 不认**。修复 = 全链路去调：
   - 固件 `board.cc` 汉字→拼音表（`ni3 hao3 xiao3 he2` 等）→ 改为无调（`ni hao xiao he`）
   - `my-s3-tft/config.json` + `sdkconfig` 的 `CONFIG_CUSTOM_WAKE_WORD` 去调
   - 服务器下发的 `wake_word` 字段同步去调（服务端 pinyin 生成逻辑需 agent-C 确认）
   - 重建 assets（index.json 命令表随 sdkconfig 重新生成）+ 重建固件
   - **建议顺带根修**：`esp_mn_commands_add` 返回值检查 + 失败时 ESP_LOGE，杜绝静默失败复发

### 与嫌疑清单的对照

- 嫌疑 1（拼音带调）：✅ **证实**（物证+官方工具+上游默认三重）
- 嫌疑 2（index.json 解析/NVS）：⚠️ 部分存疑——即便解析成功，带调也不认；但 NVS 缓存里同样存的是带调串，清 NVS 不能根治
- 嫌疑 3（assets 挂载时序）：⏳ 等 agent-D；但"MultiNet 检测器激活"日志已证明模型加载成功，此嫌疑降级

## 根因共识与分歧

**共识（全 agent + 运行时证据一致）**：根因 = 拼音带声调格式 MN7 不认（`ni3 hao3 xiao3 he2` 被模型 check_speech_command 拒绝）。修复 = 全链路去调 + NVS 自愈 + 返回值检查。

**补充发现（agent-3）**：用户 21:33 烧录可能只刷 app 未刷 assets（app-flash 不写 0x800000 分区）——故障为"带调拼音 + 可能未刷 assets"双因叠加，烧录终版 merged（0x0 整烧）可同时消除两因。

**分歧**：无。各路调查结论互相印证。

## 最终修复清单（全部完成）

1. board.cc 拼音表全量去调 + 多字词条置顶（agent-6，22:11）
2. my-s3-tft/config.json `CUSTOM_WAKE_WORD="ni hao xiao he"`（agent-6，22:11）
3. NVS 带调自愈：检测字母+数字1-5 → 丢弃 + EraseKey + 回落默认（agent-6）
4. settings.cc EraseKey/EraseAll dirty_ 落盘修复（自愈依赖）（agent-6）
5. esp_mn_commands_add/update 返回值检查 ×3 处，防静默失败回归（agent-6，22:18）
6. 服务端 wake_word_service.py 改发 device_config + 鉴权修复（agent-7 线）
7. 终版三件套：xiaozhi.bin + generated_assets.bin + merged-binary.bin（agent-8，22:44，四项内容验证全 PASS）

## 波次 2：修复实施（已由某 agent 启动，22:11-22:15 进行中）

**实测修复进度（文件 mtime + 内容验证）**：
| 项 | 状态 | 证据 |
|----|------|------|
| board.cc 拼音表去调 | ✅ 22:11 | 全表无调（`{"小禾","xiao he"}`），多字词条置顶，注释更新 |
| my-s3-tft/config.json | ✅ 22:11 | `CONFIG_CUSTOM_WAKE_WORD="ni hao xiao he"` |
| sdkconfig 重建 | ✅ 22:14+ | 旧文件已删，新生成值无调（1188 行） |
| assets 重建 | ✅ 22:13 | generated_assets.bin 内 index.json 命令="ni hao xiao he"，带调串已消失 |
| NVS 带调自愈 | ✅ 已实现 | custom_wake_word.cc L139-159：legacy_toned 检测→丢弃→EraseKey |
| settings.cc EraseKey 落盘 | ✅ 已实现 | dirty_ 置位修复（自愈删除依赖此） |
| 服务端推送格式 | ✅ 已改 | wake_word_service.py 改发 device_config + handler 鉴权修复 |
| xiaozhi.bin 固件重建 | 🔄 22:15 进行中 | 21:50 的 bin **不含** 22:11 board.cc 修改，须等新构建 |
| merged-binary | ⏳ 待新 bin | 21:50 版已过时 |

**⚠️ 剩余缺口（协调员核查后：3→2 项）**：
1. **`esp_mn_commands_add` 返回值不检查**（custom_wake_word.cc L190/L253/L304 三处）——静默失败缺陷未根修，下次格式错误仍无日志可查
2. **21:50 xiaozhi.bin 不含去调修复**——烧录必须等 22:15 构建完成的新 bin（防拿旧件再烧一次）
3. ~~服务器直发拼音透传风险~~ **已排除**（22:20 协调员核查）：DB `ai_device_config.wake_word`="你好小禾"（汉字，12:12 更新）；Java ConfigServiceImpl 只做白名单透传（≤32字符/≤5项），无 pinyin 生成代码；Python 端 config.yaml 全局 wakeup_words 全为汉字。服务器永远下发汉字，由固件 HanziToPinyin 无调表转换——链路安全

### 任务系统状态（22:18 核查）
- #1 [completed] 等待 agent-6 完成 board.cc 拼音去调修复 → **波次 2 实施者=agent-6（gp-3?）**
- #2 [in_progress] 执行固件构建（my-s3-tft）→ CMake 配置完成（22:15），编译中（242/1480 @22:25）

### 跨固件影响排查（22:25 协调员补查）
- **小屏**（small_secreen/my-s3-tft）：唯一受影响设备，修复中 ✅
- **大屏**（big_secreen）：`CONFIG_USE_AFE_WAKE_WORD=y`（WakeNet 路线，无 MultiNet 命令表），board.cc 无拼音表 → 不受影响
- **超小屏**（super_small_screen）：纯 C 精简工程（main.c 100 行），无唤醒词功能 → 不受影响
- 结论：无需跨固件修复，历史技术债"大屏/超小屏未同步移植"反而使它们幸免

## 事件日志

- [开始] 初始化状态板，等待 4 份 agent 报告
- [T+15min] 协调员完成独立交叉复核：四重证据（官方工具实测/commands_cn.txt/Kconfig 上游默认/esp-sr 源码 #else 分支）+ assets.bin 物证，裁决根因=带调拼音 MN7 不认；固件侧 `esp_mn_commands_add` 返回值不检查为放大缺陷（静默失败）。已上报 team-lead
- [22:11-22:15] 发现波次 2 已被某 agent 启动：board.cc/config.json 去调（22:11）、assets 重建（22:13）、sdkconfig 重生成（22:14）、固件构建中（22:15）。NVS 自愈+settings.cc 落盘修复+服务端 device_config 改造均已就位。剩余 3 缺口（返回值检查/旧 bin 风险/服务端直发拼音透传）已记录并上报
- [22:18] 任务系统确认：波次 2 实施者=agent-6（任务#1 completed），构建任务#2 in_progress（CMake 配置完成）
- [22:20] 缺口 3 排除：DB/Java/Python 三层核查，服务器只下发汉字，无带调拼音风险。剩余缺口 2：返回值检查（可后补）+ 等新 bin 烧录（关键路径）
- [22:23] 新 xiaozhi.bin 产出（2,834,144B，22:23:24，构建日志 20616）。同刻发现 COM6 串口监控日志（61076）在跑
- [22:28] **运行时实锤闭环**：设备日志捕获 `E MN_COMMAND: invalid command, please check format, ni3 hao3 xiao3 he2`（I(9808)/I(131948) 嗨小禾 hai1 xiao3 he2 同拒）+ `No commands available, not updating` + 活跃表仅剩 MN7 自带 313 条 → 根因机理 100% 确认
- [22:28] 判定设备仍跑旧固件（无自愈日志+推送转换仍带调）。待烧录：22:23 bin + 22:13 assets（merged 21:50 过时）；COM6 被 monitor 占用需先释放。已上报 team-lead
- [22:30] 任务#2 completed（构建日志 57720：bin 2,834,144B）。**merged-binary 22:23:58 已重打**（含新 bin+新 assets，验证：带调=-1/无调@190667/自愈串@191132）——三件套全部就绪且内容验证通过。COM6 monitor（61076）已于 22:23:31 停更，等待烧录执行
- [22:37] ⚠️ build 目录 22:36:46 被整删，22:23 三件套全部丢失。初判"高危"后经记忆文件澄清：**有意删除**——agent-6 的返回值检查补丁在 22:23 构建后才完成，需重建才能包含。补丁已验证（3 处 add esp_err_t + 3 处 update esp_mn_error_t* 检查，API 语义正确）。等 agent-8 重建
- [22:39] 缺口清单更新：缺口1（返回值检查）✅ 已入源码；缺口2（等含补丁的新 bin）🔄 等待 agent-8 构建；缺口3 已排除。最终产物预期 = 拼音去调 + NVS 自愈 + 返回值检查三项全含
- [22:40] agent-8 重建启动（CMake 配置中，日志 54164）。源码定格 22:18 版（含三项核心修复；multinet_model 缺失 LOGW 未纳入，属增强项下轮）。监控挂好，bin 产出即复检
- [22:44] **🎯 终版三件套产出并复检全 PASS**：xiaozhi.bin（22:44:35，带调-1/无调@59595/自愈@60060/**返回值检查@59232**）+ assets（22:40:49，带调-1/无调@3570694）+ merged（22:44:38 重打）。增量构建仅 4.5 分钟。已通知 team-lead 烧录要点（整烧 merged 0x0 + 三连验证）。**协调员任务闭环**
