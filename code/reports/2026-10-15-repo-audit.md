# 本地项目目录审计与整理方案

> 生成：2026-10-15 22:40 GMT+8 ｜ 扫描方式：全量只读审计（20 个并行 agent 因基础设施 406 故障全部失败，由主 agent 亲自完成）
> 仓库：G:/demo/21_xiaozhi（git 仓，远程 gitee，.git 468M / 136 commits）

---

## 一、总览

| 区域 | 大小 | 一句话判定 |
|---|---|---|
| code/big_secreen | 1.2G | 大屏固件工作区（活跃）· build 384M + managed_components 758M 可回收 |
| code/small_secreen | 1.2G | 小屏固件**规范主区**（最活跃）· 同上构成 |
| code/small_secrenn_test | 1.2G | small_secreen 的试验沙盒（与主区仅 4 文件不同）· git 未跟踪 |
| code/camera | 1.2G | **独立上游仓库副本**，开发 lckfb/szpi-esp32s3 摄像头板（IDF v6.1）· **git 完全未跟踪（代码无版本保护）** |
| code/test_environment | 1.2G | 测试环境部署包快照（app 933M + db 189M + deploy 82M）· 远端真实环境在 22223 |
| code-server-mirror | 633M | 服务端源码镜像（含未部署 order 模块，红线保留）· node_modules 292M + 5 份 dist 共 78M 可回收 |
| hermes-agent-main | 338M | 上游 agent 框架参考仓（带 .aoci 治理）· 保留 |
| 网页后台 | 275M | **最早期上游 xiaozhi-esp32-server 完整克隆**（1625 个 git 跟踪文件，状态干净）· 与 code-server-mirror 功能重叠 |
| code/super_small_screen | 173M | 小屏原型（已被 small_secreen 取代）· build 170M 可回收 |
| console-v2 | 43M | 生产前端（活跃）· 有源码未进 git（风险） |
| stylekit / aoci-code / cc-console | 42M/17M/39M | UI 样式库参考 / AOCI 工具源码 / 旧控制台（线上仍在用）· 保留 |
| 根目录散件 | ~400K | 4 个 TTS 探针脚本 + 2 输出目录 + 6 份项目文档 |

## 二、关键发现（风险点）

1. **【高危】console-v2 有 7 个 .vue 生产源码未进 git**：AuditLog / CustomReview / DisplayConfig / Roles / UserDefaults（admin）+ MyModels / Profile（customer）——全部被 main.js 引用（第 35-44 行），生产已部署但本地无版本保护，误删即丢失。
2. **【高危】code/camera 整个 1.2G 未进 git**：摄像头板固件开发中（szpi-esp32s3），有自定义 build_szpi.bat、board 改动，无任何版本保护。
3. **【敏感】code/artifacts/token_main.json 含登录 token + clientHash**：虽是测试 token，不应躺在可入库的 artifacts 目录。
4. **nul 保留名文件 ×3**：code/nul（51B，`dir` 命令误重定向产物）、camera/nul（365B，git CRLF 警告重定向）、small_secreen/nul（同类）——Windows 下无法常规删除，需 PowerShell `\\?\` 前缀隔离到 .trash（已有先例）。
5. **code/.mcp.json 已失效**：三个 MCP 条目全部指向 `code/xiaozhi-esp32`（该目录已不存在，现分散在 big_secreen/small_secreen 下）。
6. **纯冗余副本 ×4**：code/ 根的 heartbeat.py.new/.orig 与 push_scheduler.py.new/.orig 两对文件 diff=0（内容完全相同，是当时留下的重复拷贝，正式补丁在生产与 fixes/ 体系里）。
7. **git 22 个已修改文件未提交**：含 big_secreen 固件源码（application.cc 等 8 个）、small_secreen 板型 4 个、console-v2 3 个、code-server-mirror 4 个（order 模块相关）、memory 文档 3 个。
8. **.workbuddy 里有 330M 死重**：scope_status_server.json 150M + aoci/results 155M + scope_plan/status_hermes 25M——全部来自已锁定的 scope 工具失败实验（记忆确认 scope apply/plan/preview 已禁用）。

## 三、整理方案（分五步，P1 最优先）

### P1 · Git 保护（零风险，最优先）
- 补提交：console-v2 七个 .vue + deploy/ + 3 份验收报告；code/{fixes,reports,tests} 交付物；code-server-mirror order 模块（**只入库不部署**，红线不变）；artifacts/push-debug（剔除 token_main.json）
- 提交 22 个已修改文件（按模块分组 commit）
- .gitignore 增补：`code/nul`、`code/sim-*`、`console-v2/.tmpbuild/`、`code/artifacts/agent-*/`、`code/agents/`、camera 与 small_secrenn_test 的 build/managed_components（若整目录入库则先加 ignore 再 add 源码）
- camera/ 源码入库（build/、managed_components/ 除外）

### P2 · 空间回收（可再生产物，~2.5G）
| 目标 | 可回收 | 说明 |
|---|---|---|
| 5 个固件区 build/ | 1.74G | 纯编译缓存，idf.py 可重建（big 384M + small 400M + secrenn_test 397M + camera 386M + super_small 170M） |
| code-server-mirror/manager-web 旧 dist ×4 + node_modules | 354M | dist-bak2-20261010/dist-viz/dist-qtts/dist-new 共 62M + node_modules 292M（npm i 可重建） |
| .workbuddy scope 死重 | 330M | scope_status_server.json 150M + aoci/results 155M + hermes scope 25M（工具已锁定，产物永不再用） |
| code/.workbuddy deploy_tmp + web tars | 59M | deploy_tmp 26M + 3×11M web_*.tar.gz（部署中间产物） |

### P3 · 目录规范化（挪文件，可逆）
- 根目录：6 份 PROJECT-*.md + 验收清单 → `docs/`（新建）；4 个 tts 探针脚本 + tts_out/ + tts_ab_out/ + tts_output.opus → `docs/archive/tts-probe-20261009/`（结论已沉淀记忆，留档即可）
- code/ 根散件：sim-body.bin + sim-headers.txt → artifacts/push-debug/；heartbeat/push_scheduler 四个冗余副本 + ._tmp_devmgmt.scss + .tmpbuild → .trash；logs/ → docs/archive/（或保留）；验收清单 → 根 docs/
- 3 个 nul → PowerShell `\\?\` 隔离到 .trash/
- .mcp.json 修正路径（aoci-fw 指向 small_secreen/xiaozhi-esp32 等）或移除失效条目
- README.md 充实为真实导航（当前仅 1 行）

### P4 · 大区处置（需用户拍板）
- **网页后台 275M**：最早期完整克隆，git 干净、1625 文件入库。与 code-server-mirror 重叠，但 code-server-mirror 无 Python main/ 的完整 docker 体系。建议整体移出仓库归档（历史在 git 里永远可找回）。
- **test_environment 1.2G**：远端 22223 的离线部署包。建议移出仓库归档（或保留——若常用它恢复测试环境）。
- **small_secrenn_test 1.2G**：与 small_secreen 仅 4 文件差异的沙盒。建议保留（是改板试验田）但清理其 build/managed_components；或与主区合并后删除。
- **super_small_screen 173M**：已被取代的早期原型。建议归档或仅清 build 保留源码。

### P5 · 收尾
- 整理后全量 `git status` 应接近干净；更新 README 导航；写入项目记忆。

## 四、预计效果

- **保守执行 P1-P3**：磁盘回收 ~2.5G，git 工作区从 22M+57?? 降到接近 0，根目录从 30+ 散件降到 ~10 个目录
- **加 P4 全部归档**：再回收/外移 ~2.6G，仓库总占用从 ~8.6G 降到 ~3.5G

## 五、执行纪律

- 删除一律进 `.trash/`（本仓既有隔离区），不用 rm 直删；git 跟踪文件的"删除"通过 git mv/rm 走历史
- 每步动作前备份受影响 index（baseline.json 不动）
- 20 个并行 agent 因基础设施 406 全部失败，本次审计由主 agent 独立完成，结论均有一手命令输出佐证

---

## 六、执行结果（2026-10-15 22:40-22:55，用户确认 P1-P4 全做）

### 已全部完成 ✓
**P1 Git 保护（14 提交，git status → 0）**
- 补提交：console-v2 7 个 .vue + deploy/ + 3 报告；push-audio 全部交付物；code-server-mirror order 模块（仅归档不部署）；workbuddy 产物 43 文件；杂项 7 文件
- 22 个已修改文件分 5 组提交（固件双屏/console-v2/mirror/记忆）
- camera 嵌套仓自身提交 `03b09d2`（653 处 dev 改动）；父仓加 ignore `code/camera/`
- 3 个 nul 保留名文件 PowerShell `\\?\` 隔离 → .trash
- token_main.json（登录 token）移出 git + 隔离 + ignore

**P2 空间回收（全部进 .trash 可回滚）**
- 5 处 build ≈1.7G + secrenn_test managed_components 758M = **2.5G**
- manager-web 4 份死 dist + node_modules = **352M**
- .workbuddy scope 死重 + backup + log = **504M**（含 150M scope_status_server.json）
- super_small_screen/build 1718 文件 + 3 个 web_*.tar.gz 退出 git 跟踪

**P3 目录规范化（git mv 保历史）**
- 6 份 PROJECT-*.md → docs/；验收清单 ×2 → docs/；logs → docs/archive/logs-20261010/
- TTS 探针 4 脚本 + tts_out/ + tts_ab_out/ + tts_output.opus → docs/archive/tts-probe-20261009/
- sim-body.bin/sim-headers.txt → artifacts/push-debug/；README 充实；.mcp.json 拆分 small/big 条目

**P4 大目录归档（git rm --cached 保历史后物理外移）→ G:/demo/archive-20261015/**
- 网页后台 275M ✓、test_environment 1.2G ✓、super_small_screen 173M ✓
- small_secrenn_test **保留**（清 build+managed_components，46M 源码沙盒）

### 最终状态
| 指标 | 整理前 | 整理后 |
|---|---|---|
| git 未提交/未跟踪 | 22 M + 57 ?? | **0** |
| 仓库占用 | ~8.6G | **3.3G**（+.trash 3.3G 可回滚 + 外移 1.5G） |
| 根目录条目 | 30+ 散件 | 9 目录 |

### 遗留（后续可选）
- .trash/ 3.3G 观察期后确认无用可删（含全部 build 缓存，删则彻底释放）
- .git 468M 历史膨胀可 `git gc --aggressive`（可选，需用户确认）
- 活跃固件区 build 已清 → 下次构建需全量编译
