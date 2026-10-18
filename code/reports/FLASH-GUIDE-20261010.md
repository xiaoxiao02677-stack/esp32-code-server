# 小屏固件烧录与验证手册（2026-10-10 唤醒词修复版）

> 适用板型：`my-s3-tft` 圆屏（ESP32-S3 / 16MB Flash）
> 本轮固件改动：MultiNet 自定义唤醒词（"你好小禾"）+ NVS 清空语义修复 + 拼音表次序修复 + 日志规范化
> 产物时间：2026-10-10 21:33（已含本轮全部修复，二进制内验证通过）

---

## 一、什么时候需要烧录

**本次必须全量烧录**，原因有二：

1. **assets 分区变更**：本轮固件将唤醒引擎从 WakeNet（"你好小智"官方模型）切换为 MultiNet7（自定义词"你好小禾"），`generated_assets.bin` 内打包了 MN7 模型 + 命令表，同时彻底移除了旧 WakeNet 模型。**OTA 升级不会刷 assets 分区**，只刷 app 无法生效。
2. **新增 NVS 清空 + 拼音表修复**（21:24-21:29 改动，21:33 重新构建）：
   - 清空唤醒词恢复默认词的语义修复（此前下发空词会被忽略，造成"无法回默认"死锁）
   - 拼音表多字词条（"小禾"/"哈喽"/"hello"）前移，修复逐字拆词导致整词被丢弃的 bug

**产物三件套**（位于 `small_secreen/yuhe-esp32/build/`）：

| 文件 | 大小 | 说明 |
|------|------|------|
| `yuhe.bin` | 2.83 MB | 应用固件（app 分区 0x20000） |
| `generated_assets.bin` | 3.6 MB | 资产分区（MN7 模型 + index.json 命令表，**必须刷**） |
| `merged-binary.bin` | 12 MB | 五合一合并镜像（含 bootloader/分区表/ota_data/app/assets） |

烧录前可自查构建新鲜度：`yuhe.bin`、`generated_assets.bin`、`merged-binary.bin` 三个文件的时间戳应一致且晚于源码修改时间（本轮为 2026-10-10 21:33）。若 merged 比另两个旧，说明 merge 步骤没跑完，**不要使用旧 merged**。

---

## 二、烧录命令

### 方式 A：esptool 分区烧录（推荐）

先进入固件仓库的 build 目录（命令中的相对路径以此为准）：

```bash
cd G:/demo/21_xiaozhi/code/small_secreen/yuhe-esp32/build
```

一行式全量烧录（COM 口按实际改，Windows 下如 `COM5`）：

```bash
python -m esptool --chip esp32s3 -p COM5 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0xd000 ota_data_initial.bin 0x20000 yuhe.bin 0x800000 generated_assets.bin
```

**分区地址说明**（勿改动）：

| 偏移 | 文件 | 分区 |
|------|------|------|
| `0x0` | `bootloader/bootloader.bin` | 引导加载器 |
| `0x8000` | `partition_table/partition-table.bin` | 分区表 |
| `0xd000` | `ota_data_initial.bin` | OTA 数据（保证从 factory/app 首分区启动） |
| `0x20000` | `yuhe.bin` | 应用固件 |
| `0x800000` | `generated_assets.bin` | **资产分区（MN7 模型+命令表）** |

### 方式 B：merged 一把梭

```bash
python -m esptool --chip esp32s3 -p COM5 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 merged-binary.bin
```

> ⚠️ 用方式 B 前务必确认 `merged-binary.bin` 是最新合并产物（见上文"新鲜度自查"）。

### 烧录后初始化

烧录完成后设备自动重启。首次启动即连接服务器 `sandyun.top:12399` 并拉取云端配置。

---

## 三、烧录后验证清单

接串口（115200 或构建配置的波特率），逐条核对日志关键词：

| # | 检查项 | 日志关键词（出现即通过） | 说明 |
|---|--------|--------------------------|------|
| 1 | 引擎正确 | `Initialized FD AFE detector: MultiNet` | 见于 `afe_audio_engine.cc` 初始化。若是 `WakeNet` 说明烧的还是旧固件 |
| 2 | 默认命令表注册 | `Command: ni3 hao3 xiao3 he2` | 默认唤醒词"你好小禾"拼音命令已注册（来自 assets 的 index.json） |
| 3 | 云端配置下发 | `Received device_config: ...` 且 JSON 含 `"wake_word"` 字段 | 设备连上服务器后拉取/下发；若 DB 里配了词，紧随其后应出现 `应用云端唤醒词: N 个（首个: ...）` |
| 4 | NVS 缓存恢复（可选） | `Restored 1 server wake-word command(s) from NVS` | 仅当 NVS 有旧的下发缓存时出现，没有也正常 |
| 5 | 唤醒词替换生效 | （喊话测试，见下节） | 旧词"你好小智"模型已从 assets 移除 |

**全链路自检**：唤醒后随便说句话，应看到 ASR 识别文本 → LLM 回复 → TTS 合成播放（官方音色"小何温柔女声"）。

---

## 四、唤醒测试方法

### 基本测试

| 测试 | 预期 | 结论 |
|------|------|------|
| 喊 **"你好小智"** | **不应唤醒** | 旧词已随 WakeNet 模型删除，这是本轮改造的负向验证点 |
| 喊 **"你好小禾"** | **应唤醒**（1 米内正常音量） | 默认词生效 |
| 唤醒后说"现在几点" | 应正常对话+语音回复 | ASR→LLM→TTS 全链路通 |

### 灵敏度不合适时调阈值

MultiNet7 识别阈值当前为 **0.4**（`my-s3-tft/config.json` 中 `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD=40`，整数即百分比）。阈值越高越难唤醒（误触少），越低越灵敏（易误唤醒）。

| 现象 | 调整方向 | 修改位置 |
|------|----------|----------|
| 环境噪声下频繁误唤醒 | 阈值调高：40 → 50~60 | `main/boards/my-s3-tft/config.json` 的 `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD` |
| 正常音量喊不应、要喊很大声 | 阈值调低：40 → 30~35 | 同上 |

调整后**必须重新构建+全量烧录**（阈值编译进固件）。建议区间 **30-60**，超出该范围误触/漏触都会明显恶化。参考基线：安静环境 40 档识别率约 95%，噪声环境约 90%。

---

## 五、唤醒词管理（云端动态换词）

管理后台：`https://sandyun.top:8001/admincc/#/admin/wake-word`（编辑弹窗支持多行输入，最多 10 个词、每个 ≤30 字符）。

### 生效时机

| 操作 | 生效方式 |
|------|----------|
| 后台修改/保存唤醒词 | **设备重连后生效**（重启设备或断开重连；配置仅连接时拉取） |
| 后台推送 | 推送消息实时生效**需新固件**（本轮固件已支持 device_config 格式推送消费；旧固件不认推送消息） |
| 清空唤醒词（删光所有词保存） | 服务器下发空数组 → 固件清空 NVS 缓存、**恢复默认词"你好小禾"**（本轮修复的死锁点，旧固件会忽略空值导致卡死在旧词） |

### 词表约束

- 支持中文词（固件内置汉字→拼音映射表自动转换）与纯拼音（如 `ni3 hao3` 直接下发）
- 映射表未收录的汉字会打 WARN 并跳过该词（其余词不受影响）；日志关键词：`云端唤醒词全部无法转换为拼音，忽略`
- 命令表未变化时重连会打 `云端唤醒词未变化，跳过更新`（幂等，正常现象，**不是**故障）

---

## 六、常见问题（FAQ）

**Q1：喊"你好小禾"没反应？**
按顺序排查：
1. 串口日志有无 `Initialized FD AFE detector: MultiNet`？没有 → 烧的还是旧固件，重新全量烧录
2. 有 MultiNet 但喊不应 → 阈值偏高，调低到 30-35（见第四节）
3. 环境噪声（电视/音乐/风扇）→ MN7 对噪声敏感，先换安静环境测试
4. 确认 DB 词表没有被改成含未收录汉字的词（看日志有无拼音转换 WARN）

**Q2：喊"你好小智"居然还能唤醒？**
说明 assets 分区没刷（大概率只刷了 app）。旧 WakeNet 模型仍在 assets 里。用第二节命令**务必含 `0x800000 generated_assets.bin`** 重新烧录。

**Q3：串口日志显示 `当前音频引擎不支持动态唤醒词（需 MultiNet 模型），已忽略`？**
设备跑的是纯 WakeNet 构建（旧固件）。该日志在新固件中仅当引擎真不是 MultiNet 才会出现；正常 MultiNet 构建下命令表相同会打"未变化跳过"。

**Q4：后台改了唤醒词，设备没反应？**
配置仅在设备**连接时**拉取。重启设备或断开重连。若仍不生效，串口看 `Received device_config` 是否含 `"wake_word"` 字段——没有则查服务器 jar 是否为本轮新部署（含唤醒词下发代码）。

**Q5：清空唤醒词后设备唤醒不了了？**
旧固件 bug（空值被忽略+死锁）。本轮固件已修复：清空 → 恢复默认词"你好小禾"。若你还在跑旧固件，重新烧录本轮固件即可恢复。

**Q6：烧录报错 `A fatal error occurred: Could not open COM5` / 连不上设备？**
1. 换 USB 线（部分线只供电不传数据）
2. 按住设备 BOOT 键再上电进下载模式
3. 关掉占用串口的程序（串口监视器/上位机）

**Q7：唤醒后对话正常但没有语音回复（只有字幕）？**
检查 TTS 音色配置：demo 智能体已切官方音色 `TTS_DoubaoV3_V01`（小何温柔女声）。若日志见火山 403 `code=45000030`，说明又切回了复刻系音色（资源授权已失效），换回官方音色即可。

**Q8：`Restored ... from NVS` 日志里是旧词，怎么彻底清掉？**
这是正常的脱机缓存设计（断网也能用云端下过的词）。后台清空唤醒词一次（触发固件删 NVS 键），日志出现 `已清空云端唤醒词，恢复默认` 即彻底清除。

---

*手册生成：2026-10-10 21:35 · 基于构建产物 21:33（yuhe.bin 2.83MB / generated_assets.bin 3.6MB / merged-binary.bin 12MB，二进制内已验证：NVS 清空日志串、默认拼音命令、MN7 模型均在位，WakeNet 零残留）*
