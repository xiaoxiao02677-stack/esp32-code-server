# xiaozhi-esp32 AOCI 项目记忆（长期）

## aoci CLI 运行必读（环境陷阱）
- git 仓库根 = `G:/demo/21_xiaozhi`（那里有 `.git`），`xiaozhi-esp32` 只是子目录。
- `aoci.exe` 靠 `.git` 定位仓库根 → 会错误指向父目录并报告 "The index does not exist; run aoci init first"。
- **必须显式指定 `--repo <子项目绝对路径>`** 才能让 `aoci status` / `aoci verify` / `aoci update-entry` 正确作用于本项目。
- CLI 路径：`D:/INSTALL/aoci/aoci.exe`。离线确定性工具，无 AI 配置也能跑治理命令。

## 项目结构（2026-10-10 重组）
- 原单一 `code/xiaozhi-esp32` 已拆分为**两个独立 AOCI 子项目**（各自带 `.aoci` 索引与备份）：
  - 大屏：`G:/demo/21_xiaozhi/code/big_secreen/xiaozhi-esp32`（含新板级 `main/boards/bigscreen-s3/`）
  - 小屏：`G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32`（含 my-s3-tft 圆屏 + audio 引擎改造）
- 两者基线规模相近（~12600 文件）。新增首方源默认归 `observe`，重要板级源建议建 FRAS 条目升 `index`。
- 安全同步脚本：`G:/demo/21_xiaozhi/code/.workbuddy/safe_reconcile.py`（参数=repo路径；raw-sha-only 比对，先备份再仅刷新 raw 变化者）。

## 治理模式（Volumes v1 + Managed Scope）
- `aoci scan --force` 被锁定：已有 Managed Scope Baseline 不能通过 scan 重建。
- **`scope apply` / `scope plan` / `scope preview` 在本环境有缺陷**：全量重扫且不套用 `exclude_dirs`，会把 index 从 ~1071 暴涨到 ~9000+（41196 等）。严禁使用，会用它"修复对齐"会破坏索引。
- `governance_aligned: false` 是**结构性、既存、无害**的：工具 computed scope 要 9016 index（忽略 exclude_dirs 缺陷）vs 策展基线 1074 index → `policy_identity ≠ active_policy_identity`。它代表 scope 策略指纹不符，**不代表内容漂移**（code_drift 恒为空）。
- 安全增量流程：`aoci update-entry --repo ... --source-sha256 <sha> <file[tag]>` 写条目；基线指纹刷新走**手动 Python 编辑** baseline.json（套用 exclude_dirs + .git/.aoci/.workbuddy），不触发重扫。
- **基线 reconcile 铁律（2026-10-09 踩坑）**：同步指纹时**只比较 raw sha256（实际内容），仅当 raw 不同才刷新 sha256/size/normalized_sha256 三项**；raw 相同则原样保留 baseline 中原始的 normalized_sha256，绝不按自算的 LF 归一化值批量覆盖。否则会把数千文件误判为"changed"并改写 normalized_sha256，导致 aoci verify 出现伪漂移。`.workbuddy` 目录走扫描排除但基线已有条目须 preserve（不 drop）。size 在 baseline 中以 int 存储。

## 基线/索引关键事实
- 基线 baseline.json：`{files:{相对路径:{role,sha256,size,normalized_sha256}}}`，role∈index/observe/exclude。
- 660 个二进制资产（.ogg/.jpg/.png/.eaf）已被人工从 index 翻为 observe（在基线直接持有，非依赖 config 规则；config.json 的 scope.rules 实际为空，规则未持久化但不影响现状）。
- 全部 2808 个二进制资产在基线中均为 observe。
- aoci.code.txt 条目格式：`文件名[标签]: F:... | R:... | A:... | S:...`；标签形如 `EA9L`（A层-模块-重要性-规模）；规模档由行数定（S/T 边界≈70 行：69→S/T，81 行实测须 **T**，故 ≥~70 优先 T；~221→M；~449→L）；S 字段有 FRAS token 预算（C4≤40/C7≤80/C9≤200）；模块字母须合法（`CT` 触发 `impact_candidate_tag_dictionary_violation`，`CH` 可用）。
- **⚠️ FRAS 字段分隔符铁律（2026-10-10 踩坑，代价 3 次失败）**：F/R/A/S 四字段**必须用 ` | `（空格-竖线-空格）分隔**，绝不能用 `;` 或 `,`。误用 `;` 会让整行被解析成单一超长 `F`（>160 runes 触发 `fras_f_too_long`），且 `R/A/S` 判为空 → `update-entry` 报 `impact_candidate_fras_invalid`（含 `fras_r_empty`/`fras_a_empty`/`fras_s_empty`/`fras_structure_invalid`）。字段**内部**可用 `;` 细分小点。**`--preview --json` 是只读探测利器**：会返回结构化 `findings` 精确指出哪字段违规（含 `retry_scope`），先 preview 再正式写可避免盲试。
- **config.h 规模档**：同目录同名首方头按行数定档（76 行 → `CH4T`，与 `bigscreen_display.h[CH4T]` 一致）；全仓库其余 163 个上游 `config.h` 多标 `CH4S`，但工具会对 76 行文件给"E规模档位错配"提醒（属正常，可顺手改 T）。

## 备份
- baseline 编辑前必备份：`baseline.json.bak-<UTC时间戳>`。已知：20261007T192834Z（660翻转前）、20261009T003322Z（reconcile前）。
