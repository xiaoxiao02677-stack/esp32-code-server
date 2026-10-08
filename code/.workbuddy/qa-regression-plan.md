# Kawaii 控制台 · QA 回归执行清单（v1，待 team-lead GO 后执行）

生成：2026-10-06 · e-qa-regress · 预算：总时长 ≤ 5 min（超项降级为静态判据并标注）

## 0. 环境与基线事实（准备期已验证）

| 项 | 事实 | 来源 |
|---|---|---|
| Python 单测入口 | `xiaozhi-server` 内 `python -m pytest tests`（pytest 9.1.1，testpaths=tests，报告基线 29 项） | pyproject.toml `[tool.pytest.ini_options]` |
| 运行解释器 | `C:\Users\34808\.workbuddy\binaries\python\versions\3.13.12\python`（workbuddy python） | `which python` |
| **坑 1** | 裸跑 pytest 时用户站点 `C:\Users\34808\AppData\Roaming\Python\Python313\site-packages\dash` 混入 → `No module named 'typing_extensions'`。解法：跑前设 `PYTHONNOUSERSITE=1` | 实测 |
| **坑 2** | `data/.config.yaml` 含 manager-api 块（url+secret 2d7b6bde…，即 P0-1 待轮换的生产 secret）→ conftest L91-116 判「全模块部署」`sys.exit(2)`，收集都进不去。解法：跑前临时挪走该文件（mock 模式回落 config.yaml，缺 key 仅软告警可跑），跑完恢复；若 P0-1 已处理该文件则跳过挪动 | 实测 + conftest 源码 |
| 前端快检 | `node scripts/qa/tag-balance-check.js <file.vue>` 逐文件跑，实测 KawaiiLayout.vue PASS | 实测 |
| 前端契约测试 | `node --test tests/*Contract.test.mjs`（node 原生测试，秒级；date/format 等是 vitest 用例，不走 node --test） | 实测 8/8 |
| 前端单测 | `node_modules/.bin/vitest run`（node_modules 已装好，无需 npm install） | 实测存在 |
| node | v22.22.2，可用 | 实测 |
| 契约测试 | `tests/test_device_config_sync_contract.py` **当前不存在**（e-pi 在写）→ 清单按「存在则自动被 `pytest tests` 收集」处理 | ls 确认 |
| 部分 P1 已落盘 | `manager-api` 已有 `202610070010.sql`（JSON_MERGE_PATCH，P1-6 部分交付）；`theme-green` 当前 src/ 内 0 命中（P1-7 未完成，按「缺失记遗留」处理） | grep 实测 |

---

## 步骤 1 · Python 全量单测（上限 90s + 15s 前置）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server
# 1a. 前置（~5s）：若 data/.config.yaml 仍含 manager-api 块且 P0-1 未处理：
grep -q "manager-api" data/.config.yaml && cp data/.config.yaml data/.config.yaml.qa-bak
# 1b. 执行（timeout 90）：
PYTHONNOUSERSITE=1 timeout 90 python -m pytest tests -q
# 1c. 恢复：
[ -f data/.config.yaml.qa-bak ] && mv -f data/.config.yaml.qa-bak data/.config.yaml
```
- 若 1b 超时/被 90s 截断 → 降级：仅记 `--collect-only -q` 用例数 + 失败项清单，标注「超时降级」。
- **通过判据**：`N passed` 且 N ≥ 29（新增契约测试存在时会 >29，正常）；0 failed/error。有失败 → 记录 文件:行 + 断言输出。
- 注意：conftest 软告警（缺 LLM/TTS/Memory configJson）属预期，不算失败。

## 步骤 2 · Vue 标签配平快检（~15s）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/manager-web
for f in src/components/layout/KawaiiLayout.vue src/components/layout/KawaiiSidebar.vue \
         src/components/layout/KawaiiTopbar.vue src/components/layout/SidebarMenu.vue \
         src/components/layout/SidebarSearch.vue src/components/layout/KawaiiMobileDrawer.vue \
         src/components/memory/MemoryEngineParams.vue; do
  [ -f "$f" ] && node scripts/qa/tag-balance-check.js "$f"
done
```
- KawaiiMobileDrawer.vue 若尚未交付则跳过（不算失败，标注）。
- **判据**：每个存在文件 `PASS … tags balanced`，exit 0。

## 步骤 3 · 残留 grep 检查（~10s）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/manager-web
# 3a. HeaderBar 残留（src/views 内应为 0）
grep -rln "HeaderBar" src/views --include=*.vue
# 3b. 旧口径 calc(100vh 硬编码（src/views + layout 组件应为 0）
grep -rn "calc(100vh" src/views src/components/layout
# 3c. SEARCH_HISTORY_KEY undefined 隐性 bug（应为 0 命中）
grep -rn "SEARCH_HISTORY_KEY.*undefined\|undefined.*SEARCH_HISTORY_KEY" src/
# 3d. 正向确认修复：SidebarSearch.vue 内应有 'agentSearchHistory'
grep -n "agentSearchHistory" src/components/layout/SidebarSearch.vue
```
- **判据**：3a/3b/3c 命中数为 0；3d ≥1 命中。任一不满足 → 记录 文件:行。

## 步骤 4 · 新 P1 功能抽查（静态判据，~20s）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/manager-web
# 4a. jelly 动效 token 存在
grep -cn "kawaii" src/styles/kawaii/tokens.scss
grep -in "spring\|bounce\|squash\|ease\|motion\|cubic-bezier" src/styles/kawaii/tokens.scss | head -5
grep -n "prefers-reduced-motion" src/styles/kawaii/*.scss
# 4b. 双主题：theme-green 可切换
grep -rln "theme-green" src/ | head
# 4c. 移动端断点
grep -rn "@media" src/components/layout src/styles/kawaii | head
# 4d. 新路由可达（静态）：router 中 children 数量与 layout 引用
grep -c "path:" src/router/index.js
grep -n "KawaiiLayout" src/router/index.js
# 4e. MQTT 网关透传手册（P1-5）存在性
ls ../../.workbuddy | grep -i "mqtt\|gateway" 2>/dev/null || find .. -maxdepth 3 -iname "*mqtt*手册*" -o -iname "*gateway*.md" 2>/dev/null | head
# 4f. 设备配置管理 UI（P1-4）路由/页面存在
grep -rln "device-config\|DeviceConfig" src/views src/router 2>/dev/null | head
```
- **判据**：4a tokens ≥60 且存在动效类 token + reduced-motion 降级声明；4b ≥1 命中；4c 存在移动端媒体查询（若 P1-2 未完成则标注「未交付」而非失败）；4e/4f 按交付状态记「存在/缺失」，缺失项进遗留清单。
- **team-lead 批注（GO 前）**：theme-green 0 命中属 P1-7 在途（e-pi7-theme 落盘中），步骤 4b 标注「在途，非失败」；202610070010.sql 已有 → P1-6 视为已交付，步骤 5 正常执行静态自查。
- **执行期实况（覆盖批注）**：执行时 P1-7 已落盘，4b 实际命中（ThemeToggle.vue + theme-green.scss），6/6 全中，未触发在途标注。

## 步骤 5 · JSON_MERGE_PATCH SQL 语法自查（P1-6，~5s）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror
grep -rn "JSON_MERGE_PATCH" manager-api/ | head
```
- **判据**：命中形如 `UPDATE … SET config_json = JSON_MERGE_PATCH(config_json, :json)` 的**单条原子**语句；若仍为非原子读改写（LWW 两处分离）→ 记「P1-6 未生效」。占位符风格（`:name` / `?`）与 MyBatis/项目既有 SQL 风格一致即可。

## 步骤 6 · secret 模板与 .gitignore 生效（P0-1，~10s）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server
# 6a. 旧生产 secret 仍明文存在（P0-1 未闭合的判据）
grep -n "2d7b6bde" data/.config.yaml
grep -rn "2d7b6bde" . --include=*.yaml --include=*.yml 2>/dev/null
# 6b. .gitignore / 模板（准备期实测：镜像目录**不是 git 仓**，无任何 .gitignore，无法在此验证）
ls -a | grep gitignore; ls data/ | grep -i "template\|sample"
```
- **判据**：6a 命中 0 = P0-1 已轮换/清除；6b 有 .gitignore 含 `data/.config.yaml` 且模板存在 = 已生效。
- **已知限制**：镜像非 git 工作树 → 6b 全部缺失时**降级为静态标注「镜像侧不可验证，转 e-secret-ops 在真实仓确认」**，不算回归失败；仅 6a 命中记为 P0 未闭合（遗留清单首条）。

## 步骤 7 · 前端契约+单测快检（~60s 上限）

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/manager-web
timeout 30 node --test tests/*Contract.test.mjs     # 基线 9/9（准备期实测 8/8，以当前文件为准）
timeout 45 node_modules/.bin/vitest run --reporter=basic   # 基线 7/7
```
- 超时项降级：跳过 vitest，仅以 7 静态判据 + 契约测试结果入账并标注。
- **判据**：pass = 总数，fail = 0。

---

## 预算总表（上限合计 ≈ 4.5 min < 5 min）

| 步骤 | 命令组 | 上限 |
|---|---|---|
| 1 | pytest（含前置挪移） | 90s + 15s |
| 2 | tag-balance ×7 | 15s |
| 3 | grep 残留 | 10s |
| 4 | P1 抽查 | 20s |
| 5 | SQL 自查 | 5s |
| 6 | secret/gitignore | 10s |
| 7 | node --test + vitest | 75s |
| 合计 | | **~4.4 min** |

## 产出格式（GO 后回报 team-lead）

1. 通过率：每步骤 PASS/FAIL/SKIP + 一行命令输出摘要
2. 失败项：文件:行 + 命令 + 原始输出（截断 20 行内）
3. 遗留问题清单：未交付 P1 / 超时降级项 / P0-1 未闭合项，逐条编号

## 执行前协调事项

- **e-secret-ops**：步骤 1 会临时挪移 `data/.config.yaml`，若你正在改它请错峰；P0-1 交付后该步骤简化为直接跑。
- **e-pi 批次**：步骤 4 的 4b/4c/4e/4f 按「存在则检查、缺失记遗留」处理，不影响判失败。

---

## 执行记录（GO 批次，2026-10-06）

### 实际执行命令（与环境修复后的最终口径）

```bash
# 步骤 1（最终有效命令）
cd G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server
# 前置：data/.config.yaml 临时裁剪为无 manager-api 块的 6 行版本（conftest exit2 守卫），
#       原始 9 行版本完整备份 /tmp/qa_config_orig.yaml，跑完已恢复
cp data/.config.yaml /tmp/qa_config_orig.yaml && head -6 data/.config.yaml > data/.config.yaml
py -3.13 -m pytest -p no:dash -p no:anyio tests -q
cp /tmp/qa_config_orig.yaml data/.config.yaml
```
环境修复（一次性，已偏离 5min 预算并在此标注）：本机无现成可用解释器——
`py -3.13`（D:/INSTALL/python313）缺 pytest/pyyaml/requests/PyJWT/cryptography/portalocker/psutil/cnlunar==0.2.0 等，
`pip install -r requirements.txt` 因 torch==2.2.2 PyPI 无版失败（已跳过 torch 系批量装齐）；
user-site 的 dash/anyio pytest 插件与 pytest 9 不兼容 → `-p no:dash -p no:anyio`。
结果：**1 failed / 60 passed / 5 skipped**；新契约测试 `tests/core/providers/tools/test_device_config_sync.py`（06:44 落盘，8 用例）单独验证 **8/8 PASSED**（注：落盘位置与 GO 指令所述 `tests/test_device_config_sync_contract.py` 不同，按「存在则跑」执行）。
唯一失败 `test_tts.py::test_tts_text_to_speak_writes_file` = workbuddy sitecustomize safe-delete bulk guard（50 文件阈值）对 tmp/tts-*.mp3 写盘触发 `SystemExit(1)`，**环境因素非产品缺陷**，降级静态判据（TTS 构造类 4 用例全过）。
5 skipped = 设计内（缺 data/.config.yaml 真配 / LLM 占位 key）。

### 结果速览
- 步骤 2 tag-balance：8/8 PASS（含 KawaiiMobileDrawer.vue、DeviceConfigManager.vue）
- 步骤 3 grep 残留：3a/3c/3d 通过；**3b 失败——4 处 calc(100vh 残留**（DeviceManagement.vue:454 / roleConfig.vue:1943 / VoiceCloneManagement.vue:374 / VoiceResourceManagement.vue:288）
- 步骤 4 P1 抽查：jelly-motion.scss（15 处 spring/cubic-bezier + reduced-motion 降级）、theme-green（ThemeToggle.vue L18-23）、移动端断点（1023/767 三处）、/device-config-management（router L232）、mqtt-gateway-verify.md、pwa-screenshot-compare.mjs + qa-screenshots/ → **全部存在**
- 步骤 5 JSON_MERGE_PATCH：DeviceConfigDao.java:30 单条原子 upsert ✓（`VALUES()` 语法 8.0.20+ 弃用但可用，轻微提示）
- 步骤 6 secret：旧生产 secret 2d7b6bde 仍在 data/.config.yaml:9（P0-1 未交付）；镜像非 git 仓，.gitignore/模板无法镜像侧验证 → 转 e-secret-ops 真实仓确认
- 步骤 7：node --test 契约 9/9 ✓；vitest 15+9 全过（基线「7/7」口径已过时，format 现为 9 用例）；3 个 unhandled EPERM = workbuddy temp 文件 shim，环境因素
