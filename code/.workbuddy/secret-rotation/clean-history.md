# git 历史清除操作手册（server.secret 明文入库治理）

> 状态：**只写不执行**。所有命令需人工执行，执行前完成 secret 轮换（rotate-secret.sh）。
> 事实（2026-10-06 实测）：
> - 仓库 `G:/demo/21_xiaozhi/code-server-mirror`（git 根在镜像根目录，非 yuhe-server 子目录），
>   仅 1 个提交 `31c20d1 "init: yuhe-server source mirror from sandyun.top (AOCI baseline)"`，
>   **无 remote**（`git remote -v` 为空）。
> - `yuhe-server/data/.config.yaml` L9 `secret: 2d7b6bde-…` 已含在该提交中。
> - 该文件是运行时文件：清历史后**必须保留在工作区**（Python 服务从该路径读配置），只是不再进 git。

---

## 步骤 0：前置（必须先完成）

1. rotate-secret.sh 已在部署机执行并冒烟通过（旧 secret 已失效）。
2. 本地离线留底了 `/root/backup/secret-rotation/*/old-secret.txt`（回滚唯一依据）。
3. 确认旧值 `2d7b6bde-4de9-49f1-9072-476cec13292e` 已不再被任何脚本/QA 用例引用（或已同步改掉）——清史前把引用全部更新，避免清史后从别的文档恢复。

## 步骤 1：本地源仓库清史（需人工在本机执行）

本仓库**只有一个提交**，最简可靠路径是 amend 掉 init 提交（等价于 BFG 的效果，无需重打包对象）：

```bat
:: Git Bash 下执行（路径用正斜杠）
cd G:/demo/21_xiaozhi/code-server-mirror

:: 1) 从 git 跟踪中移除该文件（保留工作区文件，Python 服务不受影响）
git rm --cached yuhe-server/data/.config.yaml

:: 2) 重写唯一的 init 提交（不追加新提交——新提交仍可在历史里搜到旧值，必须 amend）
git commit --amend --no-edit
```

校验（必须全过才算清干净）：

```bash
# 历史里搜旧值：无输出 = 干净
git log -S '2d7b6bde-4de9-49f1-9072-476cec13292e' --all --oneline
# 文件仍在工作区、且被 ignore
test -f yuhe-server/data/.config.yaml && echo FILE_KEEP_OK
git check-ignore -v yuhe-server/data/.config.yaml   # 应命中 .gitignore 规则（见步骤 3）
# 工作区内容与磁盘实际文件一致（防 amend 误改内容）
git status --porcelain yuhe-server/data/.config.yaml   # 应为空（被 ignore 后不显示）
```

> 若团队规范坚持用工具链（或将来提交数 >1），等价替代方案二选一：
>
> **BFG**（Windows 需 Java 环境）：
> ```
> java -jar bfg.jar replace-text old-secrets.txt --.directory-in . \
>   --folder G:/demo/21_xiaozhi/code-server-mirror   :: old-secrets.txt 内容：2d7b6bde-4de9-49f1-9072-476cec13292e=***
> ```
> **git filter-repo**（更现代，需 `pip install git-filter-repo`）：
> ```
> git filter-repo --replace-text <(echo "2d7b6bde-4de9-49f1-9072-476cec13292e==>***") --force
> ```
> 清完统一收尾：
> ```bash
> git reflog expire --expire=now --all
> git gc --prune=now --aggressive
> ```
> （GC 之后被引用的旧对象才真正物理消失，**必须执行**，否则 .git/objects 里仍搜得到旧值。）

## 步骤 2：远端处置

当前 `git remote -v` 为空，**本镜像无远端，步骤 2 不适用**——但按以下规则应对未来的远端：

- 若源仓库（上游 yuhe-server 官方库或其他 fork）历史中**不含**本生产 secret（官方库种子值是占位/示例），**不需要**去官方库提 PR；只需确认团队私有 fork 无远端推送即可。
- 若任一私有远端曾 `push` 过该 init 提交：清史后 `git push --force-with-lease <remote> <branch>`，并联系 Git 服务商（GitLab/Gitee）清除其服务端未 GC 的旧对象（force push 不会删除服务端旧 reflog/pack）；**轮换 secret 已先行完成**（所以旧值即使被远端泄露也已失效，这正是 runbook 顺序「先轮换→再清史」的原因）。
- 本仓库若日后新增 remote：先清史、再首次推送。

## 步骤 3：.gitignore 兜底（另一工程师负责建，此处仅引用）

`yuhe-server/.gitignore` 需含以下条目（或等价的 `data/.config.yaml` 规则）——**建立后步骤 1 的校验 `git check-ignore` 才能通过**：

```gitignore
# 运行时配置/数据（含 server.secret 明文），严禁入库
yuhe-server/data/.config.yaml
yuhe-server/data/memory/
```

交接点：e-pi4/e-pi6 或其他负责 .gitignore 的工程师建立该文件后，请其回报条目内容，再执行步骤 1 的 amend（顺序：.gitignore 先入库 → `git rm --cached` → `commit --amend`）。

## 步骤 4：团队知会（清史完成后立即发）

发给 team-lead 的知会模板：

1. 旧 secret `2d7b6bde-…` 已失效（轮换时间：<填写>），任何仍在用旧值的脚本/QA 断言/e2e 套件 `AUTH_KEY` 默认值需改为新值；
2. 新 secret 完整值仅存在于：部署机 `/root/backup/secret-rotation/<TS>/old-secret.txt` 的**同目录 rotation-RESULT.log**（其中 `new_secret=` 行）、MySQL `sys_params`、`data/.config.yaml` L9——**不要**再写进任何会被 git 跟踪的文件或聊天记录明文；
3. 本地镜像 init 提交已重写（`31c20d1` 旧 hash 作废），依赖过该 hash 做基线比对的同事（如 aoci baseline）需重新取 HEAD；
4. `qa_memory` 脚本（deploy_memory_v1.md R2/R3 段的 `AUTH_KEY=2d7b6bde-…`）在下一轮部署/QA 前先替换为新值。
