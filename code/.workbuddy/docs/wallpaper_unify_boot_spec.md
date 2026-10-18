# 开机壁纸与服务器壁纸统一 · 改造方案

> 需求：连接 WiFi 前屏幕上的壁纸，与连接 WiFi 后（服务器下发）的壁纸统一成同一张图。
> 本文只做只读分析 + 改造方案，不含任何已落地的代码改动。
> 仓路径：`G:/demo/21_xiaozhi/hardware/sets/yuhe-esp32/`（下称 `FW`）

---

## 0. 一句话结论

**问题的本质不是"画错了图"，而是"服务器那张图在开机那一刻根本不在设备上"。**

壁纸目前只存在于 PSRAM（`WallpaperManager::Impl::buffer`），掉电即失；NVS 里只存了
`version / url / md5`，真正把图拉回来要等 WiFi 连上（`HandleNetworkConnectedEvent` →
`RestoreFromNvsAsync`）。所以开机阶段画面上只能看到编译进固件的品牌底纹 `yh_skin_bg`。

**唯一干净的解法：把服务器下发的 115,200 字节 RGB565 原图持久化到独立 flash 分区，
开机在 `SetupUI()` 之前读回 PSRAM。** 其余（透明度、配网遮罩）是配套的观感对齐。

---

## 1. 现状：三个渲染点 + 一条时序

| # | 阶段 | 画的是什么 | 代码位置 |
|---|------|-----------|---------|
| ① | 上电 ~ WiFi 未连 | **`yh_skin_bg`**（编译期品牌底纹，紫渐变 + `good.jpg`），60% 不透明叠在渐变上 | `main/display/yh_skin/yh_skin_boot.cc:154-169` |
| ② | WiFi 配网中 | **纯黑全屏遮罩**盖住一切（连上面那张都看不见） | `main/display/yh_skin/yh_skin_cards.cc:112` |
| ③ | WiFi 连上、进入待机 | **服务器下发的用户壁纸**，100% 不透明铺满 | `main/display/yh_skin/yh_skin_display.cc:785-833` |

关键时序（`main/application.cc`）：

```
163  Application::Initialize()
168    auto display = board.GetDisplay();
169    display->SetupUI();                 // ← 此处 BuildSplash()，第一帧上屏
171    display->SetChatMessage(...)        // UA 串（已被皮肤层吞掉）
...
470  Application::HandleNetworkConnectedEvent()
473    WallpaperManager::RestoreFromNvsAsync();   // ← 这时才开始下载壁纸
```

`SetupUI()` 内部 `ShowBootSplash()`（`yh_skin_display.cc:521-535`）取 `info.background = user_wallpaper_`；
此时 `user_wallpaper_` 恒为 `nullptr`（PSRAM 刚上电、`SetWallpaper` 从未被调过），
所以 `BuildSplash` 走到 `bg_src = &yh_skin_bg`（`yh_skin_boot.cc:157-159`）—— **这就是"WiFi 前那张"**。

另外注意 `SetWallpaper()` 有条硬闸（`yh_skin_display.cc:852-857`）：
`setup_ui_called_ == false` 时**直接拒绝**，日志 `SetWallpaper called before SetupUI, rejected`。
所以"开机前先塞图"不能靠提前调 `SetWallpaper`，必须走"预加载 + 建完 UI 再绑"。

---

## 2. 为什么改代码顺序治不了

三条错路，都已排除：

| 思路 | 为什么不行 |
|------|-----------|
| 把 `RestoreFromNvsAsync()` 提前到 `SetupUI()` 之前 | 它只是把 NVS 里的 **url** 变成 HTTP 请求，没有 WiFi 就没有图；且它是异步的，`SetupUI()` 不会等 |
| 开机时直接把 splash 底图改成待机那张 | 待机那张此刻不存在。`user_wallpaper_` 是空指针，`ApplyBackground()` 会回落 `yh_skin_bg`（`yh_skin_display.cc:789-798`） |
| 开机先不画图，等壁纸到了再建 splash | WiFi 握手 + 激活动辄 3-15 秒，这段时间黑屏，比现状更差 |

**所以必须让"图"本身活过掉电。** 这是唯一解。

---

## 3. 存哪儿：分区空间实测

`partitions/v2/16m.csv`（四个 yuhe 版型全部引用，`config.json:19-21`）：

```
nvs       0x009000  0x4000     (16 KB)
otadata   0x00D000  0x2000
phy_init  0x00F000  0x1000
ota_0     0x020000  0x3F0000   (4.03 MB)
ota_1     —         0x3F0000
assets    0x800000  8M         (8 MB)
```

16 MB **已用满，尾部余量为 0**。而 assets 实际内容：

```
FW/build/generated_assets.bin = 4,054,873 B ≈ 3.87 MB
```

**8 MB 分区里只用了 3.87 MB，空着 ~4.1 MB。**

### 方案对比

| 方案 | 做法 | 结论 |
|------|------|------|
| **A（推荐）** | assets `8M → 7M`，尾部新增 `wallpaper` 分区 `1M @0xF00000` | ✅ 起始地址不变 ⇒ **assets 内容不用重烧**；独立分区可自由擦写；1 MB 放 115 KB 绰绰有余 |
| B | 不改分区表，借用 assets 尾部 0xF00000 附近写 raw | ❌ 排除。assets 被 `esp_partition_mmap` 只读映射（`main/assets.cc:195`），写同分区有 cache 一致性风险；且 assets OTA 更新会整段重写，壁纸必被覆盖 |
| C | 把服务器壁纸预先编译进固件 | ❌ 违背需求。服务端换图后固件里的还是旧的，且每次换图要重编重烧 |
| D | 把图塞进 NVS | ❌ 物理不可能。NVS 分区 16 KB，图 115,200 B |
| E | 存 OTA 分区剩余空间 | ❌ app 写 OTA 时会覆盖 |

### 方案 A 的分区表改法

`FW/partitions/v2/16m.csv`，只改**两行**：

```csv
assets,    data, spiffs,  0x800000,  7M
wallpaper, data, spiffs,  0xF00000,  1M
```

校验：`0x800000 + 7M = 0xF00000`；`0xF00000 + 1M = 0x1000000 = 16 MB` ✅ 首尾对齐、无空洞。

> `subtype` 用 `spiffs` 只是占位（ESP-IDF 对 data 分区 subtype 检查宽松）。
> 运行期用 `esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "wallpaper")`
> 按 **label** 查找，不依赖 subtype。

---

## 4. 数据布局（1 MB 分区内的双槽）

单槽擦写期间掉电会丢图（回退品牌底纹，可恢复但不优雅）。用双槽轮换，掉电永远至少有一份完整图。

```
0x000000  slot A: [header 64B][payload 115,200B]     共 128 KB
0x040000  slot B: [header 64B][payload 115,200B]     共 128 KB
0x080000 .. 0x100000  保留（可扩到 8 槽）
```

header 结构（64 B，小端）：

```c
struct WallpaperSlotHeader {
    uint32_t magic;         // 'YHWP' = 0x50574859
    uint32_t format_ver;    // 1
    uint32_t payload_bytes; // 115200
    uint32_t payload_crc32; // 对 payload 算 CRC32
    uint32_t seq;           // 单调递增，取两个有效槽里 seq 大的
    char     version[32];   // 服务端 version（"3-<md5>"），空串=无
    uint8_t  reserved[12];  // 补到 64
};
```

读取规则：两槽都读 header → 校验 `magic / format_ver / payload_bytes / payload_crc32` →
取通过校验且 `seq` 最大的一槽。**任一环节不符就当没有壁纸**，回落品牌底纹，绝不崩。

写入规则：找 `seq` 较小的那一槽（或空槽）→ `esp_partition_erase_range` 擦 128 KB →
写 header → 写 payload → 回读 header 校验 → 更新内存里 `seq`。

预计耗时：擦 128 KB ≈ 150-300 ms，写 115 KB ≈ 100-200 ms。**在 `WallpaperManager` 的
worker 任务里做**（`kTaskStackBytes` 12 KB，`kTaskPriority` 4，见 `wallpaper_manager.cc:43-44`），
不占音频/协议任务。

---

## 5. 改动清单（供执行 agent）

### M1 · 分区表

- `FW/partitions/v2/16m.csv`：按 §3 改两行。
- 同步检查：`FW/scripts/build.py` 是否有 assets 大小硬编码校验（当前无，只调 `build_default_assets.py`）；
  建议在 `build_default_assets.py` 产出后加断言 `size < 7M`，超标直接 fail，避免将来 assets 长大到撞壁纸分区。
- 注意：`v2/16m.csv` 被**四个 yuhe 版型 + build.py 的 s3 默认值**引用（`scripts/tests/test_build.py:268-279`），
  改它等于全平台生效。`v2/16m_c3.csv` 等其它变体不动。

### M2 · 新增持久化模块

新文件 `FW/main/wallpaper/wallpaper_store.h` + `wallpaper_store.cc`（纯 C++，不依赖 LVGL）：

```cpp
namespace wallpaper_store {
bool  Available();                                    // 分区存在？（旧分区表设备返回 false）
bool  Load(std::string& version, uint8_t** out_buf);  // 成功则 malloc PSRAM 并填图；调用方负责 free
bool  Save(const uint8_t* data, size_t len, const std::string& version);
void  Erase();                                        // 清空（HandleClear / 无壁纸时）
}
```

实现要点：
- 分区查找失败 → `Available()` 返回 false，**只打一次** `ESP_LOGW(TAG, "wallpaper partition not found (old partition table?)")`，之后所有调用静默返回 false。
- 所有 `esp_partition_read/write/erase_range` 的返回值都要判，非 `ESP_OK` 直接 fail。
- `Load` 分配用 `heap_caps_malloc(115200, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)`，与
  `wallpaper_manager.cc:266` 同一标志，失败返回 false（不 assert）。
- CRC32 用 `esp_rom_crc32_le(0, data, len)`（`<esp_rom_crc.h>`）。

### M3 · 接线：下载成功后落盘

`FW/main/wallpaper/wallpaper_manager.cc`：

1. `Impl` 加成员 `uint32_t flash_seq = 0;`（缓存当前最大 seq，避免每次读两槽）
2. `Impl::ApplyToDisplay()` 成功分支（**line 464-470 那个 `dsc_valid = true` 块之后、`ESP_LOGI` 之前**）
   追加：
   ```cpp
   wallpaper_store::Save(new_buffer, kImageBytes, request.version);
   ```
   > 位置必须在 `SetWallpaper` 成功之后：显示层没接的图不该被记成"开机壁纸"。
   > `Save` 失败只打 WARN，不影响本次应用结果（屏幕已经换好了，下次开机回退品牌底纹而已）。
3. `Impl::ProcessClear()`（释放 buffer 那段，`wallpaper_manager.cc:546` 附近）追加
   `wallpaper_store::Erase();`
4. `HandleClear` 的幂等/失败路径不用改。

### M4 · 开机预加载（三步）

**M4a** 新增公开接口 `WallpaperManager::PreloadFromFlash()`：

```cpp
// 开机同步调用（SetupUI 之前）。命中则把图读进 PSRAM、填好 dsc/applied_version，
// 但【不】调 display->SetWallpaper —— 那时 UI 还没建，会被显示层拒绝。
void WallpaperManager::PreloadFromFlash();
```

实现：
```cpp
std::string version;
uint8_t* buf = nullptr;
if (!wallpaper_store::Load(version, &buf)) return;

lv_img_dsc_t d;
d.header.magic  = LV_IMAGE_HEADER_MAGIC;
d.header.cf     = LV_COLOR_FORMAT_RGB565;
d.header.w      = 240;  d.header.h = 240;  d.header.stride = 480;
d.data_size     = 115200;
d.data          = buf;

std::lock_guard<std::mutex> lock(impl_->mutex);
impl_->buffer        = buf;
impl_->dsc           = d;
impl_->dsc_valid     = true;
impl_->applied_version = version;
impl_->preloaded     = true;     // 新增标志：已加载但未绑定显示层
ESP_LOGI(TAG, "wallpaper: preload from flash version=%s", version.c_str());
```

**M4b** 新增 `WallpaperManager::PeekImage()`，返回 `const lv_img_dsc_t*`（未预加载则 `nullptr`）。

**M4c** 新增 `WallpaperManager::BindPreloaded()`：
UI 建好后调用，内部 `display->SetWallpaper(&impl_->dsc)`，成功则清 `preloaded`，
并把 `dsc_valid` 保持 true。失败只打 WARN（屏幕继续显示品牌底纹，不影响开机）。

**M4d** `FW/main/application.cc` 的 `Initialize()` 插两行：

```cpp
    auto display = board.GetDisplay();
    WallpaperManager::GetInstance().PreloadFromFlash();   // ← 新增，必须在 SetupUI 之前
    display->SetupUI();
    display->SetChatMessage("system", SystemInfo::GetUserAgent().c_str());
    WallpaperManager::GetInstance().BindPreloaded();      // ← 新增，紧跟 SetupUI
```

> 为什么 `PreloadFromFlash` 必须在 `SetupUI()` 之前：溅射画面要在**同一个函数调用栈里**
> 拿到图（见 M5），否则第一帧仍是品牌底纹，之后才被换掉（会闪一下）。
> 读 115 KB flash 约 20-40 ms，对开机时间无感。

### M5 · 让 splash 第一帧就用上（零闪变）

`FW/main/display/yh_skin/yh_skin_display.cc`：

1. 顶部加 `#include "wallpaper_manager.h"`（**只在 .cc**，头文件不加，避免 display ↔ wallpaper 循环依赖；
   `wallpaper_manager.h` 本身不 include `display.h`，`display.h` 也不 include 它，安全）
2. `ShowBootSplash()`（**line 531-533**）把

   ```cpp
   info.background = user_wallpaper_;
   ```

   改为

   ```cpp
   info.background = user_wallpaper_;
   if (info.background == nullptr) {
       info.background = WallpaperManager::GetInstance().PeekImage();
   }
   ```

   `BuildSplash` 内部 `user_wallpaper = (bg_src && bg_src->data)`（`yh_skin_boot.cc:156`）会自动
   走"用户壁纸"分支：按长边等比放大铺满，不再回落 `yh_skin_bg`。

改完后的顺序：`PreloadFromFlash` 填好 PSRAM → `SetupUI` → `BuildSplash` 取到图 →
**屏亮第一帧就是服务器那张** → `BindPreloaded` 绑定主界面背景 → 待机时 `ApplyBackground`
用同一指针 → 全程同一张图。

### M6 · 观感对齐（不做会"同一张图看着还是不一样"）

现状：splash 上的底图是 `LV_OPA_60`（`yh_skin_boot.cc:166`），叠在紫渐变 `#2A1633→#120B18` 上；
待机背景是 100% 不透明。**同一张图在两处的观感差异明显偏紫偏暗。**

两选一（建议 B）：

- **A** 直接把 `LV_OPA_60` 改成 `LV_OPA_COVER`。最简单，但品牌名/状态文案可能被亮色壁纸压住看不清。
- **B（建议）** 底图改 `LV_OPA_COVER`，另建一层全屏半透明遮罩（`#120B18`，`LV_OPA_30~40`）
  压在底图之上、文字之下，保证文字对比度。遮罩层要在 `g_root` 里紧跟 `g_bg` 创建、
  在 `brand` 之前，并在 `UpdateSplashBackground` 里不参与换图。

### M7 · 配网黑屏（可选，看需求边界）

如果"连接 WiFi 前"指的是**配网中的界面**（出现二维码/热点提示那屏），那它是纯黑遮罩，
壁纸被完全盖住（`yh_skin_cards.cc:112` 的 `lv_obj_set_style_bg_color(g_root, lv_color_black(), 0)`）。
此时改 M1-M6 都看不到效果，需要：

- 把 `g_root` 的 `bg_color` 改成 `lv_color_black()` + `bg_opa = LV_OPA_60`，让底下的 splash
  壁纸透出来；卡片本体 `kCardBg` 保持不透明以保证可读性。

**这一条是否要做，需要先确认用户说的"WiFi 前"到底是开机 branding 画面还是配网界面。**

### M8 · 服务端

**无需改动。** 壁纸原图已由服务端保存（`yh/manager-api/.../wallpaper/`），
NVS 里的 `version/url/md5` 三个键语义不变；`RestoreFromNvsAsync` 保留原样，
作为"flash 槽损坏时的兜底重拉"路径，与新增的 flash 预加载不冲突
（`restore_version` 守卫在 `wallpaper_manager.cc:693-704`，已防重连风暴）。

---

## 6. 验证判据

### 串口

| 日志 | 含义 |
|------|------|
| `wallpaper: preload from flash version=3-xxxx` | ✅ 开机从 flash 读到图 |
| `wallpaper: preload skipped (no partition)` | 分区表没烧进去 / 老分区表 |
| `wallpaper: preload skipped (slot invalid)` | 槽 CRC/magic 不符（首次开机、或上次写一半掉电） |
| `wallpaper: save to flash version=3-xxxx bytes=115200` | ✅ 下发成功后落盘 |
| `wallpaper: save to flash failed` | 分区擦写失败（看 `esp_err_to_name`） |
| `SetWallpaper called before SetupUI, rejected` | 说明 `BindPreloaded` 被放到了 `SetupUI` 之前，顺序错了 |

### 视觉

1. 设备已下发过壁纸 → **拔电重启** → 屏幕亮起第一帧就是那张图（不是紫渐变品牌画面）
2. 保持断网（不配 WiFi）重启 → 依然是那张图（证明不依赖网络）
3. 服务端换一张图 → 待机看新图 → 拔电重启 → 第一帧是新图（证明槽已更新）
4. 服务端清空壁纸 → 重启 → 回到品牌底纹（证明 `Erase` 生效）

### 烧录

分区表变了，**首次必须整片重烧**（OTA 不会更新分区表）：

```bash
# 在 IDF shell（CMD/PS，不要在 Git Bash 里跑 idf.py）
idf.py -B build -D SDKCONFIG=build/sdkconfig build
idf.py -B build -p COM18 flash
```

或分开烧：`partition-table.bin` `ota_data_initial.bin` `yuhe.bin` `generated_assets.bin`（assets 地址未变，可只烧分区表 + app）。

> 记忆里的红线：assets 必须全量烧；baud 230400；反相复位线的板子不能直接跑 `idf.py flash`
> （走 `tools/flash.py`）。本次只加分区表 + app，assets 不用动。

---

## 7. 风险

| 风险 | 影响 | 处置 |
|------|------|------|
| 分区表变更，OTA 不会更新 | 老设备升级后没有 `wallpaper` 分区 | M2 的 `Available()` 守卫：找不到分区就静默降级，功能退回现状（不崩、不报错）。要享受新功能必须整片烧一次 |
| 写槽途中掉电 | 该槽损坏 | 双槽 + `seq` 轮换 + CRC 校验：另一槽仍可用；两槽都坏则回落品牌底纹 |
| assets 将来长过 7 MB | 撞进 `wallpaper` 分区 | `build_default_assets.py` 加大小断言（当前 3.87 MB，余量 3.1 MB） |
| flash 擦写寿命 | 每次换壁纸写 115 KB，按每天 10 次算 ≈ 0.4 GB/年，NOR flash 寿命 10 万次擦除量级 | 可忽略 |
| 改了共享层却没生效 | `yh_skin_display.cc` 现在**只有一份**（`hardware/sets/yuhe-esp32/main/display/yh_skin/`），`boards/<board>/` 下**没有** `main/display/yh_skin/` 副本（已实测确认） | 不需要同步两份；但改完必须 `tools/sets_diff_audit.py` PASS |
| C++ 依赖倒挂 | `yh_skin_display.cc` 新增 include `wallpaper_manager.h` | 只在 .cc include，头文件不加；两个 .h 互不引用，无循环 |

---

## 8. 回滚

1. `git checkout -- partitions/v2/16m.csv`
2. 删 `main/wallpaper/wallpaper_store.{h,cc}`，从 `CMakeLists.txt` 移除
3. 还原 `wallpaper_manager.cc` 的三处接线、`application.cc` 的两行、`yh_skin_display.cc` 的两处
4. 整片重烧（分区表回到 8M assets）

---

## 9. 给执行 agent 的任务分解

按依赖顺序，B/C/D 之间有共享文件，建议 A 独立、B→C 串行、D 可与 B 并行（不同文件）。

| 任务 | 范围 | 文件 | 依赖 |
|------|------|------|------|
| **A** 分区表 + 构建守卫 | §3 / M1 | `partitions/v2/16m.csv`、`scripts/build_default_assets.py` | 无 |
| **B** 持久化模块 | §4 / M2 | 新增 `main/wallpaper/wallpaper_store.{h,cc}`、`main/CMakeLists.txt` | A（分区 label 定稿） |
| **C** 管理器接线 | M3 / M4a-c | `main/wallpaper/wallpaper_manager.{h,cc}`、`main/application.cc` | B |
| **D** 皮肤层零闪变 + 观感 | M5 / M6 | `main/display/yh_skin/yh_skin_display.cc`、`yh_skin_boot.cc` | C（接口名定稿） |
| **E** 配网遮罩（待确认） | M7 | `main/display/yh_skin/yh_skin_cards.cc` | 需先答复"WiFi 前"指哪一屏 |

**验收统一在 `tools/yh_syntax_check.py` + `tools/sets_diff_audit.py` 之后，由人工烧录验证（§6）。**

---

## 10. 需要先确认的两个问题

1. **"连接 WiFi 前的壁纸"具体指哪一屏？**
   - (a) 开机品牌画面（紫渐变 + `good.jpg` + "小柚"字 + 呼吸点）→ 走 M1-M6，方案完整。
   - (b) 配网界面（热点名/二维码提示，当前是纯黑遮罩）→ **M1-M6 改完也看不到**，必须加 M7。
   - (c) 两屏都要 → M1-M7 全做。

2. **是否接受"首次整片重烧一次"？**
   分区表变更无法通过 OTA 下发。若不接受，就只能放弃 flash 持久化，功能无解
   （备选只有"C 把图编译进固件"，但服务端换图后必须重编）。
