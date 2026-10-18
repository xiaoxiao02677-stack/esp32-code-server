# 实时打断（Server AEC）+ NVS 崩溃修复 + 壁纸双源：根因与烧录验收清单

> 2026-10-17 23:40 三次更新 · 新增根因 5：**原厂固件的实时打断走服务端 AEC，我们 config 把它关了**
> 覆盖修复：①打断阈值链路 ②NVS 0x1107 崩溃 ③开机/背景壁纸用用户图 ④**Server AEC 实时打断（本轮新增）**

## 根因（两条，主次分明）

### 1. 主根因：固件代码从未编译进设备固件
`interrupt_threshold` 的全部固件消费代码都是**未提交、未编译**的工作区改动：

| 文件 | mtime | 内容 |
|---|---|---|
| main/audio/engines/afe_audio_engine.h | 19:39:48 | NVS 恢复 + atomic 成员 |
| main/audio/engines/afe_audio_engine.cc | 19:40:11 | SetInterruptThreshold + UpdateVadState |
| main/audio/audio_service.cc | 19:40:28 | 转发层 |
| main/boards/common/board.cc | 20:41:23 | device_config 解析 + NVS 写入 |

而 `build/yuhe.bin` 编译于 **19:20:57**——代码全部晚于编译。

**二进制铁证**：`yuhe.bin` 里 `wake_word_threshold` 字符串 FOUND@0xe8da（同期功能，工作正常），
而 `interrupt_threshold`、`云端实时打断阈值已更新`、`SetInterruptThreshold` 符号全部 NOT FOUND。

⇒ 设备收到 `interrupt_threshold` 帧后**静默忽略**（cJSON_GetObjectItem 拿不到键就不动），
一直用编译期默认 `CONFIG_YH_VAD_SPEECH_CONFIRM_MS=300`（≈15 档）。

### 2. 前置条件：yh-154tft-wifi 版型语音打断整体关闭（设计行为）
`application.cc:1441`：Speaking 态只有 `Realtime 模式 && IsDeviceAecEffective()` 才开 VAD。
- `yh-154tft-wifi` 用 `NoAudioCodecSimplex`（单工 I2S，无回采通道）→ `IsDeviceAecEffective()` 恒 false
- 其 config.json 只有 `CONFIG_USE_SERVER_AEC=n`，没配 `CONFIG_USE_DEVICE_AEC` → aec_mode_=kAecOff
- ⇒ Speaking（播报）期间 VAD 完全关闭，**无论阈值调多少都无法语音打断**
- 仅 `yh-cam` 有 AEC 回采（`CONFIG_USE_DEVICE_AEC=y` + BoxAudioCodec）
- 替代打断路径：播报中喊**唤醒词**可打断（application.cc:1266，不依赖 AEC）

### 3. 同批修复：NVS 0x1107 崩溃（触发唤醒词/语音/LLM 即重启）
症状：设备一触发唤醒词就 `ESP_ERROR_CHECK failed: esp_err_t 0x1107 (ESP_ERR_NVS_INVALID_HANDLE)` 重启。
根因是两个叠加：
- **NVS 命名空间超长**：`NVS_NS_NAME_MAX_SIZE=16` 含 null 终止符，有效字符上限是 **15**。
  `"interrupt_config"` 和 `"wake_word_config"` 都是 16 字符 → `nvs_open` 永远失败，句柄留 0。
- **Settings 写方法无判 0**：Get* 系列有 `nvs_handle_==0` 保护返回默认值，但 Set* 系列没有 →
  `ESP_ERROR_CHECK(nvs_set_i32(0,…))` 直接 abort。

修复：5 处命名空间改名（`interrupt_cfg`/`wake_word_cfg`）+ `settings.cc` 全部写方法加判 0 保护。
崩溃现场与定位手法详见 `topics/firmware-crash-cookbook.md` 现场 ③。

### 4. 同批修复：开机壁纸 + 背景壁纸都使用用户下发的图
- **背景**（主界面）：原有 `ApplyBackground()` 三级回落已含 `user_wallpaper_` 优先。
- **开机画面**：`SplashInfo::background` 新增——`SetupUI`/`ShowBootSplash` 传 `user_wallpaper_`，
  splash 底图从编译期品牌底纹改为**壁纸优先**（回落逻辑与背景一致：壁纸 > 品牌底纹）。
- **开机期间壁纸到达**：`ApplyBackground()` 成功尾部调 `yh_skin::UpdateSplashBackground(user_wallpaper_)`
  ——splash 亮着时壁纸下发成功，开机画面底图立刻换掉，不用等下次开机。
- **重启后的开机画面**：NVS 只存壁纸元数据（url/md5），图像需从服务器重拉。
  本次运行的时序是「splash 先亮（此时无图）→ 服务器下发壁纸 → 拉取应用成功 → UpdateSplashBackground
  立刻换图」。**冷启动后壁纸下载完成前，开机画面仍是品牌底纹**，下载完成后（若 splash 还在）即刻切换；
  若关心「上电第一帧就是壁纸」，需要把壁纸缓存进 LittleFS/嵌入式 assets，属后续增强。

### 5. ★ 决定性根因（2026-10-17 23:13 用户反馈"原厂固件能实时打断"后查明）：Server AEC 被关闭
用户指出：**原厂固件在同一块硬件上可以实时打断**。逐行比对上游源码 + 生产服务器取证后确认：

- **原厂的实时打断走的是服务端 AEC**，不是设备侧：
  - 上游 `application.cc` Speaking 态只判 `listening_mode_ != kListeningModeRealtime`（没有 `IsDeviceAecEffective` 门禁）
  - `aec_mode_ != kAecOff → GetDefaultListeningMode() = Realtime` → Speaking 期间麦克风持续推流
  - 服务端 `receiveAudioHandle.py`：`if conn.client_aec and have_voice and conn.client_is_speaking and listen_mode != "manual": handleAbortMessage(conn)` —— **服务器 VAD 判人声 → 直接打断 TTS**
  - 回声消除在服务端做（`connection.py _apply_aec`：互相关延迟估计 + Wiener 滤波），设备只需在播报包带时间戳、上行麦克风包对齐时间戳
- **服务端能力齐全且从未被使用**：`grep '客户端启用了服务端AEC' app.log` 返回 **0 条**——从来没有设备声明过 `features.aec`
- **我们的固件把这条路关死在两处**：
  1. `config.json`：`CONFIG_USE_SERVER_AEC=n` → 握手不发 `features.aec` → 服务端 `client_aec=False`
  2. `application.cc:1441` 自定义门禁 `|| !IsDeviceAecEffective()` → 即使开了 Server AEC，Speaking 态也会关推流（服务端收不到音频，无从打断）

**修复（3 处）**：
1. `config.json`：`CONFIG_USE_SERVER_AEC=y`（握手声明 aec → 服务端启用 AEC 打断）
2. `application.cc` Speaking 态门禁重写为三分支：设备侧 AEC 生效（VAD+推流全开）/ **服务端 AEC（保持推流、关本地 VAD 防自打断、唤醒词检测保持）** / 无 AEC（全关）
3. `application.cc` VAD 消费点：`aec_mode_ != kDeviceSide` 时本地不做打断决策（打断交给服务器），避免单工板被自己的播报声误打断

**注意（重要预期）**：管理端「实时打断阈值」滑条是**设备本地 VAD 参数**（人声确认窗 ms）。
Server AEC 模式下打断灵敏度由**服务端 Silero VAD** 决定（`config.yaml` `VAD.SileroVAD.threshold: 0.5`），
该滑条对播报打断的即时灵敏度不再起作用（仍影响 Listening 态本地上报）。要调播报打断灵敏度需改服务端 VAD threshold。

## 服务端链路已实证全通（无需再查）

用户 5 次保存的完整轨迹（Java manager-api.log）：
```
21:27:57  interrupt_threshold=0  推送成功
21:50:39  0  推送成功
21:51:28  0  推送成功      （同轮保存唤醒词「鬼鬼」→ gui gui，汉字拼音链路正常）
21:52:28  3  推送成功
21:52:45  1  推送成功
```
Python 侧 WS 下发记录（app.log）：`{"interrupt_threshold":1}` 于 21:52:53/21:52:59 **真实到达设备**。
设备在线（21:50 后 8 次连接）。

## 烧录步骤（用户手动执行）

```powershell
# CMD / PowerShell（不要 Git Bash），先切到版型中心
cd G:\demo\21_xiaozhi\hardware\sets

# 1) 编译（--board 直指定版型）
#    4 个文件久改未编，稳妥起见删 build 全量重编：
Remove-Item -Recurse -Force .\yuhe-esp32\build
#    用 IDF venv python 启动（环境：IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf、
#    IDF_TOOLS_PATH=D:\INSTALL\esp、IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv、
#    ESP_IDF_VERSION=6.1；参考 C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1）
python .\build.py --board yh-154tft-wifi

# 2) 烧录（零编译、三道闸；COM 口自动探测；baud 230400）
python .\flash.py --board yh-154tft-wifi
```

## 烧录后验收（按序执行）

| # | 步骤 | 期望 |
|---|---|---|
| A | 烧前自检：编译产物字符串扫描 | bin 内 FOUND `interrupt_threshold` 与 `云端实时打断阈值已更新` |
| B | 烧后串口：管理端改一次阈值 | 串口出现 `云端实时打断阈值已更新: N`（board.cc:435） |
| C | 重启设备（阈值已保存过） | 串口出现 `Restored interrupt threshold N from NVS`（afe:75） |
| D | 验证 NVS 持久化：再重启一次 | 同样出现 C 行，值不变 |
| E | **★ Server AEC 实时打断测试（本轮核心验收）**：TTS 播报中直接说话（如「停」） | 播报被打断、设备立即进入聆听。服务端日志出现 `客户端启用了服务端AEC`（首次声明）+ `Abort message received`（每次打断）。注意打断灵敏度由服务端 VAD（threshold 0.5）决定，管理端阈值滑条对此场景不起作用 |
| F | 回归：唤醒词功能 | 汉字唤醒词正常（wake_word_threshold 同链路已验证工作）；播报中喊唤醒词仍可打断（保底路径保留） |
| G | 回归：音量/亮度下发 | device_config 同帧其他键正常 |
| H | **NVS 崩溃回归（关键）**：触发唤醒词/语音对话/LLM 播报 | 设备**不再重启**；串口无 `0x1107`；若曾触发过配置下发，可看到 NVS 写入正常无报错 |
| I | **壁纸验收**：管理端下发壁纸 | 串口 `wallpaper applied`（或既有成功日志）；主界面背景立即变为用户图 |
| J | **壁纸×开机画面**：壁纸应用成功后（不重启）触发 ShowBootSplash 场景，或重启后等待壁纸重拉完成 | 开机画面底图 = 用户壁纸（60% 透明度，不遮挡品牌字/状态文案）；无壁纸时回落品牌底纹 |
| K | **壁纸清除回归**：管理端清除壁纸 | 背景与 splash（若可见）都回落品牌底纹，无悬空指针崩溃 |
| L | **自打断回归（Server AEC 生效后必测）**：正常音量播放 TTS，保持安静听完整段 | 播报**不被自己打断**（服务端 `_apply_aec` 回声消除生效）。若频繁自己打断自己，把 `config.yaml` 的 `VAD.SileroVAD.threshold` 从 0.5 提到 0.6~0.7，或检查时间戳对齐 |

### A 步自检命令（编译后立刻跑）
```bash
cd /g/demo/21_xiaozhi/hardware/sets/yuhe-esp32
"D:/INSTALL/python313/python.exe" -c "
data = open('build/yuhe.bin','rb').read()
for pat in [b'interrupt_threshold', '云端实时打断阈值已更新'.encode()]:
    i = data.find(pat)
    print(pat[:30], 'FOUND @0x%x' % i if i >= 0 else 'NOT FOUND')
"
```
两个都 FOUND 才继续烧录。

## 重要预期管理

- **实时打断（核心变化）**：烧录后 `CONFIG_USE_SERVER_AEC=y` 生效，播报中直接说话即可打断（服务端判断）。
  上一版文档写的「该版型无法语音打断」结论**已被本轮修复推翻**——当时只分析了设备侧 AEC 路径，漏了服务端 AEC 路径。
- **阈值滑条语义变化**：Server AEC 模式下，管理端「实时打断阈值」不再控制播报打断灵敏度（那是服务端 Silero VAD 的 `threshold: 0.5`）。
  滑条仍生效于 Listening 态（设备本地 VAD 上报去抖）。
- **自打断风险**：服务端 AEC 用软件回声消除（互相关 + Wiener），效果弱于硬件回采。L 步回归必测；
  若有自打断，优先调服务端 threshold（0.5→0.65），不要回退固件。
- **首个包的对齐**：设备播报包时间戳 → 服务端缓存对齐（`aec_audio_cache`）。若服务器时钟与设备时间戳
  有大偏差，`_apply_aec` 会退化成"不消除"（cache 空/时间对不上），此时 VAD 直接看原始麦克风——
  初期若有偶发误打断，属对齐窗口未热身，观察几轮再调参。

## 相关文件
- 固件解析：`hardware/sets/yuhe-esp32/main/boards/common/board.cc:423-437`
- 阈值应用：`hardware/sets/yuhe-esp32/main/audio/engines/afe_audio_engine.cc:310-321`
- 打断消费：`hardware/sets/yuhe-esp32/main/application.cc:379-411`（上升沿 + 800ms 保护窗）
- AEC 门禁：`hardware/sets/yuhe-esp32/main/application.cc:1436-1461`（三分支）+ `audio_service.cc:852`
- Server AEC 修复：`application.cc` Speaking 态三分支 + VAD 消费点（`aec_mode_ != kDeviceSide` 不做本地打断）+ `hardware/sets/boards/yh-154tft-wifi/config.json`（`CONFIG_USE_SERVER_AEC=y`）
- 服务端参照：`receiveAudioHandle.py`（client_aec 打断）、`connection.py`（_apply_aec）、`helloHandle.py`（features.aec）、`websocket_protocol.cc:251`（握手 features）、`abortHandle.py`（tts stop 下行）
- NVS 修复：`main/settings.cc`（写方法判 0）+ `board.cc:400/414/432`、`afe_audio_engine.cc:72`、`custom_wake_word.cc:139`（命名空间改名）
- 壁纸双源：`main/display/yh_skin/yh_skin_boot.h/.cc`（SplashInfo::background、UpdateSplashBackground）+ `yh_skin_display.cc`（SetupUI/ShowBootSplash/ApplyBackground 调用点）+ `main/display/display.h`（GetWallpaper/ClearWallpaper 接口）
- 语法检查已过：6 个 .cc 全 OK（yh_syntax_check）
- 审计提示：sets_diff_audit 3 项 DIFF（board/custom_wake_word/settings）是壁纸模块+唤醒词清洗等既有功能演进（A 侧=上游原生树，B 侧=sets 真源），非本轮引入，不阻塞
