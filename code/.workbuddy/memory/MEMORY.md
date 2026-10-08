# xiaozhi-esp32 AOCI 项目记忆（长期）

## aoci CLI 运行必读（环境陷阱）
- git 仓库根 = `G:/demo/21_xiaozhi`（那里有 `.git`），`xiaozhi-esp32` 只是子目录。
- `aoci.exe` 靠 `.git` 定位仓库根 → 会错误指向父目录并报告 "The index does not exist; run aoci init first"。
- **必须显式指定 `--repo G:/demo/21_xiaozhi/code/xiaozhi-esp32`** 才能让 `aoci status` / `aoci verify` / `aoci update-entry` 正确作用于本项目。
- CLI 路径：`D:/INSTALL/aoci/aoci.exe`。离线确定性工具，无 AI 配置也能跑治理命令。

## 治理模式（Volumes v1 + Managed Scope）
- `aoci scan --force` 被锁定：已有 Managed Scope Baseline 不能通过 scan 重建。
- **`scope apply` / `scope plan` / `scope preview` 在本环境有缺陷**：全量重扫且不套用 `exclude_dirs`，会把 index 从 ~1071 暴涨到 ~9000+（41196 等）。严禁使用，会用它"修复对齐"会破坏索引。
- `governance_aligned: false` 是**结构性、既存、无害**的：工具 computed scope 要 9016 index（忽略 exclude_dirs 缺陷）vs 策展基线 1074 index → `policy_identity ≠ active_policy_identity`。它代表 scope 策略指纹不符，**不代表内容漂移**（code_drift 恒为空）。
- 安全增量流程：`aoci update-entry --repo ... --source-sha256 <sha> <file[tag]>` 写条目；基线指纹刷新走**手动 Python 编辑** baseline.json（套用 exclude_dirs + .git/.aoci/.workbuddy），不触发重扫。

## 基线/索引关键事实
- 基线 baseline.json：`{files:{相对路径:{role,sha256,size,normalized_sha256}}}`，role∈index/observe/exclude。
- 660 个二进制资产（.ogg/.jpg/.png/.eaf）已被人工从 index 翻为 observe（在基线直接持有，非依赖 config 规则；config.json 的 scope.rules 实际为空，规则未持久化但不影响现状）。
- 全部 2808 个二进制资产在基线中均为 observe。
- aoci.code.txt 条目格式：`文件名[标签]: F:... | R:... | A:... | S:...`；标签形如 `EA9L`（A层-模块-重要性-规模）；规模档由行数定（S<~80→S/T, ~220→M, ~450→L）；S 字段有 FRAS token 预算（C4≤40/C7≤80/C9≤200）。

## 备份
- baseline 编辑前必备份：`baseline.json.bak-<UTC时间戳>`。已知：20261007T192834Z（660翻转前）、20261009T003322Z（reconcile前）。
